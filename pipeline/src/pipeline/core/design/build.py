"""Un `Blueprint` devient un objet que le lanceur appelle.

Les trois classes d'emballage que chaque workflow recopiait, ecrites une
fois : celle qui parcourt les portes, celle qui verifie ce qui devait etre
obtenu, et celle qui porte les six membres du contrat.

Ce qu'elles ne font pas : decider. Elles n'ont ni politique ni valeur par
defaut au-dela de « pas de porte » et « rien a verifier apres » — tout le
reste vient du blueprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.core.design.blueprint import Blueprint
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.execution.contract import workflow as contract
from pipeline.core.execution.contract.gate import verify_all
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.runtime.monitoring.logbook import Logbook


@dataclass
class Gates:
    """Les portes du blueprint, dans la forme que le contrat appelle."""

    blueprint: Blueprint
    cfg: Any
    log: Logbook

    def verify(self) -> Result[None]:
        """Rend la premiere condition qui empeche ce workflow de tourner."""
        got = verify_all(self.blueprint.gates, self.cfg, self.log)
        if got.failed:
            return got
        if self.blueprint.announce is not None:
            self.blueprint.announce(self.cfg, self.log)
        return Result.of(None)


@dataclass
class Obtained:
    """Ce que le blueprint dit devoir avoir obtenu. Rien, le plus souvent."""

    blueprint: Blueprint
    cfg: Any
    log: Logbook

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        if self.blueprint.obtained is None:
            return Result.of(None)
        return self.blueprint.obtained(self.cfg, self.log, outcome)


@dataclass
class Built:
    """Un workflow declare, dans la forme que `contract.Workflow` decrit."""

    blueprint: Blueprint
    config: Any
    log: Logbook
    preconditions: Gates = field(init=False)
    postconditions: Obtained = field(init=False)

    def __post_init__(self) -> None:
        self.preconditions = Gates(self.blueprint, self.config, self.log)
        self.postconditions = Obtained(self.blueprint, self.config, self.log)

    async def run(self) -> WorkflowOutcome:
        """Le workflow entier, dans l'ordre que le contrat impose."""
        return await contract.sequence(self)

    async def execute(self) -> WorkflowOutcome:
        """La forme du blueprint, une fois le preflight passe."""
        return await self.blueprint.shape.run(
            self.config, self.log,
            log_dir=self.blueprint.artifacts(self.config))


def workflow(blueprint: Blueprint, config: Any, log: Logbook) -> Built:
    """L'objet que le lanceur lance, monte depuis la declaration."""
    return Built(blueprint, config, log)
