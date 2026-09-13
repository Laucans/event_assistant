"""Ce qu'un stage recoit, et la table qui decide lequel tourne.

Un placeholder oublie part tel quel dans une session payante, et un prompt
qui ne dit pas ce qu'il doit rendre rend autre chose. Les deux se voient
avant la depense, ici.
"""

import re
import types

import pytest

from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.issues import Issue
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.workflows.refinement import stages
from pipeline.workflows.refinement.internals import refine, sections
from pipeline.workflows.refinement.settings import RefinementConfig

# Ce qu'un prompt monte n'a plus le droit de porter. `{` seul ne suffit pas :
# la prose en contient (un `{num}` dans un exemple n'existe pas, mais une
# accolade de code oui), donc on cherche la forme d'un champ.
FIELD = re.compile(r"\{[a-z_]+\}")

ISSUE = Issue(number=25, title="Une task", state="open",
              body="## Business Goal\n\nLe but.\n")

ALL_SKILLS = (stages.ROUTER,) + sections.KEYS


def flat(text):
    """Le meme texte sans ses retours a la ligne d'enveloppe.

    Un prompt est de la prose enveloppee : une phrase y est coupee la ou la
    largeur tombe, et l'exiger d'une seule ligne casserait au premier
    reformatage.
    """
    return " ".join(text.split())


def built(skill, *, context="", round_no=2, issue=ISSUE, tmp_path=None):
    """Le texte que ce stage recevrait, monte comme la sequence le monte."""
    cfg = RefinementConfig(issue=25, context=context,
                           workspace=Workspace(tmp_path or "/tmp"))
    state = refine.RefinementState()
    state.issue = issue
    state.round_no = round_no
    ctx = types.SimpleNamespace(cfg=cfg)
    return stages.prompt_of(types.SimpleNamespace(skill=skill), ctx, state)


# --- la table --------------------------------------------------------------


def test_the_sequence_is_the_router_the_five_sections_then_the_publication():
    cfg = RefinementConfig(issue=25)
    assert [step.skill for step in stages.passes(cfg)] == [
        "router", "business-goal", "technical", "acceptance-criteria",
        "business-rules", "technical-plan", "publish"]


def test_the_sections_run_in_the_order_the_body_is_written_in():
    cfg = RefinementConfig(issue=25)
    ran = [s.skill for s in stages.passes(cfg)]
    assert [k for k in ran if k in sections.KEYS] == list(sections.KEYS)


def test_the_publication_is_a_local_step_and_the_rest_are_paid_sessions():
    cfg = RefinementConfig(issue=25)
    table = stages.passes(cfg)
    assert isinstance(table[-1], Action)
    assert all(isinstance(step, StageSpec) for step in table[:-1])


def test_every_section_has_a_prompt_and_a_pair_of_knobs():
    """Une section sans prompt ferait lever la sequence en pleine depense."""
    assert set(stages.PROMPTS) == set(sections.KEYS)
    assert set(stages.KNOBS) == set(sections.KEYS)


def test_each_section_runs_on_the_model_its_own_knob_names():
    cfg = RefinementConfig(issue=25, goal_model="haiku", goal_effort="low",
                           plan_model="opus", plan_effort="high")
    table = {step.skill: step for step in stages.passes(cfg)
             if isinstance(step, StageSpec)}
    assert (table["business-goal"].model, table["business-goal"].effort) == (
        "haiku", "low")
    assert (table["technical-plan"].model, table["technical-plan"].effort) == (
        "opus", "high")


def test_the_router_is_the_cheap_one():
    cfg = RefinementConfig(issue=25)
    router = stages.passes(cfg)[0]
    assert (router.model, router.effort) == ("sonnet", "low")


