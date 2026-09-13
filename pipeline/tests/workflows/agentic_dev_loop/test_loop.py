"""La boucle sur les rounds : quand elle continue, et quand elle s'arrete.

Le shell `break`ait sur un rollover sans entree planner
(`agent-loop.sh:566`). La version Python jetait la valeur de retour de
`one_round`, donc un milestone entierement termine faisait tourner MAX_ROUNDS
kickoffs de flow identiques, en repetant les deux memes lignes.
"""

import asyncio

import pytest
from conftest import milestone

from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.core.domain.outcomes.result import Result
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.agentic_dev_loop.internals import loop as workflow_loop


@pytest.fixture
def local(tmp_path):
    """Ce que la boucle ecrit sur ce disque, deporte dans un tmp_path."""
    return Workspace(tmp_path)


def spend(cfg, log_dir, answers):
    """Fait tourner `run_rounds` avec un `one_round` scripte.

    Rend `(rounds vus, le double)`. Le preflight n'est plus ici a ecarter :
    c'est la precondition du workflow, et `run_rounds` ne fait plus que
    repeter des rounds.
    """
    seen = []

    async def one(cfg_, round_no, log, dir_, tally=None):
        seen.append(round_no)
        return answers

    return seen, one


def test_the_loop_stops_as_soon_as_a_round_says_nothing_is_left(
        tmp_path, monkeypatch):
    seen, one = spend(None, None, Result.of(False))
    monkeypatch.setattr(workflow_loop, "one_round", one)
    asyncio.run(workflow_loop.run_rounds(
        RunConfig(max_rounds=3, workspace=Workspace(tmp_path)),
        logbook.null(), tmp_path))
    assert seen == [1], "la boucle a rejoue un round qui ne pouvait rien ouvrir"


def test_the_loop_spends_its_budget_while_rounds_keep_closing_tasks(
        tmp_path, monkeypatch):
    seen, one = spend(None, None, Result.of(True))
    monkeypatch.setattr(workflow_loop, "one_round", one)
    outcome = asyncio.run(workflow_loop.run_rounds(
        RunConfig(max_rounds=3, workspace=Workspace(tmp_path)),
        logbook.null(), tmp_path))
    assert seen == [1, 2, 3]
    assert outcome.ok and "loop finished" in outcome.summary


def test_a_round_that_stops_ends_the_run_and_carries_its_reason(
        tmp_path, monkeypatch):
    """Un round qui s'arrete n'en laisse pas partir un second.

    Chaque round restant coutait trois sessions payantes : c'est ce que la
    valeur de retour est la pour empecher, et elle porte desormais la raison
    jusqu'au point d'entree.
    """
    seen, one = spend(None, None, Result.halt("l'arbre est sale"))
    monkeypatch.setattr(workflow_loop, "one_round", one)
    outcome = asyncio.run(workflow_loop.run_rounds(
        RunConfig(max_rounds=3, workspace=Workspace(tmp_path)),
        logbook.null(), tmp_path))
    assert seen == [1]
    assert outcome.failed and outcome.reason == "l'arbre est sale"
    assert outcome.exit_code == 1


def test_the_round_context_carries_the_workspace_of_its_config(
        local, hub, monkeypatch, tmp_path):
    """Le workspace descend de la config jusqu'au contexte du round."""
    from pipeline.workflows.agentic_dev_loop.internals import round as flow

    number, numbers = milestone(hub, ready=(0,), tasks=("Une task",))
    hub.close(numbers[0])
    ailleurs = Workspace(tmp_path / "un-autre-depot")
    seen = []
    real = flow.RoundCtx
    monkeypatch.setattr(flow, "RoundCtx",
                        lambda **kw: (seen.append(kw["workspace"]),
                                      real(**kw))[1])
    asyncio.run(workflow_loop.one_round(
        RunConfig(max_rounds=1, run_id="test", workspace=ailleurs), 1,
        logbook.null(), local.root))
    assert seen == [ailleurs]


def test_a_rollover_round_that_opened_nothing_reports_it(local, hub):
    """Le round lui-meme : c'est lui qui sait qu'il n'y a plus rien a ouvrir."""
    number, numbers = milestone(hub, ready=(0,), tasks=("Une task",))
    hub.close(numbers[0])
    # ROLLOVER est None par defaut : le noeud planner ne fait que le dire.
    more = asyncio.run(workflow_loop.one_round(
        RunConfig(max_rounds=1, run_id="test", workspace=local), 1,
        logbook.null(), local.root))
    assert more.ok and more.value is False


def test_a_rollover_that_opened_a_task_lets_the_loop_carry_on(local, hub,
                                                              monkeypatch):
    """Le tableau est relu apres le planner : c'est ce qu'il vient de changer."""
    number, numbers = milestone(hub, ready=(0,), tasks=("Une task",))
    hub.close(numbers[0])

    from pipeline.workflows.agentic_dev_loop import stages as table
    from pipeline.workflows.agentic_dev_loop.internals import tasks
    from pipeline.core.execution import session

    async def planner_opens_one(stage, cfg, **kw):
        hub.link(number, hub.add("Une nouvelle task", tasks.AGENT))
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", planner_opens_one)
    more = asyncio.run(workflow_loop.one_round(
        RunConfig(max_rounds=1, run_id="test", workspace=local,
                  rollover=table.StageSpec("planner", "opus", "high")),
        1, logbook.null(), local.root))
    assert more.ok and more.value is True


def test_the_resume_pointer_is_keyed_by_the_issue_number(local, hub,
                                                         monkeypatch):
    """Un titre reecrit changeait la cle et faisait repayer la task."""
    from pipeline.core.adapters.store import resume
    from pipeline.core.execution import session

    number, numbers = milestone(hub, ready=(0,), tasks=("Une task",))

    async def halting(stage, cfg, **kw):
        return Result.of(session.StageResult(
            "AGENT_LOOP_STOP: stop", 0.0, "s", None, "AGENT_LOOP_STOP: stop"))

    monkeypatch.setattr(session, "run", halting)
    stopped = asyncio.run(workflow_loop.one_round(
        RunConfig(max_rounds=1, run_id="test", workspace=local), 1,
        logbook.null(), local.root))
    assert stopped.failed
    assert resume.read_pointer(local.state)[0] == str(numbers[0])


def test_a_dry_run_with_restart_keeps_the_resume_point_it_describes(
        local, hub, monkeypatch, tmp_path):
    """Un dry-run prevoit, il ne detruit pas ce qu'il prevoit.

    Les deux autres ecritures du magasin dans `one_round` sont deja gardees
    par `dry_run` ; celle de `--restart` ne l'etait pas.
    """
    from pipeline.core.adapters.store import resume

    number, numbers = milestone(hub, ready=(0,), tasks=("Une task",))
    resume.write_pointer(str(numbers[0]), "un-flow", local.state)

    asyncio.run(workflow_loop.one_round(
        RunConfig(max_rounds=1, run_id="test", dry_run=True, restart=True,
                  workspace=local),
        1, logbook.null(), tmp_path))

    assert local.state.exists()
    assert resume.read_pointer(local.state) == (str(numbers[0]), "un-flow")
