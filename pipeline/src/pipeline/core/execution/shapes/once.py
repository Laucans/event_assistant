"""Une sequence d'etapes, une fois.

La forme d'un workflow qui a une cible et s'arrete : une revue de PR, une
migration, un rapport. Il declare ses etapes, cette forme les enchaine et
rend au premier echec.

`plan` est une fonction de la config et non une table constante, parce que
toutes les tables ne sont pas constantes : celle du round l'est, celle de la
revue tire ses modeles de `--level` et des `PR_REVIEW_*`. Une fonction dit
les deux ; une constante n'aurait dit que la premiere, et c'est ce qui avait
laisse un workflow sans table du tout.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.core.execution import shapes
from pipeline.core.execution.context import Ctx
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.execution.stage_runner import StageRunner
from pipeline.core.execution.steps import run_sequence
from pipeline.core.runtime.monitoring import metrics
from pipeline.core.runtime.monitoring.logbook import Logbook


@contextlib.contextmanager
def _unguarded(cfg, state):
    """Le defaut : rien ne garde ce workflow, il part."""
    yield True


@dataclass(frozen=True)
class Once:
    """Les etapes de `plan`, dans l'ordre, jusqu'a la premiere qui echoue."""

    plan: Callable[[Any], tuple]
    state: Callable[[], Any] = dict
    # Le texte propre a une etape, ajoute au preambule que `prompt_for` monte.
    extra: Callable[[Any, Ctx, Any], str] | None = None
    # La ligne qu'un run reussi laisse derriere lui.
    summary: Callable[[Any, Any], str] | None = None
    # Comment le total s'annonce dans le journal.
    tally_as: str = "run"
    # Y a-t-il seulement quelque chose a faire ? Rend la raison de n'en rien
    # faire, ou la chaine vide pour continuer. **Un run qui n'a rien a faire
    # est un succes** : une PR en brouillon ou deja revue n'a rien a obtenir,
    # et l'echouer ferait echouer exactement les cas que les regles de saut
    # existent pour laisser passer. C'est aussi ou l'etat se remplit de ce que
    # les etapes liront.
    precheck: Callable[[Any, Logbook, Any], Any] | None = None
    # Au plus un a la fois. Rend False quand un autre run tient deja la cible :
    # deux hooks partis sur la meme PR la commenteraient deux fois.
    guard: Callable[[Any, Any], Any] = _unguarded
    # Ce qui se dit quand le garde est deja tenu.
    held: Callable[[Any, Any], str] | None = None
    # L'echec d'une etape qui n'arrete pas la sequence. Voir `run_sequence`.
    tolerate: Callable[[Any, Any], str | None] | None = None

    async def run(self, cfg: Any, log: Logbook, *,
                  log_dir: Path) -> WorkflowOutcome:
        """La sequence, une fois."""
        ctx = Ctx(cfg=cfg, log=log, log_dir=log_dir, round_no=1,
                  tally=metrics.Tally(), workspace=cfg.workspace)
        state = self.state()

        if self.precheck is not None:
            checked = self.precheck(cfg, log, state)
            if checked.failed:
                return WorkflowOutcome.of_result(checked)
            if checked.value:
                log(checked.value)
                return WorkflowOutcome.done(checked.value)

        with self.guard(cfg, state) as mine:
            if not mine:
                said = self.held(cfg, state) if self.held else "already running"
                log(said)
                return WorkflowOutcome.done(said)
            return await self._steps(ctx, state, cfg, log)

    async def _steps(self, ctx: Ctx, state, cfg, log) -> WorkflowOutcome:
        """Les etapes, une fois le garde tenu."""
        runner = StageRunner(ctx)
        try:
            ran = await run_sequence(
                self.plan(cfg), ctx=ctx, state=state,
                run=lambda step: shapes.perform(step, runner, ctx, state,
                                                extra=self.extra),
                log=log, excluded=runner.filtered, tolerate=self.tolerate)
        finally:
            # Une sequence qui s'arrete a quand meme coute de l'argent, et
            # c'est justement celle dont on veut le chiffre.
            if ctx.tally.stages:
                log(ctx.tally.summary(self.tally_as))
        if ran.failed:
            return WorkflowOutcome.of_result(ran)
        said = self.summary(cfg, state) if self.summary else ""
        return WorkflowOutcome.done(said)