# --- ce qu'un prompt monte porte -------------------------------------------


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_placeholder_survives_into_a_paid_session(skill):
    """Un `{body}` non substitue part tel quel et coute la session entiere."""
    assert FIELD.search(built(skill)) is None


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_placeholder_survives_when_a_context_is_given_either(skill):
    assert FIELD.search(built(skill, context="revois les criteres")) is None


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_every_prompt_names_the_issue_it_works_on(skill):
    said = built(skill)
    assert "#25" in said and "Une task" in said


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_every_prompt_carries_the_body_as_it_stands(skill):
    assert "## Business Goal\n\nLe but." in built(skill)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_an_issue_with_an_empty_body_says_so_in_words(skill):
    """Un blanc ne se distingue pas d'une injection cassee ; une phrase, si."""
    said = built(skill, issue=Issue(number=25, title="Une task", body="  "))
    assert prompts.EMPTY_BODY in said


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_every_prompt_says_which_round_it_is(skill):
    assert "round 4" in built(skill, round_no=4)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_prompt_lets_a_session_touch_the_issue_itself(skill):
    """Le workflow ecrit le corps : un stage qui l'ecrit aussi le fait deux fois."""
    said = built(skill)
    assert "Change no file, post no comment, touch no issue" in said


@pytest.mark.parametrize("key", sections.KEYS)
def test_each_section_prompt_names_the_section_it_writes(key):
    heading = sections.by_key(key).heading
    said = built(key)
    assert f"**{heading}**" in said


@pytest.mark.parametrize("key", sections.KEYS)
def test_each_section_prompt_asks_for_the_content_without_its_heading(key):
    """Un `## Business Goal` rendu par le stage ferait un titre en double."""
    assert "Output the content of the section and nothing else" in built(key)


@pytest.mark.parametrize("key", sections.KEYS)
def test_each_section_prompt_forbids_a_level_two_heading_anywhere(key):
    """Un `## ...` rendu par un stage ampute sa section au round suivant.

    `parse` traite tout titre de niveau 2 inconnu comme une frontiere : le
    texte qui le suit sort du corps reecrit, et ne revient pas.
    """
    said = flat(built(key))
    assert "never write a level-2 heading" in said
    assert "split back into sections" in said


@pytest.mark.parametrize("key", sections.KEYS)
def test_each_section_prompt_still_allows_the_deeper_headings(key):
    """`parse` ne coupe que sur `## ` : interdire `###` amputerait la prose."""
    assert "Deeper headings (`### `) are fine" in built(key)


@pytest.mark.parametrize("key", sections.KEYS)
def test_each_section_prompt_says_the_issues_are_public(key):
    """Les issues de ce depot sont publiques, et un SPEC y est ecrit en clair."""
    said = built(key)
    assert "issues of this repository are public" in said
    assert "Never write the value of a secret" in said


def test_the_router_is_given_the_only_five_keys_it_may_name():
    said = built(stages.ROUTER)
    for key in sections.KEYS:
        assert key in said
    assert "one per line" in said


# --- le bloc de contexte additionnel ---------------------------------------


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_what_the_human_asked_reaches_every_stage_of_the_round(skill):
    said = built(skill, context="ne parle que du cache")
    assert "--- additional_context ---" in said
    assert "ne parle que du cache" in said
    assert "--- end additional_context ---" in said


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_a_round_without_a_context_carries_no_context_block(skill):
    """Un bloc vide se lit comme une demande vide, et non comme pas de demande."""
    assert "additional_context" not in built(skill)


def test_the_context_block_is_empty_when_there_is_nothing_to_say():
    assert stages.additional_context("") == ""


def test_the_context_block_quotes_the_human_verbatim():
    said = stages.additional_context("ne parle QUE du cache")
    assert "ne parle QUE du cache" in said
    assert said.startswith("--- additional_context ---")
    assert said.endswith("--- end additional_context ---")


@pytest.mark.parametrize("key", sections.KEYS)
def test_a_context_that_names_a_field_is_not_a_second_substitution(key):
    """`--context` est du texte humain : `{body}` n'y est pas un champ."""
    said = built(key, context="garde la section {body} telle quelle",
                 issue=ISSUE)
    assert "garde la section {body} telle quelle" in said
    assert said.count(ISSUE.body.strip()) == 1
