"""Ce que le declencheur lit d'un evenement, sans rien lancer.

`refinable` est la seule chose qui decide si un raffinage — jusqu'a cinq
sessions opus — part. Pure, elle se teste en lui passant un dictionnaire.
"""

import pytest

from pipeline.launcher.hooks.refinement_trigger import LABEL, refinable


def payload(label=LABEL, number=25, action="labeled"):
    """La charge utile GitHub `issues.labeled`."""
    return {"action": action, "label": {"name": label},
            "issue": {"number": number}}


def flat(label=LABEL, number=25, action="labeled"):
    """La forme plate, celle qu'un appelant a la main ecrit."""
    return {"action": action, "label": label, "issue": number}


def test_the_label_the_hook_watches_is_the_one_the_workflow_reads():
    """Un hook ne peut pas importer `workflows` : les deux chaines se separent."""
    from pipeline.workflows.common import labels
    assert LABEL == labels.REFINEMENT


def test_an_issue_the_human_just_labelled_is_refinable():
    assert refinable(payload()) == "25"


def test_the_flat_form_is_read_as_well():
    assert refinable(flat()) == "25"


@pytest.mark.parametrize("number", [25, "25"])
def test_a_number_said_as_a_number_or_as_a_string_is_the_same_issue(number):
    assert refinable(payload(number=number)) == "25"
    assert refinable(flat(number=number)) == "25"


@pytest.mark.parametrize("label", ["pipeline:ready", "pipeline:agent",
                                   "refinement", "pipeline:refinements", ""])
def test_another_label_launches_nothing(label):
    """Un faux positif ici depense cinq sessions et reecrit un corps d'issue."""
    assert refinable(payload(label=label)) is None
    assert refinable(flat(label=label)) is None


@pytest.mark.parametrize("action", ["unlabeled", "opened", "closed", "edited",
                                    "", None])
def test_anything_but_a_labelling_launches_nothing(action):
    """`unlabeled` porte la meme etiquette : la retirer relancerait un round."""
    assert refinable(payload(action=action)) is None


@pytest.mark.parametrize("number", [None, "", "abc", "25a", -0.5, True,
                                    {"id": 1}])
def test_an_issue_number_that_is_not_one_launches_nothing(number):
    assert refinable(payload(number=number)) is None
    assert refinable(flat(number=number)) is None


def test_an_issue_without_a_number_launches_nothing():
    assert refinable({"action": "labeled", "label": {"name": LABEL},
                      "issue": {}}) is None


@pytest.mark.parametrize("event", [
    {}, None, [], "labeled", {"action": "labeled"},
    {"action": "labeled", "label": None, "issue": None},
    {"action": "labeled", "label": {"name": None}, "issue": {"number": 25}},
    {"action": None, "label": {"name": LABEL}, "issue": {"number": 25}},
])
def test_a_shape_it_does_not_expect_never_raises(event):
    """Le hook echoue en ouvert : il ne doit jamais casser un etiquetage."""
    assert refinable(event) is None
