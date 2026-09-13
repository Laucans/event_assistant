"""Le contrat, verifie sur les workflows qui existent vraiment.

`tests/core/execution/test_contract.py` tient ce que `sequence()` promet,
avec des doubles. Ici c'est l'autre moitie : les deux implementeurs exposent
bien les quatre attributs et les deux methodes, ce que
`isinstance(w, contract.Workflow)` sait dire puisque le `Protocol` est
`runtime_checkable`.
"""

import pathlib

import pytest

from pipeline.core.execution.contract import workflow as contract
from pipeline.core.runtime.monitoring import logbook
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.agentic_dev_loop.workflow import AgenticDevLoop
from pipeline.workflows.pr_review.settings import ReviewConfig
from pipeline.workflows.pr_review.workflow import PrReview


def a_loop(log, tmp_path: pathlib.Path):
    return AgenticDevLoop(RunConfig(), log, tmp_path)


def a_review(log, tmp_path: pathlib.Path):
    return PrReview(ReviewConfig(pr="12", base="main_agent"), log)


@pytest.mark.parametrize("build", [a_loop, a_review], ids=["loop", "review"])
def test_every_workflow_satisfies_the_contract(build, tmp_path):
    """La forme promise par `how_to_design_a_workflow.md`, en assertion."""
    workflow = build(logbook.open_logbook("test"), tmp_path)
    assert isinstance(workflow, contract.Workflow)


@pytest.mark.parametrize("build", [a_loop, a_review], ids=["loop", "review"])
def test_every_workflow_carries_both_guards(build, tmp_path):
    """`sequence()` les appelle sans les construire : elles sont deja la."""
    workflow = build(logbook.open_logbook("test"), tmp_path)
    assert isinstance(workflow.preconditions, contract.Preconditions)
    assert isinstance(workflow.postconditions, contract.Postconditions)
