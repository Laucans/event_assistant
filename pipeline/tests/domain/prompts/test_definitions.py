"""The registry: a stage is either given instructions, or declared without."""

import pytest

from pipeline.domain.prompts import definitions
from pipeline.domain.stages.agentic_dev_loop_stages import PIPELINE


@pytest.mark.parametrize("skill", [s.skill for s in PIPELINE])
def test_every_stage_of_the_pipeline_is_named_by_the_registry(skill):
    """A typo in a definition module would otherwise leave a stage mute."""
    assert skill in definitions.EXTRA or skill in definitions.NO_INSTRUCTIONS


@pytest.mark.parametrize("skill", sorted(definitions.NO_INSTRUCTIONS))
def test_a_stage_declared_without_instructions_has_none(skill):
    assert skill not in definitions.EXTRA


@pytest.mark.parametrize("skill", sorted(definitions.NO_INSTRUCTIONS))
def test_a_stage_declared_without_instructions_is_in_the_table(skill):
    """A name left behind by a removed stage declares nothing at all."""
    assert skill in [s.skill for s in PIPELINE]


@pytest.mark.parametrize("stage, text", sorted(definitions.EXTRA.items()))
def test_no_entry_of_the_registry_is_empty(stage, text):
    assert text.strip()
