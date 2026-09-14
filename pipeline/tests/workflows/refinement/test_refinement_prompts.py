"""Ce qu'un stage recoit, et la table qui decide lequel tourne.

Un placeholder oublie part tel quel dans une session payante, et un prompt
qui ne dit pas ce qu'il doit rendre rend autre chose. Les deux se voient
avant la depense, ici.
"""

import re
import types
from pathlib import Path

import pytest

from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.issues import Issue
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.workflows.common import stages as common
from pipeline.workflows.refinement import stages
from pipeline.workflows.refinement.internals import refine, sections
from pipeline.workflows.refinement.settings import RefinementConfig

# Ce qu'un prompt monte n'a plus le droit de porter. `{` seul ne suffit pas :
# la prose en contient (un `{num}` dans un exemple n'existe pas, mais une
# accolade de code oui), donc on cherche la forme d'un champ.
FIELD = re.compile(r"\{[a-z_]+\}")

ISSUE = Issue(number=25, title="Une task", state="open",
              body="## Business Goal\n\nLe but.\n")

ALL_SKILLS = (stages.ROUTER, stages.COHERENCE) + sections.KEYS


def flat(text):
    """Le meme texte sans ses retours a la ligne d'enveloppe.

    Un prompt est de la prose enveloppee : une phrase y est coupee la ou la
    largeur tombe, et l'exiger d'une seule ligne casserait au premier
    reformatage.
    """
    return " ".join(text.split())


def built(skill, *, context="", round_no=2, issue=ISSUE, tmp_path=None,
          repo_context="", wanted=(), results=None):
    """Le texte que ce stage recevrait, monte comme la sequence le monte.

    `state.found` est pose comme `precheck` le poserait vraiment (le corps
    de l'issue, parse) : aucun stage autre que la coherence ne le lit, mais
    c'est ce dont la coherence a besoin pour montrer un `{body}` different du
    corps brut — `wanted`/`results` simulent ce qu'un round a deja produit.
    """
    cfg = RefinementConfig(issue=25, context=context,
                           workspace=Workspace(tmp_path or "/tmp"))
    state = refine.RefinementState()
    state.issue = issue
    state.round_no = round_no
    state.found = sections.parse(issue.body if issue is not None else "")
    state.wanted = list(wanted)
    # La carte et les sections du round voyagent par `ctx.results`, sous le
    # nom de l'etape qui les a produites — comme la reponse du routeur.
    all_results = dict(results or {})
    if repo_context:
        all_results[common.SKILL] = types.SimpleNamespace(text=repo_context)
    ctx = types.SimpleNamespace(
        cfg=cfg, log_dir=Path(tmp_path or "/tmp"), round_no=round_no,
        results=all_results)
    return stages.prompt_of(types.SimpleNamespace(skill=skill), ctx, state)


# --- la table --------------------------------------------------------------


def test_the_sequence_is_the_router_the_five_sections_then_the_publication():
    cfg = RefinementConfig(issue=25)
    assert [step.skill for step in stages.passes(cfg)] == [
        "ground", "explore",
        "router", "business-goal", "technical", "acceptance-criteria",
        "business-rules", "technical-plan", "coherence", "publish"]


def test_the_sections_run_in_the_order_the_body_is_written_in():
    cfg = RefinementConfig(issue=25)
    ran = [s.skill for s in stages.passes(cfg)]
    assert [k for k in ran if k in sections.KEYS] == list(sections.KEYS)


def test_the_two_local_steps_are_the_grounding_and_the_publication():
    """Les deux bouts de la table ne paient rien : l'un lit le depot, l'autre
    ecrit dans l'issue. Tout ce qui est entre est une session."""
    table = stages.passes(RefinementConfig(issue=25))
    local = [step.skill for step in table if isinstance(step, Action)]
    assert local == [common.GROUND, "publish"]
    assert all(isinstance(step, StageSpec) for step in table[1:-1])


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
    # Par son nom et non par sa place : la table a gagne deux entrees en tete,
    # et un index fige aurait rendu ce test muet plutot que rouge.
    router = next(s for s in stages.passes(cfg) if s.skill == stages.ROUTER)
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


# --- la carte du depot -----------------------------------------------------
#
# Ce qui a remplace le paragraphe « va lire docs/ARCHITECTURE.md » que les six
# templates portaient chacun a sa facon. Le registre disait le prix de ces six
# copies : sept a quinze tours par section, dont la moitie a s'orienter.


