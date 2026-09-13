"""Ce qu'un noeud du round exige avant de payer, et ce qu'il doit obtenir.

A ne pas confondre avec les `preconditions`/`postconditions` de la racine :
celles-la sont celles du **workflow**, verifiees une fois avant et apres le
run, et tout workflow en a. Celles-ci sont celles d'un **noeud du graphe** —
elles n'ont de sens qu'ici, dans le round, et c'est pourquoi elles vivent
avec lui.

Aucune ne leve : chacune rend un `Result` que le noeud propage. C'est ce qui
rend visible, dans `flow.py`, l'endroit exact ou le round s'arrete — et ce
qui garantit qu'un stage suivant n'est pas paye apres.
"""

from __future__ import annotations

from typing import Protocol

from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.internals import board, tasks
from pipeline.workflows.agentic_dev_loop.internals.state import RoundState


class RoundPolicy(Protocol):
    """Ce qu'une garde lit dans la config du run — pas `RunConfig` lui-meme.

    Un `Protocol` et non l'import, pour la meme raison que
    `execution.context.StagePolicy` : `settings` lit la table dans `stages/`,
    et c'est dans `stages/` que la sequence du round declare ses gardes. Sans
    cette couture, `stages` -> `gates` -> `settings` -> `stages` serait un
    cycle.
    """

    dry_run: bool
    restart: bool
    integration_branch: str
    stages: str

    def runs(self, skill: str) -> bool: ...


class RoundCtx(Protocol):
    """Ce qu'une garde lit du contexte du round.

    Les cinq gardes prennent **la meme paire** `(ctx, st)`, et c'est ce qui
    permet a la table de `stages/` de les porter : une entree ne peut
    declarer sa garde que si toutes les gardes s'appellent pareil. Elles
    avaient cinq signatures differentes, chacune taillee sur son appelant.
    """

    cfg: RoundPolicy
    log: Logbook

    @property
    def gh(self) -> GitHub: ...

    @property
    def resuming(self) -> bool:
        """Ce round reprend-il une task qu'un run precedent a entamee ?"""
        ...


def here_ref(st: RoundState) -> str:
    """`#12` — le milestone du round, tel qu'un message le nomme."""
    return f"#{st.milestone_num}"


# --- « c'est deja fait » : ce qui fait sauter une etape sans la payer -------
#
# Elles rendent la ligne a journaliser, ou la chaine vide pour laisser
# tourner. Un echec y arrete le round, et c'est voulu : « je ne sais pas si
# c'est deja fait » et « ce n'est pas fait » valent une session d'ecart.


def spec_already_written(ctx: RoundCtx, st: RoundState) -> Result[str]:
    """L'etiquette remplace le `docs/current/SPEC.md` d'avant.

    Elle dit que le SPEC a ete ecrit dans le corps de l'issue, donc qu'un run
    interrompu reprend apres ce stage plutot que de payer une seconde
    redaction par-dessus la premiere.
    """
    if not st.spec_written:
        return Result.of("")
    return Result.of(
        f"issue #{st.task_num} already carries {tasks.SPEC_WRITTEN}"
        f" — skipping /business-analyst (resuming a previous run)")


def code_already_delivered(ctx: RoundCtx, st: RoundState) -> Result[str]:
    """La PR de ce /code a-t-elle deja merge ?

    Seulement sur un round repris : sur un round neuf /code n'a jamais
    tourne, et la recherche de PR couterait un appel par round pour une
    reponse connue d'avance.
    """
    cfg = ctx.cfg
    if not ctx.resuming or cfg.dry_run or cfg.restart:
        return Result.of("")
    shipped = already_delivered(ctx, st)
    if shipped.failed:
        return shipped.recast()
    if not shipped.value:
        return Result.of("")
    return Result.of(
        f"#{st.task_num} est deja livree sur {cfg.integration_branch}"
        f" — /code saute plutot que d'etre repaye (--restart pour le"
        f" rejouer)")


# --- ce qu'un noeud exige avant de payer sa session ------------------------


def code_has_a_spec(ctx: RoundCtx, st: RoundState) -> Result[None]:
    """La portee du stage `code` : sans corps d'issue, il n'y a pas de SPEC."""
    # Une session ne demarre jamais sans sa portee : sans corps
    # d'issue, /code n'a pas de SPEC et improviserait la task.
    if not ctx.cfg.dry_run and not st.task_body.strip():
        num = st.task_num
        return Result.halt(f"issue #{num} has an empty body — there is"
                           f" no SPEC to build from. Run /business-analyst on"
                           f" it first (--stages business-analyst).")
    return Result.of(None)


# --- ce qu'un noeud doit avoir obtenu pour que le suivant parte ------------


