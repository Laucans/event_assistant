"""Une unite de travail, repetee jusqu'au budget ou jusqu'au premier arret.

La forme d'un workflow qui tourne sans personne devant : il ne vise pas une
cible, il consomme un budget. Ce que fait une unite est l'affaire du workflow
— la boucle y lit son tableau, reprend son etat, choisit sa task — et ce qui
est ici est la seule chose qui n'en depend pas : compter les tours, additionner
la depense, et savoir s'arreter.

Une unite rend `Result[bool]` : la valeur dit **s'il reste du travail**, et
c'est ce qui distingue « le budget est epuise » de « il n'y a plus rien a
faire ». Un echec est l'arret, avec la raison que l'unite a rendue.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.runtime.monitoring import metrics
from pipeline.core.runtime.monitoring.logbook import Logbook


@dataclass(frozen=True)
class Repeat:
    """`unit`, repetee `budget(cfg)` fois au plus."""

    unit: Callable[..., Awaitable[Result[bool]]]
    budget: Callable[[Any], int]
    # Comment un tour se nomme dans le journal, et comment le total s'annonce.
    label: str = "round"
    tally_as: str = "loop"
    # Ce qui se dit quand une unite repond qu'il ne reste rien a faire.
    exhausted: str = ""
    summary: Callable[[Any, Path], str] | None = None

    async def run(self, cfg: Any, log: Logbook, *,
                  log_dir: Path) -> WorkflowOutcome:
        """Les tours, jusqu'au budget ou jusqu'au premier qui s'arrete."""
        tally = metrics.Tally()
        stopped: Result[bool] | None = None
        budget = self.budget(cfg)
        try:
            for turn in range(1, budget + 1):
                log(f"{self.label} {turn}/{budget}")
                more = await self.unit(cfg, turn, log, log_dir, tally)
                if more.failed:
                    stopped = more
                    break
                if not more.value:
                    if self.exhausted:
                        log(self.exhausted)
                    break
        finally:
            if tally.stages:
                log(tally.summary(self.tally_as))
        if stopped is not None:
            return WorkflowOutcome.of_result(stopped)
        said = self.summary(cfg, log_dir) if self.summary else ""
        return WorkflowOutcome.done(said)
