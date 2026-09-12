"""Un stage : sa forme, et les niveaux d'effort qu'un modele accepte."""

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
    """

    skill: str
    model: str
    effort: str
    lead: str | None = None

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
