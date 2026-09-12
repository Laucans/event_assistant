"""Ce que l'execution tient pendant un stage, et ce qu'elle attend d'un workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pipeline.adapters.agent import AgentRunner
from pipeline.domain.stage_spec import StageSpec
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.runtime.monitoring import metrics
from pipeline.runtime.monitoring.logbook import Logbook


class StagePolicy(Protocol):
    """Ce que l'execution demande a un workflow pour lancer un stage."""

    run_id: str
    dry_run: bool
    verbose: bool
    permission_mode: str
    heartbeat_s: float
    stages: str
    workspace: Workspace

    def enabled(self, stage: StageSpec) -> bool: ...

    def resolve(self, stage: StageSpec) -> StageSpec: ...

    def prompt_for(self, stage: StageSpec, extra: str) -> str: ...


@dataclass
class Ctx:
    """Ce qu'un round doit savoir et qui n'est pas persiste."""

    cfg: StagePolicy
    log: Logbook
    log_dir: Path
    round_no: int
    tally: metrics.Tally = field(default_factory=metrics.Tally)
    # Le moteur d'agent des stages de ce round ; None laisse `session.run`
    # prendre celui par defaut.
    runner: AgentRunner | None = None
    workspace: Workspace = field(default_factory=Workspace.here)
