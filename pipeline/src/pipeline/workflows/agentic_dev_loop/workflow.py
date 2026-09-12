"""La boucle de developpement agentique, dans la forme que tout workflow a.

Ce fichier est court, et c'est le but : ce qu'il porte est le contrat — la
config, le journal, les deux gardes, et `run()` qui delegue a la sequence
commune. Le travail est dans `internals/`, ou il n'a pas a ressembler a autre
chose.

L'import du round est tardif, dans le corps d'`execute()` : le moteur de
graphe coute ~1,3 s d'import et tire 2331 modules. Importer ce fichier ne
doit pas le payer — `--status`, `--costs` et le preflight ne le chargent
jamais, et c'est ce qui les laisse repondre en quelques dizaines de
millisecondes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pipeline.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.postconditions import (
    LoopPostconditions)
from pipeline.workflows.agentic_dev_loop.preconditions import (
    LoopPreconditions)
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.common.contract import workflow as contract
from pipeline.workflows.common.contract.outcome import WorkflowOutcome


@dataclass
class AgenticDevLoop:
    """business-analyst -> code -> create-test, autant de fois que le budget.

    Satisfait `contract.Workflow` sans en heriter : les quatre membres du
    Protocol sont la, et `run()` delegue a la sequence commune.
    """

    config: RunConfig
    log: Logbook
    log_dir: Path
    preconditions: LoopPreconditions = field(init=False)
    postconditions: LoopPostconditions = field(init=False)

    def __post_init__(self) -> None:
        self.preconditions = LoopPreconditions(self.config, self.log)
        self.postconditions = LoopPostconditions(self.config, self.log)

    async def run(self) -> WorkflowOutcome:
        """Le workflow entier, dans l'ordre que le contrat impose."""
        return await contract.sequence(self)

    async def execute(self) -> WorkflowOutcome:
        """Les rounds, une fois le preflight passe."""
        # Import tardif : c'est ici, et nulle part avant, que le moteur de
        # graphe est charge.
        from pipeline.workflows.agentic_dev_loop.internals import loop

        return await loop.run_rounds(self.config, self.log, self.log_dir)