def template_of(skill):
    """Le texte non monte de ce stage — `ROUTER`/`COHERENCE` n'ont pas de
    section dans `stages.PROMPTS`, qui n'indexe que les cinq sections."""
    if skill == stages.ROUTER:
        return stages.ROUTER_PROMPT
    if skill == stages.COHERENCE:
        return stages.COHERENCE_PROMPT
    return stages.PROMPTS[skill]


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_template_carries_the_repo_context_placeholder(skill):
    """La carte prefixe le texte monte, elle n'est pas un champ substitue :
    un `{repo_context}` que sept templates auraient porte chacun se serait tu
    en silence si l'un l'avait perdu, la ou un prefixe ne peut pas manquer."""
    assert "{repo_context}" not in template_of(skill)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_every_stage_opens_on_the_repo_map_identically(skill):
    """En tete, et identique partout : c'est ce qui donne aux sept sessions un
    prefixe de cache commun. L'hypothese se verifie sur `cache_write` dans
    .llocal/refinement/costs.tsv — la place, elle, ne coute rien."""
    assert built(skill).startswith(common.UNMAPPED)
    said = built(skill, repo_context="### Constraints\njamais de push sur main")
    assert said.startswith(common.OPEN)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_template_still_sends_a_section_reading_the_documents(skill):
    """Une carte **ajoutee** pendant que la consigne reste augmente le cout au
    lieu de le reduire : elle s'ajoute a l'exploration au lieu de la
    remplacer."""
    said = flat(template_of(skill))
    assert "Ground what you write in the repository" not in said
    assert "Read whatever you need" not in said
    assert "Read the repository if you need" not in said


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_a_stage_without_a_map_is_told_so_in_words(skill):
    """Sinon elle ne distingue pas « rien a savoir » de « injection cassee »."""
    assert "No map was established" in built(skill)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_a_stage_with_a_map_gets_it_and_is_told_what_it_may_still_open(skill):
    said = built(skill, repo_context="### Constraints\njamais de push sur main")
    assert "jamais de push sur main" in said
    assert "you do not have to orient yourself" in flat(said)
    assert "No map was established" not in said


def test_the_map_enters_the_prompt_in_the_same_pass_as_the_body():
    """La carte cite les fichiers du depot : elle porte litteralement les
    `{body}` et `{num}` des templates qu'elle a lus, et une seconde passe de
    remplacement les substituerait."""
    said = built("technical", repo_context="le template porte {body} et {num}")
    assert "le template porte {body} et {num}" in said


def test_the_map_does_not_turn_the_router_on():
    """`cfg.context` decide si le routeur tourne : y deposer la carte le
    rallumerait a tous les rounds a partir du troisieme."""
    from pipeline.workflows.refinement.internals import gates, rounds

    state = refine.RefinementState()
    state.round_no = 3
    cfg = RefinementConfig(issue=25)
    ctx = types.SimpleNamespace(cfg=cfg)
    assert cfg.context == ""
    assert not rounds.routed(3, bool(cfg.context))
    assert gates.router_is_off(ctx, state).value, "le routeur s'est allume"


# --- la coherence : le corps qu'elle recoit ---------------------------------
#
# Les six autres stages recoivent `issue.body`, fige a `precheck`. La
# coherence recoit ce que ce round s'apprete a publier — sinon elle relirait
# exactement ce que chaque section a deja lu, sans jamais voir ce qu'elles
# viennent d'ecrire.


def test_coherence_sees_this_rounds_fresh_sections_not_just_the_old_body():
    said = built(stages.COHERENCE, wanted=["technical"],
                 results={"technical": types.SimpleNamespace(
                     text="La technique retouchee.")})
    assert "La technique retouchee." in said


def test_coherence_still_carries_a_section_this_round_did_not_touch():
    issue = Issue(number=25, title="Une task", state="open",
                  body="## Business Goal\n\nLe but.\n\n"
                       "## Technical\n\nLa technique.\n")
    said = built(stages.COHERENCE, issue=issue, wanted=["technical"],
                 results={"technical": types.SimpleNamespace(
                     text="La technique retouchee.")})
    assert "Le but." in said
    assert "La technique retouchee." in said


def test_coherence_is_told_not_to_drop_or_rename_a_heading():
    assert "Do not drop a section" in flat(built(stages.COHERENCE))
