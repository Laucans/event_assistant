"""Faire tourner un stage dans un round : filtrer, marquer, compter, arreter.

C'est l'orchestration, separee du design du round
(`workflows.agentic_dev_loop.flow`) parce qu'on ne les relit pas pour les
memes raisons : le round se lit pour comprendre le pipeline, ce fichier se lit
pour comprendre une panne — pourquoi un stage a ete saute, pourquoi il a ete
rejoue, pourquoi la boucle s'est arretee la.

Une classe plutot que des fermetures : le contexte etait capture par cloture
dans une fabrique, ce qui le rendait invisible depuis un test. Ici il est un
attribut, et un `StageRunner` se construit tout seul.
"""

from __future__ import annotations

from pipeline.execution import session
from pipeline.execution.context import Ctx, StagePolicy
from pipeline.domain.outcomes.result import Result
from pipeline.domain.stage_spec import StageSpec
from pipeline.runtime.monitoring.logbook import Logbook


class StageRunner:
    """Le lanceur de stages d'un round : un contexte, et ce qu'il en fait."""

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx

    @property
    def cfg(self) -> StagePolicy:
        return self.ctx.cfg

    @property
    def log(self) -> Logbook:
        return self.ctx.log

    def filtered(self, spec: StageSpec) -> bool:
        """True si `--stages` laisse celui-ci de cote — et le dit.

        Un saut silencieux est le classique « pourquoi rien ne s'est passe » :
        un run avec `--stages code` ne disait rien des trois stages qu'il
        laissait tomber, et le journal se lisait comme un pipeline plus court
        de trois stages qu'il ne l'est.
        """
        if self.cfg.enabled(spec):
            return False
        self.log(f"/{spec.skill} skipped — not in --stages ({self.cfg.stages})")
        return True

    async def run(self, spec: StageSpec, *, done: list[str], extra: str = "",
                  mark: bool = True) -> Result[None]:
        """Fait tourner un stage, au plus une fois par task, tous runs confondus.

        `done` est la liste des stages deja faits pour cette task — celle que
        le moteur persiste. Elle est lue pour sauter, et allongee pour marquer.

        `mark=False` pour le stage d'archivage : ce sont ses post-conditions
        qui disent s'il a marche, et le declarer fait avant de les verifier
        laisserait un archivage rate etre saute a chaque re-run.
        """
        if self.filtered(spec):
            return Result.of(None)
        if mark and spec.skill in done:
            self.log(f"/{spec.skill} already completed for this task —"
                     " skipping (--restart to force)")
            return Result.of(None)
        resolved = self.cfg.resolve(spec)
        # A partir d'ici chaque ligne nomme le stage qui l'a produite — c'est
        # ce qui rend un journal lisible quand une pr-review detachee y
        # entrelace sa propre sortie.
        ran = await session.run(
            resolved, self.cfg, round_no=self.ctx.round_no,
            task=self._task_key, extra=extra, log_dir=self.ctx.log_dir,
            log=self.log.bind(spec.skill), runner=self.ctx.runner)
        if ran.failed:
            return ran.recast()
        result = ran.value
        if result is not None:
            self.ctx.tally.add(spec.skill, result.cost, result.duration_ms,
                               result.usage)
            self.log(self.ctx.tally.running())
            if result.stopped:
                # Un stage qui repond AGENT_LOOP_STOP s'est arrete de
                # lui-meme : un resultat correct, et la raison est la sienne.
                return Result.halt(f"{result.stop_line} (/{spec.skill})")
        # Un dry-run n'execute rien : il ne peut pas declarer un stage fait.
        if mark and not self.cfg.dry_run:
            done.append(spec.skill)
        return Result.of(None)

    # La task en cours, posee par le round une fois qu'il l'a choisie. Elle
    # ne va que dans la colonne `task` du registre, d'ou le defaut vide
    # plutot qu'un argument de plus sur chaque appel.
    _task_key: str = ""

    def about(self, task_key: str) -> None:
        """Dit au lanceur sous quelle task facturer les stages qui suivent."""
        self._task_key = task_key
