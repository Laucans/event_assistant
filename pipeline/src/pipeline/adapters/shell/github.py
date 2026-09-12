"""Le binaire `gh`, emballe.

Une classe et non des fonctions de module, pour qu'un test la remplace par un
double au lieu de monkeypatcher un nom — c'est la seule facon d'exercer les
regles de saut de la revue, et le tableau d'issues, sans PR ni depot reels.

Rien ici ne decide : lire une PR, lire ses commentaires, en poster un, lire
une issue, en creer une, la relier. Ce qu'on fait de la reponse appartient a
`workflows.pr_review.flow` et a `workflows.agentic_dev_loop.board`.

Chaque appel nomme le depot, comme le faisait le `cd "$(git rev-parse
--show-toplevel)"` de `pr-review.sh` : `gh` resout la PR depuis son
repertoire courant, donc une revue lancee depuis un autre checkout y
resoudrait une PR homonyme — et posterait deux passes payantes de notes sur
une PR etrangere.

**Les issues passent par `gh api`**, pas par `gh issue`. Les sous-issues
(`issues/{n}/sub_issues`) et les dependances
(`issues/{n}/dependencies/blocked_by`) n'ont aucun flag natif dans `gh` :
puisque la moitie du modele doit de toute facon passer par l'API brute, tout
y passe, plutot que de laisser un lecteur deviner quelle moitie fait quoi.
"""

from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path

from pipeline.domain.outcomes.result import Result
from pipeline.domain.issues import Issue

# Assez pour un depot d'une personne, et une raison de ne pas dependre de
# `--paginate` : sa sortie multi-pages n'est pas un seul document JSON dans
# toutes les versions de `gh`, et un parseur qui se tromperait la rendrait un
# tableau vide — c'est-a-dire « plus rien a faire ».
PER_PAGE = "100"


def gh(*args: str, root: Path,
       check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          check=check, cwd=str(root))


def last_line(text: str | None) -> str:
    """The last meaningful line of a command's stderr — the diagnostic bit.

    `splitlines()[-1:]` formats as a Python list (`['fatal: …']`), and the
    `or ""` that followed it bound to the slice, so an empty stderr printed a
    bare `[]`. That was the one line a human had to read after two paid passes
    failed to post.
    """
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return lines[-1] if lines else "(no output on stderr)"


def unreadable(what: str, detail: str) -> Result:
    """La lecture d'issue qui n'a pas abouti, dite plutot que rendue vide.

    Meme discipline que `adapters.store.resume._unreadable`, et pour la meme
    raison : rendre `[]` sur une erreur d'API, c'est repondre « ce milestone
    n'a plus aucune task ouverte », qui est exactement l'entree qui declenche
    `/planner`. Un jeton expire couterait un run opus.
    """
    return Result.unreadable(
        f"cannot read {what} from GitHub ({detail}) — what is left to do is"
        f" unknown, and reading that as 'nothing left' is what makes the loop"
        f" open a roadmap item nobody asked for. Check `gh auth status` and"
        f" the repository, then re-run.")


def _issue(payload: dict) -> Issue:
    """Une issue de l'API, dans la forme que le domaine sait lire.

    Les etiquettes arrivent en objets sur la plupart des points d'entree et
    en chaines sur certains : les deux sont acceptees, parce qu'un `TypeError`
    ici arreterait un run pour une difference de forme sans importance.
    """
    labels = []
    for label in payload.get("labels") or ():
        labels.append(label["name"] if isinstance(label, dict) else str(label))
    return Issue(number=int(payload["number"]),
                title=payload.get("title") or "",
                state=payload.get("state") or "open",
                labels=tuple(labels),
                body=payload.get("body") or "")


def _merged(rows) -> list[Issue]:
    """Les PR de la liste qui ont ete mergees, dans l'ordre recu.

    Le filtre s'arrete la : `merged_at` est une propriete de l'API, et la
    lire est le travail de cet adaptateur. Quelle PR *vaut preuve de
    livraison* est la convention d'un workflow, et se decide chez lui.
    """
    return [_issue(row) for row in rows or [] if row.get("merged_at")]


