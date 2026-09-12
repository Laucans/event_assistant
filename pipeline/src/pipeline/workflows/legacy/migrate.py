"""La bascule du markdown vers les issues, une fois.

Une commande a usage unique — `agent-loop migrate` — et la seule du paquet
qui **ecrit** sur GitHub sans qu'un stage paye soit passe. Trois proprietes
la rendent sure a lancer :

1. **`--dry-run` n'ecrit rien**, nulle part : ni issue, ni lien, ni fichier
   efface. Il imprime exactement ce que l'autre mode ferait ;
2. **elle est idempotente**. Chaque issue est cherchee par son titre et son
   etiquette avant d'etre creee, chaque lien est verifie avant d'etre pose.
   Une migration interrompue au milieu se relance et se termine, au lieu de
   creer une seconde roadmap a cote de la premiere ;
3. **rien ne recoit `pipeline:ready`.** Le robinet, c'est l'humain qui
   l'ouvre — une migration qui rendrait dix tasks jouables ferait partir la
   boucle sur un plan que personne n'a relu.

Ce qu'elle efface a la fin est ce qui vient d'etre traduit : `docs/ROADMAP.md`,
`docs/current/`, et le pointeur de reprise — dont la cle est un titre de
markdown qui ne designe plus rien.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.adapters.store import resume
from pipeline.workflows.legacy import migration
from pipeline.workflows.legacy.migration import NewIssue
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.adapters import hub

# Les documents traduits. Ce sont les derniers chemins du paquet qui pointent
# vers `docs/` : ils vivent ici plutot que dans `runtime.filesystem`
# parce qu'ils ne survivent pas a la commande qui les lit.
ROADMAP = "docs/ROADMAP.md"
MILESTONE = "docs/current/CURRENT_MILESTONE.md"
CURRENT_DIR = "docs/current"


def _read(ws: Workspace, path: Path) -> Result[str]:
    if not path.exists():
        return Result.halt(
            f"{ws.rel(path)} is missing — nothing to migrate from."
            f" If the migration already ran, the issues are on GitHub"
            f" and this command has nothing left to do.")
    return Result.of(path.read_text(encoding="utf-8"))


def _already_there(gh: GitHub,
                   plan: list[NewIssue]) -> Result[dict[tuple, int]]:
    """Ce que GitHub porte deja, indexe par `(etiquette, titre)`.

    Lu une fois pour tout le plan plutot qu'une fois par issue : c'est ce
    qui fait qu'une migration deja faite se constate en quatre appels au
    lieu de trente-deux.

    Ouvertes **et** fermees : une task migree puis terminee ne doit pas etre
    recreee par une seconde execution. Un titre reecrit a la main sur GitHub
    echappe a la reconnaissance — assume, et c'est pour ca que `--dry-run`
    imprime ce qu'il compte creer.
    """
    found: dict[tuple, int] = {}
    for label in sorted({i.labels[0] for i in plan}):
        for state in ("open", "closed"):
            listed = gh.issues_labelled(label, state=state)
            if listed.failed:
                return listed.recast()
            for issue in listed.value:
                found.setdefault((label, issue.title), issue.number)
    return Result.of(found)


def _links(issue: NewIssue, numbers: dict[str, int]) -> list[str]:
    """Comment cette issue se rattache, dite en clair pour un lecteur."""
    out = []
    if issue.parent:
        out.append(f"sub-issue of {_ref(issue.parent, numbers)}")
    if issue.blocked_by:
        out.append("blocked by "
                   + ", ".join(_ref(k, numbers) for k in issue.blocked_by))
    return out


def _ref(key: str, numbers: dict[str, int]) -> str:
    return f"#{numbers[key]}" if key in numbers else f"[{key}]"


def run(*, dry_run: bool, workspace: Workspace, gh: GitHub | None = None
        ) -> Result[str]:
    """Applique le plan (ou l'imprime), et rend le compte rendu."""
    here = workspace.root
    roadmap = _read(workspace, here / ROADMAP)
    if roadmap.failed:
        return roadmap.recast()
    milestone = _read(workspace, here / MILESTONE)
    if milestone.failed:
        return milestone.recast()
    plan = migration.plan(roadmap.value, milestone.value)
    gh = gh or hub.gh(workspace)

    if dry_run:
        out = ["migrate — dry run: nothing is written"]
    else:
        repo = gh.repo
        if repo.failed:
            return repo.recast()
        out = [f"migrate — writing to {repo.value}"]
    found_all = _already_there(gh, plan)
    if found_all.failed:
        return found_all.recast()
    seen = found_all.value
    numbers: dict[str, int] = {}
    for issue in plan:
        found = seen.get((issue.labels[0], issue.title))
        labels = " ".join(issue.labels)
        links = _links(issue, numbers)
        suffix = f" ({', '.join(links)})" if links else ""
        if found is None and dry_run:
            # Pas de numero a annoncer : les liens restent en cles de plan,
            # ce qui est aussi ce qui rend la sortie stable d'une execution
            # a l'autre.
            out.append(f"\nwould create [{labels}] {issue.title}{suffix}")
            out.append(_indent(issue.body))
            continue
        if found is not None:
            numbers[issue.key] = found
            out.append(f"\n#{found} [{labels}] {issue.title}{suffix}"
                       f"\n  exists already — not created again")
        else:
            created = gh.create_issue(issue.title, issue.body, issue.labels)
            if created.failed:
                return created.recast()
            numbers[issue.key] = created.value.number
            out.append(f"\ncreated #{created.value.number} [{labels}]"
                       f" {issue.title}{suffix}")
        # Les liens sont poses meme pour une issue qui existait deja : une
        # migration interrompue entre la creation et le lien laisse
        # exactement ca derriere elle. En dry-run ils sont seulement dits —
        # c'est ce chemin-la, et non celui de la creation, qui ecrirait sans
        # qu'on le lui demande.
        posed = _apply_links(gh, issue, numbers, dry_run=dry_run)
        if posed.failed:
            return posed.recast()
        if posed.value:
            verb = "would link" if dry_run else "linked"
            out.append(f"  {verb}: {', '.join(posed.value)}")

    out.append("")
    out.append(_cleanup(workspace, dry_run))
    out.append("Nothing carries pipeline:ready: the human opens the tap.")
    return Result.of("\n".join(out))


def _apply_links(gh: GitHub, issue: NewIssue, numbers: dict[str, int], *,
                 dry_run: bool) -> Result[list[str]]:
    """Pose les liens qui manquent, et rend ceux qu'il a fallu poser.

    Ne pose que ceux qui manquent : c'est la moitie de l'idempotence, l'autre
    etant de ne pas recreer une issue qui existe. En dry-run rien n'est pose
    et la liste est rendue quand meme, parce que c'est justement ce qu'un
    humain veut lire avant de laisser la commande ecrire.
    """
    posed = []
    number = numbers[issue.key]
    if issue.parent:
        parent = numbers[issue.parent]
        subs = gh.sub_issues(parent)
        if subs.failed:
            return subs.recast()
        if number not in [t.number for t in subs.value]:
            posed.append(f"sub-issue of #{parent}")
            if not dry_run:
                linked = gh.add_sub_issue(parent, number)
                if linked.failed:
                    return linked.recast()
    known: list[int] = []
    if issue.blocked_by:
        blockers = gh.blocked_by(number)
        if blockers.failed:
            return blockers.recast()
        known = [t.number for t in blockers.value]
    for key in issue.blocked_by:
        if numbers[key] not in known:
            posed.append(f"blocked by #{numbers[key]}")
            if not dry_run:
                held = gh.add_dependency(number, numbers[key])
                if held.failed:
                    return held.recast()
    return Result.of(posed)


def _indent(text: str) -> str:
    return "\n".join("  | " + line for line in text.splitlines())


def _cleanup(ws: Workspace, dry_run: bool) -> str:
    """Efface ce qui vient d'etre traduit, ou dit ce qui le serait.

    Le pointeur de reprise part avec le reste : sa cle est `4|Schema, seed &
    first DB-backed page`, un titre de markdown. Le laisser ne ferait pas
    reprendre le mauvais round — il ne correspond a aucun numero d'issue —
    mais il ferait lire `--status` de travers pour toujours.
    """
    said = [f"{'would delete' if dry_run else 'deleted'}: {ROADMAP},"
            f" {CURRENT_DIR}/",
            f"{'would clear' if dry_run else 'cleared'}:"
            f" {ws.rel(ws.state)} (its task key is a markdown title,"
            f" which no longer names anything)"]
    if not dry_run:
        (ws.root / ROADMAP).unlink(missing_ok=True)
        shutil.rmtree(ws.root / CURRENT_DIR, ignore_errors=True)
        resume.clear(ws.state)
    return "\n".join(said)
