"""The test that justifies the migration: the stages receive the same text.

The files under `oracle/` were produced by `scripts/agent-loop.sh` before its
deletion, in dry-run, on task 4 and branch main_agent. They are the
reference: if the prompt composition ever drifts, this is where it breaks.

Three differences are intended and named:

- the injector quoted in the preamble — the script no longer exists, and the
  prompt can no longer claim otherwise;
- the per-stage instructions of `code`, which now name a GitHub issue and the
  `Closes #N` line that closes it. There is nothing in the shell's text to
  compare that to, so what is compared here is the half that must not move:
  the preamble, byte for byte, and the composition around it. Le texte des
  stages, lui, appartient au workflow et se teste chez lui —
  `workflows/agentic_dev_loop/test_stage_prompts.py` ;
- one clause of rule 1, which named `/archive-instructions steps 3 and 7`.
  That skill is deleted, so the rule pointed at nothing. The clause was cut
  from the source **and** from the oracle files in the same edit, which is
  what keeps these files an independent artifact rather than a dump of what
  the code currently prints: they are still the shell's text, minus one
  named removal.

`archive-instructions` is no longer a stage, and its oracle is kept for the
same reason — it is a second witness that the preamble and the composition
are unchanged.
"""

import pytest
from conftest import ORACLE

from pipeline.domain.prompts import prompt_builder as prompts

BRANCH = "main_agent"
NUM = "4"
TITLE = "Schema, seed & first DB-backed page"
MILESTONE = "12"
OLD_INJECTOR = "scripts/agent-loop.sh"
END = "--- END EXECUTION CONTEXT ---"

# Le texte qu'un stage d'archivage recevait. Il n'est plus construit par le
# paquet — le stage n'existe plus — mais l'oracle qui le porte teste encore
# tout ce qui l'entoure.
ARCHIVE_EXTRA = 'Archive task 4 ("%s") only.' % TITLE


def oracle(name: str) -> str:
    # The shell wrote `printf '%s\n' "$prompt"`: the file carries a trailing
    # de ligne final que le prompt n'a pas.
    return (ORACLE / ("prompt-%s.txt" % name)).read_text(encoding="utf-8")[:-1]


@pytest.mark.parametrize("stage, lead, extra", [
    ("create-test", "/create-test", ""),
    ("archive-instructions", "/archive-instructions", ARCHIVE_EXTRA),
])
def test_prompt_still_matches_the_shell_to_the_byte(stage, lead, extra):
    built = prompts.build(lead, BRANCH, extra, injector=OLD_INJECTOR)
    assert built == oracle(stage)


def test_the_injector_is_the_only_intentional_difference():
    built = prompts.build("/create-test", BRANCH, injector=prompts.INJECTOR)
    assert prompts.INJECTOR in built
    assert OLD_INJECTOR not in built
    assert built.replace(prompts.INJECTOR, OLD_INJECTOR) == oracle("create-test")


def test_branch_substitution_reaches_every_placeholder():
    built = prompts.build("/code", "integration-x")
    assert "@BRANCH@" not in built
    assert built.count("integration-x") == 3


def test_a_stage_without_extra_stops_at_the_preamble():
    assert prompts.build("/create-test", BRANCH).endswith(END)


def test_extra_is_appended_after_the_preamble():
    built = prompts.build("/x", BRANCH, "EXTRA-TEXT")
    assert built.endswith(END + "\nEXTRA-TEXT")


def test_no_instructions_and_no_scope_produce_no_extra():
    assert prompts.extra_for("", NUM, TITLE) == ""


# --- la portee injectee ----------------------------------------------------
#
# Ce que les stages lisaient dans docs/current/. Une session qui demarre sans
# elle improvise sa propre task.

def scope() -> str:
    return prompts.scope(milestone=MILESTONE, milestone_title="Le milestone",
                         milestone_body="Ce que le milestone veut",
                         num=NUM, title=TITLE, body="Le SPEC de la task")


def test_the_scope_carries_both_bodies_verbatim():
    said = scope()
    assert f"MILESTONE #{MILESTONE} — Le milestone" in said
    assert "Ce que le milestone veut" in said
    assert f"ISSUE #{NUM} — {TITLE}" in said
    assert "Le SPEC de la task" in said


def test_an_empty_body_is_said_in_words_rather_than_left_blank():
    """« rien n'a ete ecrit » et « l'injection est cassee » ne se valent pas."""
    said = prompts.scope(milestone=MILESTONE, num=NUM, title=TITLE)
    assert said.count(prompts.EMPTY_BODY) == 2


def test_a_stage_with_no_instructions_still_gets_its_scope():
    """`/create-test` n'a pas de consigne : sans ca, il ignorerait sa task."""
    built = prompts.extra_for("", NUM, TITLE, scope=scope())
    assert built.startswith("--- SCOPE")
    assert TITLE in built


