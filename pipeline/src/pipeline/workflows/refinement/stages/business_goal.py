"""Le prompt de la section « Business Goal »."""

BUSINESS_GOAL_PROMPT = """You are refining GitHub issue #{num} ("{title}") in this repository. This is
refinement round {round}, and you write one section of its body: the
**Business Goal**.

Say what this task is for, at the altitude a product owner states it: the
outcome someone gets once it ships, who that someone is, and why it is worth
doing now. A short paragraph, or a paragraph and three or four bullets — no
more. Name the user-visible change, not the code that makes it. Leave the how
out entirely: the Technical section and the Technical Implementation Plan
carry it. If this task is plumbing with no user-visible outcome, say what it
unblocks instead of inventing a user for it.

Here is the body of the issue as it stands right now:
<issue-body>
{body}
</issue-body>

On round 1 that body is the raw request, as a human dropped it there: it is
your source material to translate, not text to preserve. From round 2 on a
Business Goal section is probably already in it — rework it, keeping what
still holds and fixing what does not, rather than rewriting from scratch.

{additional_context}

Ground what you write in the repository rather than guessing: docs/PROJECT.md
for the product, docs/ARCHITECTURE.md for the technical design, CLAUDE.md for
the constraints that are not visible in the code. Read whatever you need to
read.

Output the content of the section and nothing else: no `## Business Goal`
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
