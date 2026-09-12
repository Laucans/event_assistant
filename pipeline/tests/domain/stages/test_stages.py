"""La table du pipeline : ce qu'elle valide, et ce qu'elle declare."""

import pytest

from pipeline.domain.stages.agentic_dev_loop_stages import PIPELINE, ROLLOVER
from pipeline.domain.stages.stage_spec import EFFORTS, StageSpec


def test_the_table_is_the_documented_sequence():
    assert [s.skill for s in PIPELINE] == [
        "business-analyst", "code", "create-test"]


def test_nothing_in_the_table_archives_anything():
    """Une task se ferme parce que GitHub la ferme, plus parce qu'un stage
    paye deplace deux fichiers."""
    assert "archive-instructions" not in [s.skill for s in PIPELINE]
    assert len(PIPELINE) == 3


def test_the_code_stage_opens_on_the_tech_analyst():
    code = next(s for s in PIPELINE if s.skill == "code")
    assert code.lead == "/tech-analyst"
    assert code.command == "/tech-analyst"
    assert code.label == "/tech-analyst -> /code"


def test_a_stage_without_lead_opens_on_its_own_skill():
    s = StageSpec("create-test", "sonnet", "high")
    assert s.command == "/create-test" and s.label == "/create-test"


def test_an_invalid_effort_is_refused_at_construction():
    with pytest.raises(ValueError, match="effort"):
        StageSpec("x", "opus", "enormous")


@pytest.mark.parametrize("effort", EFFORTS)
def test_every_documented_effort_is_accepted(effort):
    assert StageSpec("x", "opus", effort).effort == effort


def test_the_rollover_is_off_by_default():
    """Enchainer sur la roadmap suivante sans surveillance est un choix."""
    assert ROLLOVER is None
    assert "planner" not in [s.skill for s in PIPELINE]
