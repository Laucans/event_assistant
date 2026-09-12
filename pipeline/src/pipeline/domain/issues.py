"""Ce qu'est une issue, et rien de ce qu'un workflow en fait.

Le suivi du travail vit dans les issues GitHub. Ce module en porte la
**forme** — un numero, un titre, un etat, des etiquettes, un corps, des
bloqueurs — et les seules questions qu'on peut lui poser sans savoir a quoi
elle sert : est-elle ouverte, porte-t-elle cette etiquette, comment la nomme
un message.

**Le vocabulaire, pas la definition.** Ce qui fait d'une issue une « task
prete a tourner » — les etiquettes du suivi et les regles qui choisissent la
suivante — est la definition d'un workflow, et vit chez lui, dans son
`internals/tasks.py`. La separation est ce qui autorise
`adapters.shell.github` a rendre des `Issue` : un adaptateur deserialise, il
ne decide pas de ce qu'une etiquette *signifie*.

Metier pur : ni I/O, ni subprocess, ni bibliotheque externe.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """Une issue GitHub, vue par le paquet.

    Le meme type sert pour un item de roadmap, un milestone, une task, une
    action humaine et une PR : ce qui les distingue est une etiquette, pas
    une classe. C'est ce qui permet a `blocked_by` de porter des issues de
    n'importe quelle sorte — une dependance ne demande pas ce qu'elle bloque.

    `blocked_by` porte les bloqueurs **avec leur etat** : savoir qu'une issue
    est bloquee ne suffit pas, il faut savoir si le bloqueur est encore
    ouvert.
    """

    number: int
    title: str = ""
    state: str = "open"
    labels: tuple[str, ...] = ()
    body: str = ""
    blocked_by: tuple["Issue", ...] = ()

    @property
    def key(self) -> str:
        """L'identite de l'issue pour l'etat de reprise : son numero.

        C'etait `<num>|<titre>` du temps du markdown, ou rien d'autre ne
        designait une task de facon stable. Un numero d'issue, lui, ne change
        pas quand on reecrit le titre.
        """
        return str(self.number)

    @property
    def ref(self) -> str:
        return f"#{self.number}"

    @property
    def open(self) -> bool:
        return self.state != "closed"

    @property
    def closed(self) -> bool:
        return self.state == "closed"

    def has(self, label: str) -> bool:
        return label in self.labels
