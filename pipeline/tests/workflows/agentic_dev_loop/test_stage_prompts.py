"""Ce que les stages de ce round ont a dire — le texte, pas l'assemblage.

Ici et plus dans `domain/prompts/` : la prose d'un stage est la definition de
ce workflow. `domain/prompts/test_prompts.py` garde ce qui reste vrai pour
n'importe quel workflow — le preambule, la composition, le bloc de portee, et
l'oracle tire du shell.

Le texte voyage dans `StageSpec.instructions` : ces tests le lisent dans la
table, ce qui les fait echouer si une entree perd son texte au lieu de le
faire silencieusement.
"""

import pytest
from conftest import ORACLE

from pipeline.core.domain import prompts
from pipeline.core.domain.stage_spec import spec_of
from pipeline.workflows.agentic_dev_loop.stages import PIPELINE, PLANNER_STAGE

BRANCH = "main_agent"
NUM = "4"
TITLE = "Schema, seed & first DB-backed page"
MILESTONE = "12"
OLD_INJECTOR = "scripts/agent-loop.sh"
END = "--- END EXECUTION CONTEXT ---"

# La table, plus l'entree de rollover qui n'y est pas branchee : son texte est
# paye des qu'on l'active, donc il est tenu aux memes regles.
EVERY_STAGE = (*PIPELINE, PLANNER_STAGE)


def instructions(skill: str) -> str:
    spec = spec_of(skill, EVERY_STAGE)
    assert spec is not None, f"{skill} n'est plus dans la table"
    return spec.instructions


def extra(skill: str, **fields) -> str:
    return prompts.extra_for(instructions(skill), **fields)


def scope() -> str:
    return prompts.scope(milestone=MILESTONE, milestone_title="Le milestone",
                         milestone_body="Ce que le milestone veut",
                         num=NUM, title=TITLE, body="Le SPEC de la task")


def test_the_code_prompt_keeps_the_shells_preamble_word_for_word():
    """Seules les consignes du stage ont bouge : le preambule, jamais.

    Elles ne pouvaient pas ne pas bouger — elles nommaient
    `docs/current/SPEC.md`, qui n'existe plus. Ce qui les entoure est
    exactement ce que le shell composait.
    """
    built = prompts.build("/tech-analyst", BRANCH,
                          extra("code", num=NUM, title=TITLE,
                                milestone=MILESTONE),
                          injector=OLD_INJECTOR)
    head = (ORACLE / "prompt-code.txt").read_text(
        encoding="utf-8")[:-1].split(END)[0] + END
    assert built.startswith(head)
    assert built[len(head)] == "\n"


def test_the_code_stage_is_told_what_closes_the_issue():
    """Rien d'autre ne ferme une task, et la boucle s'arrete si rien ne l'a
    fait."""
    built = extra("code", num=NUM, title=TITLE, milestone=MILESTONE)
    assert "Closes #4" in built
    assert "docs/current/SPEC.md" not in built


def test_the_analyst_stage_is_told_to_write_into_the_issue_body():
    built = extra("business-analyst", num=NUM, title=TITLE,
                  milestone=MILESTONE)
    assert "body of issue #4" in built
    assert "pipeline:human" in built and "milestone #12" in built
    assert "docs/current" not in built


def test_the_planner_stage_reads_the_roadmap_from_the_issues():
    built = extra("planner", milestone=MILESTONE)
    assert "pipeline:roadmap" in built
    assert "docs/ROADMAP.md" not in built
    assert "pipeline:ready" in built, "le robinet reste a l'humain"


def test_the_scope_follows_the_stages_own_instructions():
    built = extra("code", num=NUM, title=TITLE, milestone=MILESTONE,
                  scope=scope())
    assert built.index("Closes #%s" % NUM) < built.index("--- SCOPE")


def test_no_stage_is_told_to_archive_anything_any_more():
    """Le stage a disparu : sa consigne ne doit pas survivre a cote."""
    for spec in EVERY_STAGE:
        assert "archive" not in spec.instructions.lower(), spec.skill


@pytest.mark.parametrize("spec", EVERY_STAGE, ids=lambda s: s.skill)
def test_no_stage_instruction_still_points_at_a_deleted_file(spec):
    """Un prompt qui nomme un fichier absent envoie la session le chercher."""
    assert "docs/current" not in spec.instructions
    assert "docs/ROADMAP.md" not in spec.instructions