class GitHub:
    """Ce que la boucle et la revue demandent a `gh`, et rien de plus."""

    def __init__(self, root: Path, run=None, repo: str = "") -> None:
        self.root = root
        self._run = functools.partial(gh, root=root) if run is None else run
        self._repo = repo
        # `sub_issue_id` et `issue_id` prennent l'identifiant interne d'une
        # issue, pas son numero. Le retenir evite de relire la meme issue a
        # chaque lien pose par `migrate`.
        self._ids: dict[int, int] = {}

    def authenticated(self) -> bool:
        """`gh` est-il authentifie ?

        Ici et pas dans la porte qui pose la question : un `subprocess.run`
        nu vivait dans `preconditions`, seul appel externe du paquet a ne pas
        passer par un adaptateur. La porte lit desormais une reponse, comme
        elle lit `dirty_files()` ou `has_branch()`.
        """
        return self._run("auth", "status", check=False).returncode == 0

    # --- les PR ------------------------------------------------------------

    def pr(self, ref: str, fields: str):
        """Les metadonnees d'une PR, ou None si `gh` n'a pas pu la lire.

        Rend `(donnees, diagnostic)` : le diagnostic est la derniere ligne
        utile de stderr, celle qu'un humain doit lire apres deux passes
        payees pour rien.
        """
        out = self._run("pr", "view", ref, "--json", fields, check=False)
        if out.returncode != 0:
            return None, last_line(out.stderr)
        return json.loads(out.stdout), ""

    def comment_bodies(self, num: str) -> tuple[str | None, str]:
        """Le corps de tous les commentaires d'une PR, concatenes.

        Rend `(texte, diagnostic)` comme `pr` : une lecture ratee rendait une
        chaine vide, que la regle de saut lisait comme « aucune revue » — et
        deux passes payees repostaient un commentaire en double.
        """
        out = self._run("pr", "view", num, "--json", "comments", "-q",
                        ".comments[].body", check=False)
        if out.returncode != 0:
            return None, last_line(out.stderr)
        return out.stdout, ""

    def post_comment(self, num: str, body_file) -> tuple[bool, str]:
        """Poste un commentaire. Rend `(pose, diagnostic)`.

        Sans `check=False` un echec levait un `CalledProcessError` nu en
        avalant stderr : deux passes payees perdues, et rien qui dise ou est
        le texte.
        """
        out = self._run("pr", "comment", num, "--body-file", str(body_file),
                        check=False)
        if out.returncode != 0:
            return False, f"exit {out.returncode}: {last_line(out.stderr)}"
        return True, ""

    # --- l'API : lire ------------------------------------------------------

    @property
    def repo(self) -> Result[str]:
        """`owner/name`, demande une fois a `gh` et retenu."""
        if self._repo:
            return Result.of(self._repo)
        out = self._run("repo", "view", "--json", "nameWithOwner", "-q",
                        ".nameWithOwner", check=False)
        if out.returncode != 0 or not out.stdout.strip():
            return unreadable("the repository name", last_line(out.stderr))
        self._repo = out.stdout.strip()
        return Result.of(self._repo)

    def _read(self, what: str, path: str, *args: str) -> Result:
        """Une lecture d'API. `path` est relatif au depot.

        Le depot est resolu ici plutot que par l'appelant : c'est la seule
        facon qu'un nom de depot illisible soit un echec propage comme les
        autres, au lieu d'un arret qui traverserait le point d'appel.
        """
        repo = self.repo
        if repo.failed:
            return repo.recast()
        out = self._run("api", f"repos/{repo.value}/{path}", *args,
                        check=False)
        if out.returncode != 0:
            return unreadable(what, last_line(out.stderr))
        try:
            return Result.of(json.loads(out.stdout or "null"))
        except ValueError as exc:
            return unreadable(what, f"{type(exc).__name__}: {exc}")

    def labels(self) -> Result[list[str]]:
        """Les etiquettes que le depot porte, par leur nom."""
        return self._read("the repository labels", "labels", "-X", "GET",
                          "-f", f"per_page={PER_PAGE}"
                          ).map(lambda rows: [r["name"] for r in rows or []])

    def issue(self, number: int) -> Result[Issue]:
        got = self._read(f"issue #{number}", f"issues/{number}")
        if got.failed:
            return got.recast()
        task = _issue(got.value)
        self._ids[task.number] = int(got.value["id"])
        return Result.of(task)

    def issues_labelled(self, label: str,
                        state: str = "open") -> Result[list[Issue]]:
        """Les issues portant cette etiquette, PR exclues.

        `/issues` rend aussi les pull requests — GitHub les modelise comme des
        issues. Une PR portant par megarde l'etiquette qu'on demande entre
        alors dans la reponse, et un appelant qui cherche son milestone la
        prendrait pour un ; la cle `pull_request` est ce qui les distingue.
        """
        return self._read(
            f"the {label} issues", "issues", "-X", "GET",
            "-f", f"labels={label}", "-f", f"state={state}",
            "-f", f"per_page={PER_PAGE}"
        ).map(lambda rows: [_issue(r) for r in rows or []
                            if "pull_request" not in r])

    def sub_issues(self, number: int) -> Result[list[Issue]]:
        return self._read(f"the sub-issues of #{number}",
                          f"issues/{number}/sub_issues",
                          "-X", "GET", "-f", f"per_page={PER_PAGE}"
                          ).map(lambda rows: [_issue(r) for r in rows or []])

    def blocked_by(self, number: int) -> Result[list[Issue]]:
        return self._read(f"what blocks #{number}",
                          f"issues/{number}/dependencies/blocked_by",
                          "-X", "GET", "-f", f"per_page={PER_PAGE}"
                          ).map(lambda rows: [_issue(r) for r in rows or []])

    def blocking(self, number: int) -> Result[list[Issue]]:
        return self._read(f"what #{number} blocks",
                          f"issues/{number}/dependencies/blocking",
                          "-X", "GET", "-f", f"per_page={PER_PAGE}"
                          ).map(lambda rows: [_issue(r) for r in rows or []])

    def with_blockers(self, tasks: list[Issue]) -> Result[list[Issue]]:
        """Les memes tasks, chacune portant ses bloqueurs et leur etat.

        Une requete par task : le point d'entree qui liste les sous-issues ne
        dit rien des dependances, et decider sans elles reviendrait a lire
        « rien ne bloque ».
        """
        out = []
        for t in tasks:
            blockers = self.blocked_by(t.number)
            if blockers.failed:
                return blockers.recast()
            out.append(Issue(number=t.number, title=t.title, state=t.state,
                             labels=t.labels, body=t.body,
                             blocked_by=tuple(blockers.value)))
        return Result.of(out)

    def merged_prs(self, base: str) -> Result[list[Issue]]:
        """Les PR mergees sur `base`, les plus recemment touchees d'abord.

        Rendues telles quelles : laquelle declare fermer quelle issue est la
        convention de /code, pas une propriete de l'API, et la lire ici
        remettrait une regle de workflow dans un adaptateur. L'appelant
        filtre — voir `agentic_dev_loop.internals.tasks.first_closing`.

        Une liste illisible rend un echec, pas une liste vide : « l'API est
        en panne » et « rien n'a ete livre » menent a des decisions opposees.
        """
        return self._read(f"the merged pull requests on {base}",
                          "pulls", "-X", "GET",
                          "-f", "state=closed", "-f", f"base={base}",
                          "-f", "sort=updated", "-f", "direction=desc",
                          "-f", f"per_page={PER_PAGE}"
                          ).map(_merged)

    # --- l'API : ecrire ----------------------------------------------------

    def _write(self, what: str, method: str, path: str, *args: str) -> Result:
        """Une ecriture d'API. `path` est relatif au depot, comme `_read`."""
        repo = self.repo
        if repo.failed:
            return repo.recast()
        url = f"repos/{repo.value}/{path}"
        out = self._run("api", "-X", method, url, *args, check=False)
        if out.returncode != 0:
            return Result.halt(
                f"GitHub refused to {what} ({method} {url}):"
                f" {last_line(out.stderr)}. Nothing is retried and nothing is"
                f" rolled back here — a half-applied change is easier to"
                f" finish by hand than to guess at.")
        return Result.of(
            json.loads(out.stdout) if out.stdout.strip() else None)

    def _id(self, number: int) -> Result[int]:
        """L'identifiant interne d'une issue — ce que les liens demandent."""
        if number not in self._ids:
            got = self.issue(number)
            if got.failed:
                return got.recast()
        return Result.of(self._ids[number])

    def create_issue(self, title: str, body: str = "",
                     labels: tuple[str, ...] = ()) -> Result[Issue]:
        args = ["-f", f"title={title}", "-f", f"body={body}"]
        for label in labels:
            args += ["-f", f"labels[]={label}"]
        got = self._write(f"create the issue {title!r}", "POST", "issues",
                          *args)
        if got.failed:
            return got.recast()
        task = _issue(got.value)
        self._ids[task.number] = int(got.value["id"])
        return Result.of(task)

    def close_issue(self, number: int) -> Result[None]:
        """Ferme une issue.

        Le round s'en sert pour la post-condition d'une task : GitHub ne
        ferme une issue liee qu'au merge dans la branche par defaut, et la
        boucle merge ailleurs. `merged_prs` fournit la matiere de la
        preuve, cette methode en tire la consequence. La migration aussi.
        """
        return self._write(f"close #{number}", "PATCH",
                           f"issues/{number}", "-f", "state=closed")

    def set_body(self, number: int, body: str) -> Result[None]:
        return self._write(f"rewrite the body of #{number}", "PATCH",
                           f"issues/{number}", "-f", f"body={body}")

    def add_label(self, number: int, label: str) -> Result[None]:
        return self._write(f"label #{number} {label}", "POST",
                           f"issues/{number}/labels",
                           "-f", f"labels[]={label}")

    def remove_label(self, number: int, label: str) -> Result[None]:
        return self._write(f"remove {label} from #{number}", "DELETE",
                           f"issues/{number}/labels/{label}")

    def add_sub_issue(self, parent: int, child: int) -> Result[None]:
        child_id = self._id(child)
        if child_id.failed:
            return child_id.recast()
        return self._write(f"make #{child} a sub-issue of #{parent}", "POST",
                           f"issues/{parent}/sub_issues",
                           "-F", f"sub_issue_id={child_id.value}")

    def add_dependency(self, number: int, blocker: int) -> Result[None]:
        """Declare que `number` est bloquee par `blocker`."""
        blocker_id = self._id(blocker)
        if blocker_id.failed:
            return blocker_id.recast()
        return self._write(f"make #{number} blocked by #{blocker}", "POST",
                           f"issues/{number}/dependencies/blocked_by",
                           "-F", f"issue_id={blocker_id.value}")
