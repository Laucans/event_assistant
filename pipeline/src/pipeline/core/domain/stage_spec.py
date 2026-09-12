"""Un stage : sa forme, les niveaux d'effort qu'un modele accepte, et ce qu'une
table de stages permet de demander.

**Le type, pas les instances.** Quels stages tourne un workflow, avec quel
modele et quel texte, est la definition de ce workflow et vit chez lui
(`workflows/<nom>/stages/`). Ce module dit seulement ce qu'un stage *est* —
ce qui permet a `execution/` de faire tourner n'importe lequel sans connaitre
aucun workflow.
"""

from __future__ import annotations

from dataclasses import dataclass

EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class StageSpec:
    """Un stage : le skill, ce qui le fait tourner, et ce sur quoi il ouvre.

    `lead` n'est rempli que pour le stage qui n'ouvre pas sur le skill dont
    il porte le nom : le stage `code` ouvre sur /tech-analyst et enchaine sur
    /code dans le meme processus, parce que le plan du tech-analyst n'est
    ecrit dans aucun fichier — un processus neuf le jetterait.

    `instructions` porte la prose propre au stage, celle qui s'ajoute au
    preambule. Elle est **dans l'entree de table** plutot que dans un
    registre a cote, parce qu'un registre indexe par nom de skill est une
    seconde liste a tenir d'accord avec la premiere : un stage renomme d'un
    cote perdait son texte de l'autre, en silence. Vide est une valeur
    normale — /create-test n'a pas de consignes propres.
    """

    skill: str
    model: str
    effort: str
    lead: str | None = None
    instructions: str = ""

    def __post_init__(self) -> None:
        if self.effort not in EFFORTS:
            raise ValueError(
                f"stage {self.skill!r}: effort {self.effort!r} is not in "
                f"{'|'.join(EFFORTS)}")

    @property
    def command(self) -> str:
        """La commande sur laquelle le prompt ouvre."""
        return self.lead or "/" + self.skill

    @property
    def label(self) -> str:
        """Comment le stage est nomme dans les journaux."""
        if self.lead:
            return f"{self.lead} -> /{self.skill}"
        return "/" + self.skill


def spec_of(skill: str, table: tuple[StageSpec, ...]) -> StageSpec | None:
    """L'entree de cette table que porte ce nom, ou None.

    Nommee plutot que supposee : `next()` sans defaut leve un `StopIteration`
    nu, et en lever un dans une methode async le transforme en
    `RuntimeError: coroutine raised StopIteration` — une forme qui ne dit rien
    d'une entree renommee dans la table, seule facon d'y arriver.
    """
    for spec in table:
        if spec.skill == skill:
            return spec
    return None


def names(table: tuple[StageSpec, ...]) -> str:
    """Les entrees de la table, pour un message d'erreur qui aide."""
    return " ".join(s.skill for s in table) or "(nothing)"