def planner_opened_a_task(ctx: RoundCtx, st: RoundState) -> Result[None]:
    """Le rollover a ouvert de quoi travailler, sur le milestone d'apres."""
    # Relu depuis zero : le milestone en cours n'est peut-etre plus
    # le meme. Il ne le sera que si /planner a ferme celui qu'il
    # vient de terminer — la boucle travaille sur le milestone
    # ouvert de plus petit numero, donc un ancien laisse ouvert
    # ferait rouler tous les rounds suivants a vide.
    after = board.read(ctx.gh)
    if after.failed:
        return after.recast()
    if not after.value.open_agents:
        return Result.halt(
            f"/planner left nothing to pick up: milestone"
            f" {after.value.milestone.ref} still has no open"
            f" {tasks.AGENT} issue. Either it opened none, or it did"
            f" not close milestone {here_ref(st)} — the loop reads the"
            f" lowest-numbered open milestone, and that one is still"
            f" it.")
    return Result.of(None)


def spec_is_in_the_issue(ctx: RoundCtx, st: RoundState) -> Result[None]:
    """Le SPEC est dans le corps de l'issue, et l'etiquette le dit."""
    # Relu, pas suppose : le corps de l'issue *est* le SPEC, et c'est
    # ce que le stage suivant recevra dans sa portee.
    gh = ctx.gh
    issue = gh.issue(int(st.task_num))
    if issue.failed:
        return issue.recast()
    if not issue.value.body.strip():
        return Result.halt(f"/business-analyst left issue #{st.task_num} with"
                           f" an empty body — the SPEC goes there, and /code"
                           f" reads nothing else")
    st.task_body = issue.value.body
    labelled = gh.add_label(int(st.task_num), tasks.SPEC_WRITTEN)
    if labelled.failed:
        return labelled.recast()
    st.spec_written = True
    return Result.of(None)


def already_delivered(ctx: RoundCtx, st: RoundState) -> Result[bool]:
    """La task porte-t-elle deja la preuve d'une livraison ?

    La meme preuve que `task_is_delivered` exige, posee avant de payer plutot
    qu'apres : une PR **mergee** sur la branche d'integration, ou une issue
    que quelqu'un a deja fermee ou marquee.

    C'est le `skip` du stage `code` : la seule des cinq qui rende un booleen,
    parce qu'elle ne dit pas « ca ne va pas » mais « c'est deja fait ».
    """
    gh, num = ctx.gh, int(st.task_num)
    branch = ctx.cfg.integration_branch
    here = gh.issue(num)
    if here.failed:
        return here.recast()
    if here.value.closed or tasks.waiting_merge(here.value):
        return Result.of(True)
    merged = gh.merged_prs(branch)
    if merged.failed:
        return merged.recast()
    return Result.of(tasks.first_closing(merged.value, num) is not None)


def task_is_delivered(ctx: RoundCtx, st: RoundState) -> Result[None]:
    """La post-condition du round : la task est livree.

    Ce qu'on exige n'est pas qu'un stage l'affirme, mais qu'une PR
    **mergee** porte `Closes #N`. Sans ce constat, un run
    `--stages business-analyst` repayerait indefiniment la redaction
    du meme SPEC.

    Livree n'est pas fermee, et l'ecart est voulu. `Closes #N` ne
    ferme rien ici : GitHub ne ferme une issue liee qu'au merge dans
    la branche **par defaut**, et la boucle merge dans
    `INTEGRATION_BRANCH`. Plutot que de fermer a sa place — ce qui
    dirait « integre dans main » d'un travail qui n'y est pas — le
    round pose `pipeline:waiting-merge`. L'issue reste ouverte, ne
    sera plus jamais choisie, et ne bloque plus la suivante ; c'est
    l'humain qui la ferme en fusionnant la branche d'integration.

    Si GitHub l'a fermee malgre tout — le jour ou la branche
    d'integration devient la branche par defaut — on n'arrive pas
    jusqu'ici : les deux chemins disent la meme chose.
    """
    cfg, gh, log = ctx.cfg, ctx.gh, ctx.log
    if cfg.dry_run or not st.task_num:
        return Result.of(None)
    num = int(st.task_num)
    here = gh.issue(num)
    if here.failed:
        return here.recast()
    if here.value.closed or tasks.waiting_merge(here.value):
        return Result.of(None)
    merged = gh.merged_prs(cfg.integration_branch)
    if merged.failed:
        return merged.recast()
    shipped = tasks.first_closing(merged.value, num)
    if shipped is not None:
        log(f"#{num} livree par la PR #{shipped.number}, mergee"
            f" sur {cfg.integration_branch} — marquee"
            f" {tasks.WAITING_MERGE}, a vous de la fermer en"
            f" fusionnant dans la branche par defaut")
        return gh.add_label(num, tasks.WAITING_MERGE)
    left_out = "" if cfg.runs("code") else (
        f" --stages ({cfg.stages}) left /code out, and nothing else"
        f" delivers a task.")
    return Result.halt(f"issue #{num} ended the round and nothing marks it"
                       f" delivered — no merged PR on"
                       f" {cfg.integration_branch} carries `Closes #{num}` on"
                       f" its own line.{left_out} Stopping rather than"
                       f" looping on the same task.")
