"""Ce qu'un stage est : la forme, les efforts acceptes, la lecture d'une table.

Le **type**, pas les instances. Quels stages un workflow fait tourner se
teste chez lui — `workflows/agentic_dev_loop/test_stages.py`.
"""

import pytest

from pipeline.domain.stage_spec import EFFORTS, StageSpec, names, spec_of


def test_a_stage_without_lead_opens_on_its_own_skill():
    s = StageSpec("create-test", "sonnet", "high")
    assert s.command == "/create-test" and s.label == "/create-test"


def test_a_stage_with_a_lead_opens_on_it_and_says_so():
    s = StageSpec("code", "opus", "high", lead="/tech-analyst")
    assert s.command == "/tech-analyst"
    assert s.label == "/tech-analyst -> /code"


def test_an_invalid_effort_is_refused_at_construction():
    with pytest.raises(ValueError, match="effort"):
        StageSpec("x", "opus", "enormous")


@pytest.mark.parametrize("effort", EFFORTS)
def test_every_documented_effort_is_accepted(effort):
    assert StageSpec("x", "opus", effort).effort == effort


def test_a_stage_carries_its_own_instructions():
    """La prose est dans l'entree, pas dans un registre indexe par nom.

    Ce que ce champ supprime : un stage renomme d'un cote et pas de l'autre,
    qui partait muet sans que rien ne le dise.
    """
    assert StageSpec("x", "opus", "high").instructions == ""
    assert StageSpec("x", "opus", "high", instructions="do it").instructions


def test_a_table_is_read_by_name_and_never_raises():
    """`next()` sans defaut levait un StopIteration nu — et dans une methode
    async, un `RuntimeError` qui ne disait rien de l'entree renommee."""
    table = (StageSpec("a", "opus", "high"), StageSpec("b", "sonnet", "low"))
    assert spec_of("a", table).model == "opus"
    assert spec_of("nope", table) is None


def test_a_table_names_its_entries_for_an_error_message():
    table = (StageSpec("a", "opus", "high"), StageSpec("b", "sonnet", "low"))
    assert names(table) == "a b"
    assert names(()) == "(nothing)"
