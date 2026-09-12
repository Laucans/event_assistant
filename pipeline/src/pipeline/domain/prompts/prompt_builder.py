"""The prompts sent to the stages — the loop's verbal contract.

The preamble and the per-stage instructions were taken character for
character from the old `scripts/agent-loop.sh`: that is what makes it
provable, by diff, that the migration changed nothing about what the stages
receive. The only intended difference is the name of the injector.
"""

from pipeline.domain.prompts import definitions

# The name quoted in the preamble. Former value: "scripts/agent-loop.sh".
INJECTOR = "pipeline/launcher/cli/agentic_dev_loop.py"

_PREAMBLE = """
--- EXECUTION CONTEXT (injected by scripts/agent-loop.sh) ---
You are running head-less in an unattended loop (`claude -p`). Nobody will
read this output before the run ends and nobody can answer a question.
These rules override the skill's interactive stopping points:

1. Where the skill waits for a go-ahead or a confirmation (/code steps 2
   and 3), write your findings into your reply and carry on. Reporting
   stays mandatory; waiting does not.
2. Where the skill says to ask because a choice is genuinely ambiguous, do
   not guess. Stop, change nothing further, and end your reply with the one
   line `AGENT_LOOP_STOP: <one-line reason>`. The loop halts and a human
   picks it up. Stopping is a correct outcome, not a failure.
3. The integration branch for this run is `@BRANCH@`. Wherever a skill says
   `main` as the PR base or the branch-off point, read `@BRANCH@`: branch
   off it, and `gh pr create --base @BRANCH@`. The rest of CLAUDE.md's
   Repository etiquette stands unchanged — branch -> PR ->
   `gh pr merge --rebase`, and never a direct push.
4. Stage by name, never `git add -A`. The tree may carry unrelated
   in-flight work that is not yours to commit.
5. Do not start another pipeline stage as its own process, and do not
   /clear. The loop runs one process per stage. Where this prompt names a
   second skill to continue into, that continuation is part of this same
   stage — not a new one, and not something to hand off.
6. End your reply with `AGENT_LOOP_OK: <one-line summary>` if the stage
   completed, or `AGENT_LOOP_STOP: <reason>` if it did not.
--- END EXECUTION CONTEXT ---"""


def fill(template: str, **values: str) -> str:
    """Replace every `{name}` placeholder in `template` by its value.

    A plain chain of replacements, not `str.format`: these bodies are prose
    written for a model, and they carry braces of their own that format would
    read as fields. Values are substituted in the order they are passed.
    """
    for name, value in values.items():
        template = template.replace("{" + name + "}", value)
    return template


def preamble(branch: str, injector: str = INJECTOR) -> str:
    """The EXECUTION CONTEXT block, with the integration branch substituted."""
    return (_PREAMBLE
            .replace("@BRANCH@", branch)
            .replace("scripts/agent-loop.sh", injector))


def build(lead: str, branch: str, extra: str = "", injector: str = INJECTOR) -> str:
    """A stage's complete prompt.

    Reproduces the shell's composition exactly:
    `prompt="$lead"$'\n'"$(preamble)"` puis `"$prompt"$'\n'"$extra"`.
    """
    prompt = lead + "\n" + preamble(branch, injector)
    if extra:
        prompt = prompt + "\n" + extra
    return prompt


# What every stage is handed on top of its instructions: the milestone it
# belongs to and the issue it is working on, both verbatim. A session that
# starts without them has to guess at its own scope, and the two files it
# used to read (docs/current/CURRENT_MILESTONE.md, docs/current/SPEC.md) no
# longer exist. It goes in `extra`, so the preamble's composition — asserted
# byte for byte against the shell's — is untouched.
_SCOPE = """--- SCOPE (injected by {injector}) ---
The milestone and the issue below are the whole brief; there is no
docs/current/ any more. Both are GitHub issues: what you produce goes back
into the issue, not into a file under docs/.

MILESTONE #{milestone} — {milestone_title}
{milestone_body}

ISSUE #{num} — {title}
{body}
--- END SCOPE ---"""

EMPTY_BODY = "(empty — nothing has been written into this issue yet)"


def scope(*, milestone: str = "", milestone_title: str = "",
          milestone_body: str = "", num: str = "", title: str = "",
          body: str = "", injector: str = INJECTOR) -> str:
    """The scope block for one stage: the milestone issue, then the task issue.

    An empty body is said in words rather than left blank: a stage that reads
    a blank section cannot tell "nothing was written" from "the injection
    broke", and only one of those is worth stopping for.
    """
    return fill(_SCOPE, injector=injector, milestone=milestone,
                milestone_title=milestone_title,
                milestone_body=(milestone_body.strip() or EMPTY_BODY),
                num=num, title=title, body=(body.strip() or EMPTY_BODY))


def extra_for(stage: str, num: str = "", title: str = "", *,
              milestone: str = "", scope: str = "") -> str:
    """A stage's `extra`: its own instructions, then the scope it works in.

    The scope comes last because it is the long part — the instructions stay
    where a reader (and a model) finds them, at the top. A stage with no
    entry in EXTRA still gets its scope: `create-test` has no instructions of
    its own, and would otherwise be the one paid session in the round that
    does not know which task it is testing.
    """
    body = fill(definitions.EXTRA.get(stage, ""), num=num, title=title,
                milestone=milestone)
    if not scope:
        return body
    return f"{body}\n\n{scope}" if body else scope
