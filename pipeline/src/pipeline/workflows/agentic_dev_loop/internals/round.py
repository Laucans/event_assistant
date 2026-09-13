"""Un round : choisir la task, faire tourner la sequence, constater la livraison.

**La sequence n'est pas ici.** Elle est dans `stages/`, une entree par etape,
et `run_sequence` la parcourt. Ce module porte ce qui l'entoure : ce qui est
vrai avant qu'aucune etape ne parte, la branche de rollover, et la
post-condition qui suit.

Ce fichier remplace un graphe. Un moteur y decrivait quatre noeuds dont trois
etaient des stages a la queue leu leu, et se payait en trois endroits : un
`if self.state.stopped: return` en tete de chaque noeud — le moteur declenche
le suivant quelle que soit la valeur de retour —, six membres de `RoundState`
qui n'existaient que pour porter cet arret, et 1,6 s d'import que tout le
reste du paquet devait ensuite eviter. Une fonction qui rend au premier echec
n'a besoin d'aucun des trois.

Ce qui reste du graphe, et ce qui n'en avait jamais eu besoin :

    pick_task
      |
      +-- pas de task, aucune ouverte ..... rollover : /planner
      +-- pas de task, des ouvertes ....... arret : dire quel geste debloque
      +-- une task ........................ PIPELINE, puis DELIVERED

Un `if/elif/else`. Le routeur du graphe avait trois sorties dont une muette,
parce que c'etait la facon la plus courte de dire « ce round ne va nulle
part » a un moteur qui, sinon, enchainait.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.core.adapters import hub
from pipeline.core.domain import prompts
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.execution.context import Ctx
from pipeline.core.execution.stage_runner import StageRunner
from pipeline.core.execution.steps import run_sequence
from pipeline.workflows.agentic_dev_loop.internals import board, tasks
from pipeline.workflows.agentic_dev_loop.internals.board import Board
from pipeline.workflows.agentic_dev_loop.internals.state import RoundState
from pipeline.workflows.agentic_dev_loop.stages import DELIVERED, INJECTOR


@dataclass
class RoundCtx(Ctx):
    """Le contexte d'un round : celui de l'execution, plus le tableau d'issues.

    Le tableau en fait partie : la boucle l'a lu pour decider sous quelle cle
    reprendre, et le round s'en sert pour choisir sa task puis pour
    reetiqueter l'issue. Le passer ici plutot que de le relire evite une
    seconde salve d'appels d'API par round — et evite surtout que les deux
    lectures ne repondent pas la meme chose.

    `gh` et `resuming` sont ce que les gardes lisent : elles prennent toutes
    la meme paire `(ctx, st)`, et c'est ce qui permet a la table de les
    porter.
    """

    board: Board | None = None

    @property
    def gh(self):
        return self.board.gh

    @property
    def resuming(self) -> bool:
        return self.board is not None and self.board.resuming is not None


def _scope(st: RoundState) -> str:
    """La portee injectee dans le prompt de ce stage.

    Une session ne demarre jamais sans elle : c'est le seul endroit ou le
    stage apprend de quel milestone et de quelle issue il parle, depuis que
    ni l'un ni l'autre n'est un fichier du depot.
    """
    return prompts.scope(
        milestone=st.milestone_num, milestone_title=st.milestone_title,
        milestone_body=st.milestone_body, num=st.task_num,
        title=st.task_title, body=st.task_body, injector=INJECTOR)


def _extra(stage, st: RoundState) -> str:
    """Les consignes de ce stage, plus la portee du round.

    Les consignes viennent de l'entree de table, pas d'un registre indexe par
    nom : c'est ce qui fait qu'un stage renomme ne peut pas perdre son texte
    en silence.
    """
    return prompts.extra_for(stage.instructions, st.task_num, st.task_title,
                             milestone=st.milestone_num, scope=_scope(st))


def pick_task(ctx: RoundCtx, runner: StageRunner,
              st: RoundState) -> Result[None]:
    """Choisit la task du round, ou bascule en rollover."""
    # La boucle a deja lu le tableau pour savoir sous quelle cle reprendre :
    # le relire couterait une poignee d'appels d'API pour une reponse qu'on
    # tient deja.
    if ctx.board is None:
        read = board.read(hub.gh(ctx.workspace))
        if read.failed:
            return read.recast()
        ctx.board = read.value
    here = ctx.board
    st.milestone_num = str(here.milestone.number)
    st.milestone_title = here.milestone.title
    st.milestone_body = here.milestone.body
    ctx.log(f"milestone {here.milestone.ref}: {here.milestone.title}")
    # Le point de reprise prime : un round interrompu apres le merge de
    # `/code` travaille sur une issue deja fermee, que plus rien n'offrirait.
    task = here.resuming or here.next
    if task is None:
        # Des tasks ouvertes mais aucune jouable n'est pas un rollover :
        # confondre les deux ferait payer un `/planner` pour une case
        # `pipeline:ready` que personne n'a cochee.
        if here.open_agents:
            return Result.halt(here.stuck())
        st.rollover = True
        ctx.log(f"milestone {here.milestone.ref} has no open"
                f" {tasks.AGENT} sub-issue — opening the next roadmap item")
        return Result.of(None)
    st.task_num, st.task_title = str(task.number), task.title
    st.task_key, st.kind = task.key, tasks.kind(task)
    st.task_body = task.body
    st.spec_written = tasks.spec_written(task)
    runner.about(task.key)
    ctx.log(f"task {task.ref}: {task.title} [{tasks.kind(task)}]")
    return Result.of(None)


async def run_planner(ctx: RoundCtx, runner: StageRunner,
                      st: RoundState) -> Result[None]:
    """Ouvre l'item de roadmap suivant, quand le milestone est fini."""
    cfg = ctx.cfg
    planner = cfg.rollover
    if planner is None or not cfg.enabled(planner):
        ctx.log("no planner entry in PIPELINE — nothing left to do")
        return Result.of(None)
    # Pas de portee ici, et c'est le seul stage dans ce cas : le planner ne
    # travaille sur aucune task — il en ouvre. Lui injecter un bloc ISSUE
    # vide lui donnerait une task a chercher.
    ran = await runner.run(planner, done=st.stages_done,
                           extra=prompts.extra_for(
                               planner.instructions,
                               milestone=st.milestone_num))
    if ran.failed:
        return ran
    if cfg.dry_run or planner.after is None:
        return Result.of(None)
    return planner.after(ctx, st)


async def run(ctx: RoundCtx, st: RoundState, *,
              save=None) -> Result[None]:
    """Un round entier. Rend l'echec qui l'a arrete, ou un succes.

    Plus de `stopped` a lire apres coup : un round qui s'arrete rend la
    raison, comme tout le reste du paquet. C'est ce que le moteur ne
    permettait pas — il rendait la main normalement quel que soit le sort du
    noeud, et l'arret devait voyager dans l'etat pour etre relu ensuite.
    """
    cfg = ctx.cfg
    runner = StageRunner(ctx)

    picked = pick_task(ctx, runner, st)
    if picked.failed:
        return picked
    if save is not None:
        save()
    if st.rollover:
        return await run_planner(ctx, runner, st)

    ran = await run_sequence(
        cfg.pipeline, ctx=ctx, state=st,
        run=lambda step: runner.run(step, done=st.stages_done,
                                    extra=_extra(step, st)),
        log=ctx.log, excluded=runner.filtered, save=save)
    if ran.failed:
        return ran
    return DELIVERED(ctx, st)
