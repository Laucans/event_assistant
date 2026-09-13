"""Le contrat : la sequence que tout workflow suit, et ce qu'elle garantit.

Rien ici ne monte un vrai workflow — le contrat se teste avec des doubles de
quinze lignes, ce qui est justement la preuve qu'il ne depend d'aucun d'eux.

Ce que ces tests gardent est ce que `sequence()` promet : les preconditions
avant tout, `execute()` jamais atteint apres un echec, les postconditions
jamais verifiees sur un travail qui ne s'est pas fait.
"""

import asyncio

import pytest

from pipeline.core.domain.outcomes.result import Result, Status
from pipeline.core.execution.contract import workflow as contract
from pipeline.core.execution.contract.outcome import WorkflowOutcome


class Gate:
    """Une garde scriptable : ce qu'elle rend, et si elle a ete appelee."""

    def __init__(self, answer=None):
        self.answer = answer if answer is not None else Result.of(None)
        self.seen = 0

    def verify(self, *args):
        self.seen += 1
        return self.answer


class Workflow:
    """Un workflow sur papier, conforme au Protocol et rien de plus."""

    def __init__(self, *, before=None, after=None, does=None):
        self.config = None
        self.log = None
        self.preconditions = before or Gate()
        self.postconditions = after or Gate()
        self.does = does or (lambda: WorkflowOutcome.done("fait"))
        self.ran = 0

    async def run(self) -> WorkflowOutcome:
        return await contract.sequence(self)

    async def execute(self) -> WorkflowOutcome:
        self.ran += 1
        return self.does()


def run(workflow):
    return asyncio.run(workflow.run())


# --- la forme ---------------------------------------------------------------


def test_a_workflow_with_the_four_members_satisfies_the_protocol():
    """Duck typing, mais verifiable : `isinstance` repond sur la forme."""
    assert isinstance(Workflow(), contract.Workflow)


def test_something_missing_a_member_is_not_a_workflow():
    """Un scan qui dirait oui a tout ne garderait rien."""
    class Incomplete:
        config = None

    assert not isinstance(Incomplete(), contract.Workflow)


# --- la sequence ------------------------------------------------------------


def test_the_nominal_sequence_runs_all_three_in_order():
    before, after = Gate(), Gate()
    workflow = Workflow(before=before, after=after)
    outcome = run(workflow)
    assert outcome.ok and outcome.summary == "fait"
    assert (before.seen, workflow.ran, after.seen) == (1, 1, 1)


def test_a_failing_precondition_never_reaches_the_work():
    """Toute la raison d'etre du preflight : ne rien depenser pour rien."""
    before = Gate(Result.halt("l'arbre de travail est sale"))
    after = Gate()
    workflow = Workflow(before=before, after=after)
    outcome = run(workflow)

    assert workflow.ran == 0, "le travail a demarre malgre la porte fermee"
    assert after.seen == 0, "les postconditions ont tourne sur rien"
    assert outcome.status is Status.HALTED
    assert outcome.reason == "l'arbre de travail est sale"
    assert outcome.exit_code == 1


def test_a_failing_workflow_does_not_get_its_postconditions_checked():
    """Elles disent ce qu'un travail *fait* doit avoir obtenu.

    Les faire tourner sur un workflow qui s'est arrete en chemin ne pourrait
    produire qu'un second message, moins juste que le premier.
    """
    after = Gate()
    workflow = Workflow(
        after=after,
        does=lambda: WorkflowOutcome.of_result(Result.quota("plus de fenetre")))
    outcome = run(workflow)

    assert after.seen == 0
    assert outcome.status is Status.QUOTA and outcome.exit_code == 3


def test_a_failing_postcondition_becomes_the_outcome():
    """Le travail s'est fait, mais il n'a pas obtenu ce qu'on exigeait."""
    after = Gate(Result.halt("rien ne marque la task livree"))
    outcome = run(Workflow(after=after))
    assert outcome.failed and outcome.reason == "rien ne marque la task livree"


@pytest.mark.parametrize("failure, code", [
    (Result.halt("x"), 1),
    (Result.unreadable("x"), 1),
    (Result.fail("x"), 2),
    (Result.quota("x"), 3),
])
def test_every_kind_of_failure_travels_out_with_its_code(failure, code):
    """Un ordonnanceur exterieur lit ces codes : la sequence ne les aplatit pas."""
    outcome = run(Workflow(before=Gate(failure)))
    assert outcome.exit_code == code
    assert outcome.status is failure.status


# --- les gardes vides -------------------------------------------------------


def test_the_empty_gates_are_usable_as_they_are():
    """Un workflow sans rien a verifier le dit, plutot que de ne rien mettre."""
    workflow = Workflow(before=contract.NoPreconditions(),
                        after=contract.NoPostconditions())
    assert run(workflow).ok
