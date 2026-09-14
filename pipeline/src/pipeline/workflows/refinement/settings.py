"""Ce qui varie d'un raffinage a l'autre, et la politique qu'il applique.

Ce qui est commun a toute config de workflow vient de `WorkflowConfig`. Ce
qui reste ici est ce que le raffinage seul connait : l'issue, le contexte du
round, et le modele de chacune des sessions qu'un round peut payer — les six
de la table, et l'exploration qui les precede. Les defauts d'environnement
sont lus par le point d'entree, pas ici.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pipeline.core.adapters.store import ledger
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.execution.contract.settings import WorkflowConfig


# `kw_only` pour la meme raison que la revue : `issue` n'a pas de defaut, et
# un champ sans defaut ne peut pas suivre les champs defautes du parent.
@dataclass(kw_only=True)
class RefinementConfig(WorkflowConfig):
    """Ce qui varie d'un round de raffinage a l'autre."""

    issue: int
    context: str = ""
    force: bool = False
    goal_model: str = "sonnet"
    goal_effort: str = "high"
    technical_model: str = "sonnet"
    technical_effort: str = "high"
    criteria_model: str = "sonnet"
    criteria_effort: str = "high"
    rules_model: str = "sonnet"
    rules_effort: str = "high"
    plan_model: str = "sonnet"
    plan_effort: str = "high"
    router_model: str = "sonnet"
    router_effort: str = "low"
    # L'exploration qui precede la sequence. Sonnet a dessein : elle lit et
    # elle condense contre des documents qu'on lui a deja colles, ce n'est pas
    # un probleme de raisonnement.
    explore_model: str = "sonnet"
    explore_effort: str = "high"
    # Le round courant, pose par le precontrole : il nomme les artefacts et
    # la ligne de registre.
    round_no: int = 0
    # Un raffinage lance par un hook tourne detache : stderr est le seul
    # canal qu'un appelant qui n'ouvre pas le fichier de log verra passer.
    warn: Callable[[str], None] | None = None

    @property
    def handle(self) -> str:
        """Le nom de fichier que cette issue porte sur le disque."""
        return str(self.issue)

    def prompt_for(self, stage: StageSpec, extra: str) -> str:
        """Le prompt d'un stage **est** son texte."""
        return extra

    def artifact_tag(self, round_no: int) -> str:
        """Les artefacts d'un raffinage portent le numero de son round."""
        return f"r{self.round_no or round_no:02d}"

    def record(self, stage: StageSpec, result, *, round_no: int, task: str,
               outcome: str) -> None:
        """La ligne du registre des raffinages."""
        ledger.append(
            self.workspace.refinement_ledger, run_id=self.run_id,
            round_no=self.round_no or round_no, task=f"#{self.issue}",
            stage=stage.skill,
            cache_read=result.usage.get("cache_read_input_tokens"),
            cache_write=result.usage.get("cache_creation_input_tokens"),
            outcome=outcome,
            **result.ledger_fields(model=stage.model, effort=stage.effort))
