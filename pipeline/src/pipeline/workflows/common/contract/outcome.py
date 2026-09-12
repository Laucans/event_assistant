"""Ce qu'un workflow rend a celui qui l'a lance.

Un `Result` sans valeur : ce qui interesse un point d'entree n'est pas ce que
le workflow a calcule mais comment il s'est termine — le code de sortie qu'il
propage, et la phrase qu'un humain lit. `summary` est ce qui s'ajoute au
`Result` du domaine : la ligne qu'un run reussi laisse derriere lui, la ou un
echec porte deja sa raison.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.domain.outcomes.result import Result, Status
from pipeline.runtime.monitoring.logbook import Logbook


@dataclass(frozen=True)
class WorkflowOutcome(Result[None]):
    """La fin d'un workflow, telle que le lanceur la lit."""

    summary: str = ""

    @classmethod
    def done(cls, summary: str = "") -> "WorkflowOutcome":
        """Le workflow est alle au bout."""
        return cls(summary=summary)

    @classmethod
    def of_result(cls, result: Result, summary: str = "") -> "WorkflowOutcome":
        """Le meme statut, porte par un resultat de workflow.

        C'est par ici que l'echec d'une porte, d'un stage ou d'une lecture
        d'API devient la fin du workflow : le statut et la raison traversent
        intacts, et seule la valeur — dont un lanceur ne fait rien — tombe.
        """
        return cls(status=result.status, reason=result.reason,
                   summary=summary)

    def report(self, log: Logbook) -> "WorkflowOutcome":
        """Dit la fin au niveau qu'elle merite, et se rend pour l'enchainer.

        Le niveau vient du statut et non d'un `if` par sorte : un arret
        volontaire est un resultat correct et ne se lit pas comme un
        avertissement, une panne de stage n'est pas un arret.
        """
        if self.status is not Status.OK:
            getattr(log, self.level)(f"{self.prefix} — {self.reason}")
        elif self.summary:
            log(self.summary)
        return self
