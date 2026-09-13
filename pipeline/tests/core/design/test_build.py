"""Un blueprint monte un objet que le lanceur ne distingue pas d'un workflow ecrit."""

import asyncio
from pathlib import Path

from pipeline.core import design
from pipeline.core.domain.outcomes.result import Result, Status
from pipeline.core.execution.contract import workflow as contract
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.execution.contract.gate import Check
from pipeline.core.execution.contract.settings import WorkflowConfig
from pipeline.core.runtime.monitoring import logbook


class Shape:
    """Une forme sur papier : ce qu'elle rend, et si elle a tourne."""

    def __init__(self, answer=None):
        self.answer = answer or WorkflowOutcome.done("fait")
        self.ran = 0

    async def run(self, cfg, log, *, log_dir):
        self.ran += 1
        return self.answer


def build(tmp_path, **fields):
    shape = fields.pop("shape", None) or Shape()
    blueprint = design.Blueprint(name="t", config=WorkflowConfig, shape=shape,
                                 artifacts=lambda c: tmp_path, **fields)
    log = logbook.open_logbook("t", file=tmp_path / "run.log")
    return design.workflow(blueprint, WorkflowConfig(workspace=None), log), shape


def run(w):
    return asyncio.run(w.run())


def test_what_a_blueprint_builds_satisfies_the_contract(tmp_path):
    w, _ = build(tmp_path)
    assert isinstance(w, contract.Workflow)


def test_a_gate_that_fails_never_reaches_the_shape(tmp_path):
    """Toute la raison d'etre du preflight : ne rien depenser pour rien."""
    gate = Check("non", lambda cfg, log: Result.halt("pas aujourd'hui"))
    w, shape = build(tmp_path, gates=(gate,))
    out = run(w)
    assert out.status is Status.HALTED and out.reason == "pas aujourd'hui"
    assert shape.ran == 0


def test_the_gates_run_in_order_and_stop_at_the_first_failure(tmp_path):
    seen = []

    def gate(name, answer):
        def verify(cfg, log):
            seen.append(name)
            return answer
        return Check(name, verify)

    w, _ = build(tmp_path, gates=(gate("a", Result.of(None)),
                                  gate("b", Result.halt("non")),
                                  gate("c", Result.of(None))))
    run(w)
    assert seen == ["a", "b"]


def test_announce_speaks_only_once_every_gate_has_passed(tmp_path):
    said = []
    w, _ = build(tmp_path, gates=(Check("non", lambda c, l: Result.halt("x")),),
                 announce=lambda cfg, log: said.append("annonce"))
    run(w)
    assert said == [], "annoncer un run qui ne part pas serait un mensonge"

    w, _ = build(tmp_path, announce=lambda cfg, log: said.append("annonce"))
    run(w)
    assert said == ["annonce"]


def test_no_obtained_is_a_valid_declaration(tmp_path):
    """Vide se dit par un champ absent, plus par une classe vide."""
    w, _ = build(tmp_path)
    assert not run(w).failed


def test_obtained_is_not_verified_after_a_shape_that_failed(tmp_path):
    """Un second message, moins juste que le premier, n'aide personne."""
    seen = []

    def obtained(cfg, log, outcome):
        seen.append(outcome)
        return Result.of(None)

    w, _ = build(tmp_path, shape=Shape(WorkflowOutcome.of_result(
        Result.fail("le travail a casse"))), obtained=obtained)
    out = run(w)
    assert out.reason == "le travail a casse"
    assert seen == []


def test_obtained_can_fail_a_run_whose_shape_succeeded(tmp_path):
    w, _ = build(tmp_path,
                 obtained=lambda cfg, log, outcome: Result.halt("pas livre"))
    out = run(w)
    assert out.status is Status.HALTED and out.reason == "pas livre"
