"""La revue consultative d'une PR, dans la forme que tout workflow a.

Meme fichier, meme forme que `agentic_dev_loop/workflow.py` : la config, le
journal, les deux gardes, et `run()` qui delegue a la sequence commune. Le
travail est dans `internals/`.

Elle ne charge aucun moteur de graphe : une revue est une sequence de deux
passes, pas un graphe, et l'exprimer comme un flow lui ferait payer 1,3 s
d'import pour rien.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pipeline.core.adapters.agent import AgentRunner
from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.core.execution.contract import workflow as contract
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.workflows.pr_review.internals import review
from pipeline.workflows.pr_review.postconditions import ReviewPostconditions
from pipeline.workflows.pr_review.preconditions import ReviewPreconditions
from pipeline.workflows.pr_review.settings import ReviewConfig


@dataclass
class PrReview:
    """Deux passes sur une PR, livrees sur la PR.

    Satisfait `contract.Workflow` sans en heriter, comme la boucle.

    `gh`, `runner` et `warn` sont les coutures : un test passe ses doubles,
    et le CLI branche `warn` sur stderr — le hook lance la revue **detachee**,
    donc c'est le seul canal qu'un appelant qui n'ouvre pas le fichier de log
    verra passer.
    """

    config: ReviewConfig
    log: Logbook
    gh: GitHub | None = None
    runner: AgentRunner | None = None
    warn: Callable[[str], None] | None = None
    preconditions: ReviewPreconditions = field(init=False)
    postconditions: ReviewPostconditions = field(init=False)

    def __post_init__(self) -> None:
        self.preconditions = ReviewPreconditions(self.config, self.log)
        self.postconditions = ReviewPostconditions(self.config, self.log)

    async def run(self) -> WorkflowOutcome:
        """Le workflow entier, dans l'ordre que le contrat impose."""
        return await contract.sequence(self)

    async def execute(self) -> WorkflowOutcome:
        """La revue, une fois les outils verifies."""
        return await review.run(self.config, self.log, gh=self.gh,
                                runner=self.runner, warn=self.warn)
