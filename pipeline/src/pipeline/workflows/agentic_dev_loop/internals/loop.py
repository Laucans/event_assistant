"""La boucle sur les rounds : ce qui depense le budget d'un run.

Un Flow decrit un graphe, pas une repetition. Les rounds sont donc du Python
ordinaire ici, autour de `flow` — et c'est aussi ce qui permet de
faire tourner un round seul dans un test sans monter un run entier.

Deux niveaux, et la separation compte pour le journal : `one_round` estampille
chaque ligne `r<n>` et rend le total du round meme quand il halte, `run`
enchaine et rend le total du run. Un round qui s'arrete a quand meme coute de
l'argent, et c'est justement celui dont on veut le chiffre.

L'import du round est tardif, dans le corps : le moteur coute ~1,3 s d'import
et les chemins rapides ne doivent pas le payer.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.adapters.store import resume
from pipeline.domain.outcomes.result import Result
from pipeline.runtime.monitoring import metrics
from pipeline.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.internals import board
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.common.contract.outcome import WorkflowOutcome
from pipeline.workflows.common.utils import hub


def _resume_point(cfg: RunConfig, here: board.Board, log: Logbook
                  ) -> Result[dict | None]:
    """Ce qu'un round reprend, ou None s'il part du haut.

    Decide avant qu'aucune machinerie ne soit montee : un etat illisible doit
    arreter le round tant que c'est encore gratuit, pas une fois que le flow
    tient le meme magasin ouvert. Pose `here.resuming` en passant.
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
    read = resume.stages_done(flow_id, cfg.workspace.flow_db)
    if read.failed:
        return read.recast()
    done = read.value
    # Une task fermee dont aucun stage n'est enregistre est un pointeur
    # perime, pas un round a finir : la reprendre repayerait les trois
    # stages d'une task deja livree.
    if not (pending.open or done):
        return Result.of(None)
    log(f"resuming task {pending.ref} — already completed:"
        f" {' '.join(done) if done else '(nothing yet)'}")
    here.resuming = pending
    return Result.of({"id": flow_id})


def _account(cfg: RunConfig, flow, ctx, round_no: int, log: Logbook,
             run_tally: "metrics.Tally | None") -> None:
    """Ce qu'un round laisse derriere, qu'il aille au bout ou non.

    Appele dans un `finally` : un round qui s'arrete a quand meme coute de
    l'argent, et c'est justement celui dont on veut le chiffre.
    """
    st = flow.state
    if not cfg.dry_run and st.task_key:
        resume.write_pointer(st.task_key, st.id, cfg.workspace.state)
    if ctx.tally.stages:
        log(ctx.tally.summary(f"round {round_no}"))
    if run_tally is not None:
        run_tally.merge(ctx.tally)


def _after_rollover(here: board.Board) -> Result[bool]:
    """Reste-t-il de quoi travailler apres le passage du planner ?

    Continuer n'a de sens que si le planner a ouvert une task : sinon les
    rounds restants rejoueraient le meme constat, en payant un kickoff de
    flow a chaque fois. Le tableau est relu — c'est justement ce que le
    planner vient de changer.
    """
    return board.read(here.gh).map(lambda after: bool(after.open_agents))


async def one_round(cfg: RunConfig, round_no: int, log: Logbook, log_dir: Path,
                    run_tally: "metrics.Tally | None" = None) -> Result[bool]:
    """Un round.

    La valeur dit s'il reste du travail : True quand une task s'est fermee,
    False quand le rollover n'a rien ouvert. Un echec est l'arret du round,
    avec la raison qu'un noeud a enregistree.
    """
    # Import tardif : c'est ici, et nulle part avant, que le moteur est charge.
    from pipeline.workflows.agentic_dev_loop.internals.flow import (
        RoundCtx, build_flow)

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

    ctx = RoundCtx(cfg=cfg, log=log, log_dir=log_dir, round_no=round_no,
                   tally=metrics.Tally(), board=here,
                   workspace=cfg.workspace)
    flow = build_flow(ctx)()
    try:
        await flow.kickoff_async(inputs=resuming.value)
    finally:
        _account(cfg, flow, ctx, round_no, log, run_tally)

    # Un noeud qui s'est arrete l'a enregistre dans l'etat : le moteur, lui,
    # rend la main normalement. C'est ici qu'un arret redevient un echec.
    if flow.state.stopped:
        return flow.state.halt.recast()

    if flow.state.rollover:
        return _after_rollover(here)
    # The task is closed: the resume point has nothing left to describe.
    if not cfg.dry_run:
        resume.clear(cfg.workspace.state)
    log(f"round {round_no} done — issue #{flow.state.task_num} closed")
    return Result.of(True)


async def run_rounds(cfg: RunConfig, log: Logbook,
                     log_dir: Path) -> WorkflowOutcome:
    """Les rounds, jusqu'au budget ou jusqu'au premier qui s'arrete.

    Le preflight n'est plus ici : c'est la precondition du workflow, et la
    sequence du contrat la passe avant d'appeler ceci. Ce module ne fait plus
    que ce que son nom dit — repeter des rounds.
    """
    tally = metrics.Tally()
    stopped: Result[bool] | None = None
    try:
        for round_no in range(1, cfg.max_rounds + 1):
            log(f"round {round_no}/{cfg.max_rounds}")
            more = await one_round(cfg, round_no, log, log_dir, tally)
            cfg.restart = False
            if more.failed:
                stopped = more
                break
            if not more.value:
                log("nothing left to open — stopping rather than replaying"
                    " the rollover")
                break
    finally:
        if tally.stages:
            log(tally.summary("loop"))
    if stopped is not None:
        return WorkflowOutcome.of_result(stopped)
    return WorkflowOutcome.done(
        f"loop finished — logs in {cfg.workspace.rel(log_dir)}")
