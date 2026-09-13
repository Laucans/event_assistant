"""La boucle sur les rounds : ce qui depense le budget d'un run.

`one_round` estampille chaque ligne `r<n>` et rend le total du round meme
quand il halte. Un round qui s'arrete a quand meme coute de l'argent, et
c'est justement celui dont on veut le chiffre.

Enchainer les rounds n'est plus ici : c'est la forme `Repeat` que le
blueprint declare, et elle ne fait que ce qui ne depend d'aucun workflow —
compter les tours, additionner la depense, savoir s'arreter. Ce module ne
porte plus que l'unite qu'elle repete.

Il n'y a plus d'import tardif ici. Le round etait un graphe, son moteur
coutait 1,6 s d'import, et ce module le chargeait dans un corps de fonction
pour que les chemins rapides ne le paient pas. Un round est maintenant une
sequence : `internals.round` s'importe comme n'importe quel module.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pipeline.core.adapters.store import resume
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring import metrics
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.internals import board, round as rnd
from pipeline.workflows.agentic_dev_loop.internals.state import RoundState
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.adapters import hub


def _resume_point(cfg: RunConfig, here: board.Board, log: Logbook
                  ) -> Result[dict | None]:
    """L'etat qu'un round reprend, ou None s'il part du haut.

    Decide avant qu'aucune machinerie ne soit montee : un etat illisible doit
    arreter le round tant que c'est encore gratuit, pas une fois qu'une
    session est partie. Pose `here.resuming` en passant.
    """
    if cfg.restart:
        log("--restart — forgetting the completed stages for this task")
        if not cfg.dry_run:
            resume.clear(cfg.workspace.state)
        return Result.of(None)

    known_task, flow_id = resume.read_pointer(cfg.workspace.state)
    pending = here.find(known_task) if flow_id else None
    if pending is None:
        return Result.of(None)
    read = resume.load(flow_id, cfg.workspace.flow_db)
    if read.failed:
        return read.recast()
    done = list(read.value.get("stages_done") or [])
    # Une task fermee dont aucun stage n'est enregistre est un pointeur
    # perime, pas un round a finir : la reprendre repayerait les trois
    # stages d'une task deja livree.
    if not (pending.open or done):
        return Result.of(None)
    log(f"resuming task {pending.ref} — already completed:"
        f" {' '.join(done) if done else '(nothing yet)'}")
    here.resuming = pending
    return Result.of(read.value)


def _account(cfg: RunConfig, st: RoundState, ctx, round_no: int,
             log: Logbook, run_tally: "metrics.Tally | None") -> None:
    """Ce qu'un round laisse derriere, qu'il aille au bout ou non.

    Appele dans un `finally` : un round qui s'arrete a quand meme coute de
    l'argent, et c'est justement celui dont on veut le chiffre.
    """
    if not cfg.dry_run and st.task_key:
        resume.write_pointer(st.task_key, st.id, cfg.workspace.state)
    if ctx.tally.stages:
        log(ctx.tally.summary(f"round {round_no}"))
    if run_tally is not None:
        run_tally.merge(ctx.tally)


def _after_rollover(here: board.Board) -> Result[bool]:
    """Reste-t-il de quoi travailler apres le passage du planner ?

    Continuer n'a de sens que si le planner a ouvert une task : sinon les
    rounds restants rejoueraient le meme constat, en payant un round a
    chaque fois. Le tableau est relu — c'est justement ce que le
    planner vient de changer.
    """
    return board.read(here.gh).map(lambda after: bool(after.open_agents))


async def one_round(cfg: RunConfig, round_no: int, log: Logbook, log_dir: Path,
                    run_tally: "metrics.Tally | None" = None) -> Result[bool]:
    """Un round.

    La valeur dit s'il reste du travail : True quand une task s'est fermee,
    False quand le rollover n'a rien ouvert. Un echec est l'arret du round,
    avec la raison que l'etape a rendue.
    """
    # Every line this round produces is stamped `r<n>`, so a journal that
    # interleaves rounds — or a terminal that interleaves a detached
    # pr-review — stays attributable.
    log = log.bind(f"r{round_no}")

    # Le tableau est lu ici, une fois : le round le recoit dans son contexte
    # plutot que de le relire, et la cle de reprise est le numero d'issue.
    read = board.read(hub.gh(cfg.workspace))
    if read.failed:
        return read.recast()
    here = read.value
    resuming = _resume_point(cfg, here, log)
    if resuming.failed:
        return resuming.recast()
    # `--restart` ne vaut que pour le premier round : les suivants reprennent
    # ce que celui-ci vient d'ecrire. C'etait la seule ligne que la boucle sur
    # les rounds avait a savoir de son unite.
    cfg.restart = False

    ctx = rnd.RoundCtx(cfg=cfg, log=log, log_dir=log_dir, round_no=round_no,
                       tally=metrics.Tally(), board=here,
                       workspace=cfg.workspace)
    # L'etat repris tel quel, ou un etat neuf sous un identifiant neuf. C'est
    # le seul endroit qui le fabrique : le moteur le faisait avant, et son
    # identifiant est ce que le pointeur de reprise designe.
    st = (RoundState(**resuming.value) if resuming.value
          else RoundState(id=uuid.uuid4().hex))

    def save() -> None:
        """L'etat apres une etape. Un dry-run lit le magasin, il n'ecrit pas —
        sinon la prevision detruirait le point de reprise qu'elle decrit."""
        if not cfg.dry_run:
            resume.save(st.id, st.stages_done[-1] if st.stages_done else "",
                        st.model_dump(), cfg.workspace.flow_db)

    try:
        ran = await rnd.run(ctx, st, save=save)
    finally:
        _account(cfg, st, ctx, round_no, log, run_tally)
    if ran.failed:
        return ran.recast()

    if st.rollover:
        return _after_rollover(here)
    # The task is closed: the resume point has nothing left to describe.
    if not cfg.dry_run:
        resume.clear(cfg.workspace.state)
    log(f"round {round_no} done — issue #{st.task_num} closed")
    return Result.of(True)
