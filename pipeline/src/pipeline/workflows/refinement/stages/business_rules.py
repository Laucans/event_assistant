"""Le prompt de la section « Business Rules »."""

BUSINESS_RULES_PROMPT = """You are refining GitHub issue #{num} ("{title}") in this repository. This is
refinement round {round}, and you write one section of its body: the
**Business Rules**.

State the rules the domain imposes on whatever gets built here: the
invariants that must hold, what is valid input and what is refused, which
rule wins when two of them meet, what happens at the boundaries (empty, zero,
the first time, the last one, two at once), and the default taken when
nothing is specified. Number them, one rule per line or per short bullet,
each one standing on its own and each one testable — a rule a test cannot
fail is a sentence, not a rule. Where the code already implies a rule, state
it as it actually is today and flag it explicitly when the request
contradicts it; that contradiction is the most valuable line in this section.
Rules only: no implementation, no schedule, no UI copy.

Here is the body of the issue as it stands right now:
<issue-body>
{body}
</issue-body>

Round 1 has already written the Business Goal, the Technical section and the
Acceptance Criteria above: read them, and stay consistent with them. From
round 2 on a Business Rules section may already be in the body — rework it,
keeping what still holds and fixing what does not, rather than rewriting from
scratch.

{additional_context}

Ground what you write in the repository rather than guessing: docs/PROJECT.md
for the product rules, docs/ARCHITECTURE.md for the design, CLAUDE.md for the
constraints that are not visible in the code, and the code itself for the
rules already in force. Read whatever you need.

Output the content of the section and nothing else: no `## Business Rules`
heading, no preamble, no closing remark, no code fence wrapped around the
whole answer. One rule on the markdown inside it: never write a level-2
heading — no line starting with `## `, anywhere in your answer — because next
round this body is split back into sections on exactly those lines, and
everything under a `## ` of yours would be dropped from the section for good.
Deeper headings (`### `) are fine, and so is the rest of markdown.

Change no file, post no comment, touch no issue and no label. The workflow
writes what you output back into the body of #{num} itself.

The issues of this repository are public. Never write the value of a secret,
a token, a key, a password, or a URL that carries one — name the variable and
say where it lives."""
