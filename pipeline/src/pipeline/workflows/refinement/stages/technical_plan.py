"""Le prompt de la section « Technical Implementation Plan »."""

TECHNICAL_PLAN_PROMPT = """You are refining GitHub issue #{num} ("{title}") in this repository. This is
refinement round {round}, and you write one section of its body: the
**Technical Implementation Plan**.

Write the ordered plan the implementing agent will follow. One numbered step
per unit of work, in the order they get done, and each step naming the real
file paths it touches, the functions or types it adds or changes with their
signatures, and the command that proves that step landed — the actual command
this repository runs, not "add tests". Put the steps in an order where each
one leaves the tree working. Close with the risks: what this plan assumes,
what could already be different from what you read, and where an
implementer's judgement will be needed. Do not write the code itself, and do
not restate the Technical section's design — plan the work it implies.

Here is the body of the issue as it stands right now:
<issue-body>
{body}
</issue-body>

Round 1 has already written the Business Goal, the Technical section and the
Acceptance Criteria above: the plan implements those, and every acceptance
criterion should be reachable through one of your steps. From round 2 on a
Technical Implementation Plan may already be in the body — rework it, keeping
what still holds and fixing what does not, rather than rewriting from
scratch.

{additional_context}

Output the content of the section and nothing else: no `## Technical
Implementation Plan` heading, no preamble, no closing remark, no code fence
wrapped around the whole answer. One rule on the markdown inside it: never
write a level-2 heading — no line starting with `## `, anywhere in your answer —
because next round this body is split back into sections on exactly those
lines, and everything under a `## ` of yours would be dropped from the section
for good. Deeper headings (`### `) are fine, and so is the rest of markdown.

Change no file, post no comment, touch no issue and no label. The workflow
writes what you output back into the body of #{num} itself.

The issues of this repository are public. Never write the value of a secret,
a token, a key, a password, or a URL that carries one — name the variable and
say where it lives."""
