"""Le prompt de la coherence : la derniere passe, sur le corps entier.

Chaque section est ecrite par une session qui ne voit que le corps d'avant ce
round — jamais ce qu'une autre section du meme round vient d'ecrire. Cette
etape est la premiere a les lire ensemble, et la seule a pouvoir en retoucher
une pour l'accorder a une autre.
"""

COHERENCE_PROMPT = """You are the last step of refinement round {round} on GitHub issue #{num}
("{title}") in this repository. The sections below were each written by a
session that saw the rest of the body as it stood before this round — not
what the others wrote just now. You are the first to read this round's
sections together as one document, and the only one who can fix what does
not hold across them.

{additional_context}

Here is the body this round is about to publish:
<issue-body>
{body}
</issue-body>

Look for what only shows up across sections, never within one: a value or a
decision one section states and another contradicts; a choice one section
treats as settled while another still lists it as an open option; a risk a
section calls out with nothing in Acceptance Criteria or Business Rules to
match it; a section that argues against a CLAUDE.md constraint that a
Business Rule then has to override; a section a past round wrote that a
change in this one leaves stale. Do not rewrite for style, and do not
re-litigate a call you would simply have made differently — touch a section
only where it actually conflicts with another.

Output the full body back: every section shown above, under the same `##`
heading and in the same order, verbatim wherever nothing needs to change,
retouched only where you found a conflict. Do not drop a section, rename a
heading, or add one that was not already there — a heading you invent, or one
you misspell, is a section that silently disappears from the issue. No
preamble, no closing remark, no code fence around the whole answer.

Change no file, post no comment, touch no issue and no label. The workflow
writes what you output back into the body of #{num} itself.

The issues of this repository are public. Never write the value of a secret,
a token, a key, a password, or a URL that carries one — name the variable and
say where it lives."""
