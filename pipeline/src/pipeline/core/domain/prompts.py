"""Le preambule, le bloc de portee, et comment ils se composent.

Ce que **toute** session recoit, quel que soit le workflow qui la lance :
le bloc EXECUTION CONTEXT — la ou il est dit qu'on ne peut poser aucune
question, comment s'arreter, et sur quelle branche on travaille — et le bloc
SCOPE, qui porte le milestone et l'issue. Les consignes propres a un stage
s'ajoutent a ca et ne sont pas ici : elles voyagent dans
`StageSpec.instructions`.

Le preambule et les blocs de portee ont ete repris caractere pour caractere
de l'ancien `scripts/agent-loop.sh` : c'est ce qui rend demontrable, par
diff, que la migration n'a rien change a ce que les stages recoivent. La
seule difference voulue est le nom de l'injecteur.

**Ce module ne connait aucun workflow.** La prose d'un stage lui est passee
en argument ; le registre `definitions` qui vivait a cote indexait des noms
de stages d'un workflow precis, ce qui faisait du vocabulaire qui nomme une
instance. Il vit maintenant dans `workflows/<nom>/stages/`.

Le preambule exige `AGENT_LOOP_OK:` en fin de reponse et
`outcomes.stage_result.read_markers` le lit : deux moities d'un meme
contrat, et un test exige qu'elles nomment la meme chaine.
"""

# Le nom cite dans le preambule quand l'appelant n'en donne pas d'autre.
# Ancienne valeur : "scripts/agent-loop.sh", qui nommait le script. Un
# workflow passe le sien, declare a cote de sa table ; ce defaut est
# volontairement generique, parce que nommer ici la CLI d'un workflow precis
# serait exactement l'instance-dans-le-vocabulaire que cette couche n'a pas
# le droit de porter.
INJECTOR = "the pipeline runner"

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


def extra_for(instructions: str, num: str = "", title: str = "", *,
              milestone: str = "", scope: str = "") -> str:
    """L'`extra` d'un stage : ses consignes, puis la portee ou il travaille.

    La portee vient en dernier parce que c'est la partie longue — les
    consignes restent la ou un lecteur (et un modele) les trouve, en haut. Un
    stage sans consignes recoit quand meme sa portee : /create-test n'en a
    pas, et serait sinon la seule session payee du round qui ignore quelle
    task elle teste.

    Les consignes arrivent en argument, pas par un nom de stage : ce module
    ne connait aucune table et n'a donc rien a chercher.
    """
    body = fill(instructions, num=num, title=title, milestone=milestone)
    if not scope:
        return body
    return f"{body}\n\n{scope}" if body else scope
