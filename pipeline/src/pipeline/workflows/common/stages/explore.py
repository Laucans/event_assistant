"""Le texte de l'exploration : ce qu'on demande a la carte, et ce qu'elle vaut.

Trois blocs de prose, et rien d'autre — la mecanique est dans
`workflows/common/stages/__init__.py`.

`EXPLORE_PROMPT` est ce que paie la session d'exploration. `MAPPED` et
`UNMAPPED` sont les deux formes du `{repo_context}` que chaque etape recoit
ensuite : l'une sert la carte, l'autre dit qu'il n'y en a pas. Les deux sont
**ici et pas dans chaque template**, parce qu'elles etaient la meme phrase
recopiee six fois avec une nuance par section — et six copies d'une consigne
sont six occasions de n'en corriger que cinq.
"""

# Ce qui ouvre et ferme la carte dans le prompt d'une etape. Un bloc qui se
# nomme : une etape qui lit du contexte sans frontiere ne sait pas ou finit ce
# qu'on lui a donne et ou commence ce qu'elle doit produire.
OPEN = "--- REPO MAP (established once for this run) ---"
CLOSE = "--- END REPO MAP ---"

# La carte est la, et ce qu'elle autorise. Le point delicat est la derniere
# phrase : une carte est lossy, et une etape a qui on interdit de lire ne peut
# pas distinguer « ce detail n'existe pas » de « il n'a pas ete inclus ». Elle
# inventerait. Ce qu'on supprime est l'orientation, pas la verification.
MAPPED = f"""{OPEN}
{{digest}}
{CLOSE}

A session read this repository for you and wrote the map above, so you do not
have to orient yourself: no directory listing, no search for where something
lives, no re-reading of CLAUDE.md or the docs. Open a file only to confirm an
exact detail the map does not carry — a signature, a field name, the precise
wording of a constraint — and only where your answer actually depends on it.
If the map and the code disagree, the code wins and you say so in what you
write."""

# Pas de carte : ce que les six templates disaient chacun a leur facon. Dit
# une fois, et symetrique de l'autre — un bloc qui se nomme, pour qu'une
# etape sache qu'elle est dans ce cas-la et non que l'injection a casse.
UNMAPPED = """--- REPO MAP (not established for this run) ---
No map was established, so ground what you write in the repository yourself
rather than guessing: CLAUDE.md carries the constraints that are not visible
in the code, docs/ARCHITECTURE.md the technical design, docs/PROJECT.md the
product, and the code the task touches carries the rest. Read whatever you
need. Naming a module that does not exist is worse than naming none.
--- END REPO MAP ---"""


EXPLORE_PROMPT = """You are establishing the map of this repository that every later session of
this run will work from. You write it once; five or six paid sessions read it
instead of exploring on their own. Nothing else in this run will read the
repository from scratch, so what you leave out is what they will not know.

Here is what this run is working on:
<subject>
{subject}
</subject>

Below is the repository's own documentation, verbatim, plus the list of every
file git tracks. You do not need to open any of these — they are already
here. Read the **code** that the subject above actually touches, and only
that: the modules it names or implies, their neighbours, and the tests that
cover them.

<repository>
{brief}
</repository>

Write the map. It has to fit in about {budget} characters, so it is a map and
not a copy — every line that does not change what a later session would write
is a line that costs five sessions something and buys them nothing. Cover, in
this order and under these exact headings:

### Constraints
The rules from CLAUDE.md that bear on this subject, stated as rules. Quote a
constraint verbatim where its precise wording is what matters; summarise the
rest. Leave out what this subject cannot touch.

### Where things live
The modules the subject touches, by real path, and what each one is for in a
sentence. Name the layer boundaries that apply and what they forbid. This is
the section that makes a later session able to name a file without looking.

### Signatures and shapes
The functions, classes, types and fields a later session would have to name
to write a plan: their real names, their arguments, what they return. Exact
spelling matters more than completeness here — a name that is almost right
sends someone looking for it.

### Commands
The commands this repository actually runs to build, test, lint and verify,
copied from where they are documented rather than guessed.

### What is already true
What exists today that the subject assumes does not, or assumes differently:
a module already there, a convention already in force, a decision already
made. Be specific, and say where you saw it. This section is the one that
stops a later session from planning work that is already done.

Output the map and nothing else — no preamble, no closing remark, no code
fence around the whole answer. Use the four `### ` headings above, exactly as
spelled. Never write a level-2 heading (`## `): what you write is spliced
into prompts whose own structure uses them.

Change no file, run no command that writes, post no comment, touch no issue
and no label. You are reading.

The issues of this repository are public and what you write here flows into
them. Never write the value of a secret, a token, a key, a password, or a URL
that carries one — name the variable and say where it lives."""
