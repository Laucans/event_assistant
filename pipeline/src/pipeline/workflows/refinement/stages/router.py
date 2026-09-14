"""Le prompt du routeur : quelles sections ce round rouvre."""

ROUTER_PROMPT = """You are routing one refinement round on GitHub issue #{num} ("{title}") in
this repository. This is round {round}. You decide which sections of the
issue body get rewritten this round, and you decide nothing else — each
section you name costs a paid session, and each one you leave out stays
exactly as it is.

These are the only section keys that exist, in the order they appear in the
body:
{keys}

Here is the body as it stands right now:
<issue-body>
{body}
</issue-body>

{additional_context}

Name the sections the request above actually asks to rework, plus the ones
that cannot stay consistent once those change — a changed Business Goal
usually drags the Acceptance Criteria with it, a changed Technical section
usually drags the Technical Implementation Plan. Name nothing else: a section
nobody asked about is better left alone. If the request is broad enough to
touch everything, naming all five is a correct answer.

Answer with the section keys alone, one per line, spelled exactly as listed
above. No numbering, no bullets, no headings, no explanation, no empty answer
— a reply naming no key stops the round.

Change no file, post no comment, touch no issue and no label."""
