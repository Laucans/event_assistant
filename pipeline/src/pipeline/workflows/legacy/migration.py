"""Le markdown du pipeline, traduit une fois en issues.

Ce module existe pour etre supprime. Il porte les dernieres regex qui savent
lire `docs/ROADMAP.md` et `docs/current/CURRENT_MILESTONE.md`, le temps de la
commande `agent-loop migrate` — apres quoi ces fichiers n'existent plus et
personne n'a plus a savoir a quoi ressemblait un « **4.** » en gras.

Il rend un **plan**, pas des issues : une liste de `NewIssue` reliees par des
cles a nous (`r1`, `m`, `t4`, `h5`), parce que les numeros GitHub n'existent
pas encore au moment ou les liens se decident. `workflows.legacy.migrate`
remplace ensuite chaque cle par le numero qu'il vient de creer — ou de
retrouver.

Metier pur : ni disque, ni reseau. C'est ce qui permet de verifier le plan
sur des chaines, et donc de savoir ce que `--dry-run` imprimera sans rien
ecrire nulle part.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.workflows.agentic_dev_loop.internals.tasks import (
    AGENT, HUMAN, MILESTONE, ROADMAP)

# Les sections du milestone qui deviennent le corps de l'issue, dans cet
# ordre. Le reste n'y va pas : « Files & interfaces », « Edge cases » et
# « Verification » decrivaient un milestone dont les trois premieres tasks
# sont deja archivees, et les recopier ferait travailler /business-analyst
# contre un etat du depot qui n'existe plus.
MILESTONE_SECTIONS = ("Problem", "Goals / Non-goals", "Approach",
                      "Out of scope")

# Un titre d'issue se lit dans une liste : ce qui suit le tiret cadratin est
# la description, et elle vit dans le corps.
TITLE_MAX = 72


@dataclass(frozen=True)
class NewIssue:
    """Une issue a creer, et ce a quoi elle sera reliee.

    `parent` et `blocked_by` portent des cles de plan, jamais des numeros :
    tout ce qui est ici est decide avant le premier appel a GitHub.
    """

    key: str
    title: str
    body: str
    labels: tuple[str, ...]
    parent: str = ""
    blocked_by: tuple[str, ...] = field(default=())


def _title_of(text: str) -> str:
    """Le titre d'un item : ce qui precede le tiret cadratin, sinon le debut."""
    head = re.split(r"\s+—\s+", text, maxsplit=1)[0].strip()
    if len(head) <= TITLE_MAX:
        return head
    cut = head[:TITLE_MAX].rsplit(" ", 1)[0]
    return cut + "…"


def roadmap_items(text: str) -> list[NewIssue]:
    """Les items non coches de la roadmap, dans l'ordre, un par issue.

    Une marche ligne a ligne plutot qu'une regex : les items courent sur
    plusieurs lignes indentees, et un `- [x]` deja fait doit sortir du lot
    sans emporter la continuation du suivant.
    """
    items: list[tuple[str, list[str]]] = []
    section = ""
    current: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if line.startswith("## "):
            section, current = line[3:].strip(), None
        elif stripped.startswith("- [ ] "):
            current = [stripped[6:]]
            items.append((section, current))
        elif stripped.startswith("- ["):          # deja coche : on l'ignore
            current = None
        elif current is not None and stripped and line.startswith(" "):
            current.append(stripped)
        elif not stripped:
            current = None
    out = []
    for n, (section, parts) in enumerate(items, start=1):
        body = " ".join(parts)
        out.append(NewIssue(
            key=f"r{n}", title=_title_of(body), labels=(ROADMAP,),
            body=f"{body}\n\nFrom docs/ROADMAP.md, under \"{section}\"."))
    return out


def _sections(text: str) -> dict[str, str]:
    """Chaque section `##` du document, par son titre."""
    out: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{1,2}\s+\S", line):
            if name is not None:
                out[name] = "\n".join(lines).strip()
            name = line.lstrip("#").strip() if line.startswith("## ") else None
            lines = []
        elif name is not None:
            lines.append(line)
    if name is not None:
        out[name] = "\n".join(lines).strip()
    return out


def milestone_issue(text: str) -> NewIssue:
    """Le milestone en cours, reduit a ce qu'un stage a besoin de lire."""
    heading = re.search(r"^#\s+(?:Spec:\s*)?(.+?)\s*$", text, re.M)
    title = heading.group(1) if heading else "Current milestone"
    found = _sections(text)
    body = "\n\n".join(f"## {name}\n\n{found[name]}"
                       for name in MILESTONE_SECTIONS if found.get(name))
    return NewIssue(key="m", title=title, body=body, labels=(MILESTONE,))


def _blocks(text: str) -> list[tuple[str, str, str]]:
    """`(numero, tete, corps)` de chaque task de la section `# Tasks`."""
    section = re.search(r"^#\s+Tasks\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    out = []
    for block in re.split(r"^(?=\*\*\d+\.)",
                          section.group(1) if section else "", flags=re.M):
        number = re.match(r"^\*\*(\d+)\.", block)
        if not number:
            continue
        head, _, body = block.partition("\n\n")
        out.append((number.group(1), " ".join(head.split()), body.strip()))
    return out


def task_issues(text: str) -> list[NewIssue]:
    """Les tasks encore ouvertes, plus l'action humaine que l'une porte.

    Les tasks DONE ne sont pas migrees : elles sont archivees sous
    `docs/archives/`, et une issue fermee ouverte pour l'occasion ne
    raconterait rien que l'archive ne raconte deja.

    Le `_(needs you: ...)_` d'une task devient une issue `pipeline:human` a
    part entiere, dont la task depend. C'est tout ce qui reste de la porte
    humaine : une dependance comme une autre.
    """
    out: list[NewIssue] = []
    previous = ""
    for number, head, body in _blocks(text):
        if "DONE" in head:
            continue
        title = re.sub(r"^\d+\.\s*", "",
                       re.sub(r"\s+", " ", head.split("**")[1])).strip()
        blockers = [previous] if previous else []
        needs = re.search(r"needs you:\s*(.+?)\)_", head)
        if needs:
            human = f"h{number}"
            out.append(NewIssue(
                key=human, title=f"{title}: {needs.group(1).strip()}",
                labels=(HUMAN,), parent="m",
                body=f"{needs.group(1).strip()}\n\nHuman-only step of the"
                     f" task \"{title}\". The loop will not pick that task up"
                     f" until this issue is closed."))
            blockers.append(human)
        out.append(NewIssue(key=f"t{number}", title=title, body=body,
                            labels=(AGENT,), parent="m",
                            blocked_by=tuple(blockers)))
        previous = f"t{number}"
    return out


def plan(roadmap: str, milestone: str) -> list[NewIssue]:
    """Le plan complet, dans l'ordre ou il doit etre applique.

    Les parents avant les enfants, et un bloqueur avant ce qu'il bloque :
    poser un lien demande que les deux issues existent, donc l'ordre de cette
    liste est aussi celui des appels.

    Le milestone est rattache au **premier** item de roadmap. C'est la regle
    que /planner suit — « le premier item non coche » — donc c'est de celui-la
    que le milestone en cours descend. `--dry-run` imprime le rattachement :
    c'est un point ou un humain doit regarder plutot que faire confiance.
    """
    items = roadmap_items(roadmap)
    top = items[0].key if items else ""
    head = milestone_issue(milestone)
    return [*items,
            NewIssue(key=head.key, title=head.title, body=head.body,
                     labels=head.labels, parent=top),
            *task_issues(milestone)]
