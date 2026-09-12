"""The instructions specific to the `business-analyst` stage."""

BUSINESS_ANALYST = """Take issue #{num} ("{title}") — its body is below, under SCOPE. The
interview in step 3 of the skill cannot happen — no human is reachable.
Answer each question you would have asked from docs/PROJECT.md,
docs/ARCHITECTURE.md and the repo itself, and record every answer you had
to assume under an `## Assumptions (autonomous run)` heading. Write the SPEC
into the body of issue #{num} itself — that body is what the /code stage
reads, and nothing else is. Anything a human must do first becomes its own
`pipeline:human` issue, a sub-issue of milestone #{milestone}, declared as a
dependency of #{num}: the loop will not pick #{num} up again until it is
closed. If an assumption would make the task useless or harmful when wrong —
a paid service, a schema decision the later tasks depend on, a credential
only the human holds — that is ambiguity, not a default: AGENT_LOOP_STOP
instead of guessing."""
