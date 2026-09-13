"""Les deux formes : ce qu'elles enchainent, et ou elles s'arretent.

Rien ici ne monte un vrai workflow — une forme se teste avec des etapes de
trois lignes, ce qui est la preuve qu'elle n'en connait aucun.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pipeline.core.domain.action import Action
from pipeline.core.domain.outcomes.result import Result, Status
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.execution.contract.settings import WorkflowConfig
from pipeline.core.execution.shapes.once import Once
from pipeline.core.execution.shapes.repeat import Repeat
from pipeline.core.runtime.monitoring import logbook


@dataclass
class Cfg(WorkflowConfig):
    """Une config de test : dry-run, donc aucune session ne part."""

    dry_run: bool = True

    def prompt_for(self, stage, extra):
        return f"prompt de /{stage.skill} {extra}".strip()


class State:
    """L'etat file entre les etapes."""

    def __init__(self):
        self.stages_done: list[str] = []
        self.seen: list[str] = []


def note(name, answer=None):
    """Une action qui note son passage et rend ce qu'on lui dit."""
    def do(ctx, st):
        st.seen.append(name)
        return answer if answer is not None else Result.of(None)
    return Action(name, do)


def run(shape, cfg, tmp_path):
    log = logbook.open_logbook("t", file=tmp_path / "run.log")
    return asyncio.run(shape.run(cfg, log, log_dir=tmp_path))


# --- once -------------------------------------------------------------------


def test_once_runs_every_step_in_the_order_of_the_plan(tmp_path):
    st = State()
    shape = Once(plan=lambda c: (note("a"), note("b"), note("c")),
                 state=lambda: st)
    out = run(shape, Cfg(workspace=None), tmp_path)
    assert not out.failed
    assert st.seen == ["a", "b", "c"]


def test_once_stops_at_the_first_step_that_fails(tmp_path):
    st = State()
    shape = Once(plan=lambda c: (note("a"), note("b", Result.halt("stop la")),
                                 note("c")),
                 state=lambda: st)
    out = run(shape, Cfg(workspace=None), tmp_path)
    assert out.status is Status.HALTED and out.reason == "stop la"
    assert st.seen == ["a", "b"], "l'etape d'apres ne doit pas partir"


def test_once_awaits_an_action_that_is_async(tmp_path):
    """Le choix d'une task ne rend la main a personne ; un rollover paie."""
    st = State()

    async def slowly(ctx, s):
        s.seen.append("async")
        return Result.of(None)

    shape = Once(plan=lambda c: (Action("async", slowly),), state=lambda: st)
    assert not run(shape, Cfg(workspace=None), tmp_path).failed
    assert st.seen == ["async"]


def test_once_mixes_a_paid_stage_and_a_local_action(tmp_path, monkeypatch):
    """La table melange les deux sortes, et la sequence ne les distingue pas."""
    from pipeline.core.runtime.filesystem.workspace import Workspace

    st = State()
    cfg = Cfg(workspace=Workspace(tmp_path))
    shape = Once(plan=lambda c: (StageSpec("paye", "sonnet", "low"),
                                 note("local")),
                 state=lambda: st,
                 extra=lambda step, ctx, s: "en plus")
    out = run(shape, cfg, tmp_path)
    assert not out.failed
    assert st.seen == ["local"]
    # dry-run : le stage n'appelle personne, il ecrit son prompt.
    written = (tmp_path / "01-paye.log").read_text(encoding="utf-8")
    assert "prompt de /paye en plus" in written


def test_once_renders_the_summary_of_a_run_that_finished(tmp_path):
    shape = Once(plan=lambda c: (), state=State,
                 summary=lambda cfg, st: "c'est fini")
    assert run(shape, Cfg(workspace=None), tmp_path).summary == "c'est fini"


# --- repeat -----------------------------------------------------------------


def test_repeat_spends_the_whole_budget_when_work_remains(tmp_path):
    turns = []

    async def unit(cfg, turn, log, log_dir, tally):
        turns.append(turn)
        return Result.of(True)

    shape = Repeat(unit=unit, budget=lambda c: 3)
    assert not run(shape, Cfg(workspace=None), tmp_path).failed
    assert turns == [1, 2, 3]


def test_repeat_stops_when_a_unit_says_nothing_is_left(tmp_path):
    turns = []

    async def unit(cfg, turn, log, log_dir, tally):
        turns.append(turn)
        return Result.of(turn < 2)

    shape = Repeat(unit=unit, budget=lambda c: 5, exhausted="plus rien")
    assert not run(shape, Cfg(workspace=None), tmp_path).failed
    assert turns == [1, 2], "un tour de plus rejouerait le meme constat"


def test_repeat_propagates_the_failure_that_stopped_a_unit(tmp_path):
    async def unit(cfg, turn, log, log_dir, tally):
        return Result.quota("fenetre epuisee") if turn == 2 else Result.of(True)

    out = run(Repeat(unit=unit, budget=lambda c: 5), Cfg(workspace=None),
              tmp_path)
    assert out.status is Status.QUOTA and out.reason == "fenetre epuisee"
