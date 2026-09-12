"""Le round, exprime comme un graphe.

Un noeud par stage : la sequence se lit dans le code au lieu d'avoir a etre
deduite d'une boucle sur une table. C'est le **design** du round —
l'enchainement, et les post-conditions qui disent qu'un stage a vraiment fait
ce qu'on lui demandait. Ce qui fait *tourner* un stage vit a cote, dans
`execution.stage_runner` : ici on lit le pipeline, la-bas on lit une panne.

Aucun nom de moteur n'apparait dans ce fichier. `Flow`, `start`, `listen` et
`router` viennent de `adapters.engine`, qui est le seul endroit du paquet ou
une implementation est choisie.

Deux noeuds ont disparu avec le passage aux issues, et c'est le meme
mouvement les deux fois : ce que la boucle verifiait dans un fichier, GitHub
le porte.

- la **porte humaine** n'existe plus. Une action humaine est une issue
  `pipeline:human` dans les `blocked_by` d'une task, donc une task qui
  attend un humain n'est simplement pas choisie. Il n'y a plus d'endroit ou
  la barriere pourrait tomber au mauvais moment ;
- l'**archivage** n'existe plus. Une task se ferme parce que la PR de `/code`
  a merge avec `Closes #N`. Qui ferme depend de la branche : GitHub le fait
  au merge dans la branche par defaut, et sur `INTEGRATION_BRANCH` c'est le
  round qui ferme apres avoir retrouve la PR mergee. Dans les deux cas la
  preuve exigee est la meme — une PR mergee, pas la parole d'un stage.

La boucle sur les rounds reste du Python ordinaire dans `loop` : un
Flow decrit un graphe, pas une repetition, et forcer les rounds dedans
n'aurait rendu service a personne.

**Chaque noeud s'ouvre sur la meme garde**, et elle paie sa place : depuis
que les arrets sont des `Result` et non des exceptions, un noeud qui rend un
echec n'arrete plus rien tout seul — le moteur declenche le suivant, qui
paierait sa session. `if self.state.stopped: return` est ce qui l'empeche, et
le chemin d'arret se lit desormais dans le graphe au lieu de le traverser.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adapters.engine import (
    Flow, listen, persisted, quiet_panels, router, start)
from pipeline.domain import tasks
from pipeline.domain.prompts import prompt_builder as prompts
from pipeline.domain.stages import agentic_dev_loop_stages as table
from pipeline.domain.stages.stage_spec import StageSpec
from pipeline.domain.outcomes.result import Result
from pipeline.execution.context import Ctx
from pipeline.execution.stage_runner import StageRunner
from pipeline.workflows.agentic_dev_loop.internals import board, gates
from pipeline.workflows.agentic_dev_loop.internals.board import Board
from pipeline.workflows.agentic_dev_loop.internals.state import RoundState
from pipeline.workflows.common.utils import hub


@dataclass
class RoundCtx(Ctx):
    """Le contexte d'un round : celui de l'execution, plus le tableau d'issues.

    Le tableau d'issues en fait partie : la boucle l'a lu pour decider sous
    quelle cle reprendre, et le round s'en sert pour choisir sa task puis
    pour reetiqueter l'issue. Le passer ici plutot que de le relire evite une
    seconde salve d'appels d'API par round — et evite surtout que les deux
    lectures ne repondent pas la meme chose.
    """

    board: Board | None = None


def _spec(pipeline: tuple[StageSpec, ...], skill: str) -> Result[StageSpec]:
    """L'entree de PIPELINE qu'un noeud fait tourner, nommee plutot que supposee.

    La seule facon d'arriver ici est d'avoir renomme une entree dans la table
    sans renommer le noeud : le message le dit, et nomme ce que la table
    contient reellement.
    """
    spec = table.spec_of(skill, pipeline)
    if spec is None:
        return Result.halt(f"PIPELINE has no {skill!r} entry, but the round"
                           f" graph runs one — the table in"
                           f" domain/stages/agentic_dev_loop_stages.py names:"
                           f" {table.names(pipeline)}")
    return Result.of(spec)


def _scope(st: RoundState) -> str:
    """La portee injectee dans le prompt de ce stage.

    Une session ne demarre jamais sans elle : c'est le seul endroit ou le
    stage apprend de quel milestone et de quelle issue il parle, depuis que
    ni l'un ni l'autre n'est un fichier du depot.
    """
    return prompts.scope(
        milestone=st.milestone_num, milestone_title=st.milestone_title,
        milestone_body=st.milestone_body, num=st.task_num,
        title=st.task_title, body=st.task_body)


def _extra(stage: str, st: RoundState) -> str:
    """Les consignes de ce stage, plus la portee du round."""
    return prompts.extra_for(stage, st.task_num, st.task_title,
                             milestone=st.milestone_num, scope=_scope(st))


# --- le travail de chaque noeud, hors du graphe ----------------------------
#
# Les decorateurs du moteur doivent porter sur des methodes de la classe de
# flow ; ce qu'elles font vit ici, ou cela se lit et s'exerce sans monter un
# flow entier.


def _pick_task(ctx: RoundCtx, runner: StageRunner,
               st: RoundState) -> Result[None]:
    """Choisit la task du round, ou bascule en rollover."""
    # Le premier noeud du round, donc le seul endroit ou l'arret du round
    # precedent peut etre oublie avant qu'une garde ne le lise.
    st.starts_a_round()
    # La boucle a deja lu le tableau pour savoir sous quelle cle reprendre :
    # le relire couterait une poignee d'appels d'API pour une reponse qu'on
    # tient deja.
    if ctx.board is None:
        read = board.read(hub.gh(ctx.workspace))
        if read.failed:
            return st.record(read)
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
            return st.record(Result.halt(here.stuck()))
        st.rollover = True
        ctx.log(f"milestone {here.milestone.ref} has no open"
                f" {tasks.AGENT} sub-issue — opening the next roadmap item")
        return Result.of(None)
    st.task_num, st.task_title = str(task.number), task.title
    st.task_key, st.kind = task.key, task.kind
    st.task_body = task.body
    st.spec_written = task.spec_written
    runner.about(task.key)
    ctx.log(f"task {task.ref}: {task.title} [{task.kind}]")
    return Result.of(None)


async def _run_planner(ctx: RoundCtx, runner: StageRunner,
                       st: RoundState) -> Result[None]:
    """Ouvre l'item de roadmap suivant, quand le milestone est fini."""
    cfg = ctx.cfg
    if cfg.rollover is None or not cfg.enabled(cfg.rollover):
        ctx.log("no planner entry in PIPELINE — nothing left to do")
        return Result.of(None)
    # Pas de portee ici, et c'est le seul stage dans ce cas : le planner ne
    # travaille sur aucune task — il en ouvre. Lui injecter un bloc ISSUE
    # vide lui donnerait une task a chercher.
    ran = await runner.run(cfg.rollover, done=st.stages_done,
                           extra=prompts.extra_for(
                               "planner", milestone=st.milestone_num))
    if ran.failed:
        return st.record(ran)
    if not cfg.dry_run:
        held = gates.planner_opened_a_task(ctx.board.gh, st)
        if held.failed:
            return st.record(held)
    return Result.of(None)


async def _run_business_analyst(ctx: RoundCtx, runner: StageRunner,
                                st: RoundState) -> Result[None]:
    """Ecrit le SPEC dans le corps de l'issue."""
    cfg = ctx.cfg
    found = _spec(cfg.pipeline, "business-analyst")
    if found.failed:
        return st.record(found)
    spec = found.value
    # Un stage ecarte par --stages n'a pas de post-condition a tenir : le
    # shell sautait tout l'emballage, pas seulement son appel.
    if runner.filtered(spec):
        return Result.of(None)
    # L'etiquette remplace le `docs/current/SPEC.md` d'avant : elle dit que
    # le SPEC a ete ecrit dans le corps de l'issue, donc qu'un run interrompu
    # reprend apres ce stage plutot que de payer une seconde redaction
    # par-dessus la premiere.
    if st.spec_written:
        ctx.log(f"issue #{st.task_num} already carries {tasks.SPEC_WRITTEN}"
                f" — skipping /business-analyst (resuming a previous run)")
        return Result.of(None)
    ran = await runner.run(spec, done=st.stages_done,
                           extra=_extra("business-analyst", st))
    if ran.failed:
        return st.record(ran)
    if not cfg.dry_run:
        held = gates.spec_is_in_the_issue(ctx.board.gh, st)
        if held.failed:
            return st.record(held)
    return Result.of(None)


def _already_shipped(ctx: RoundCtx, st: RoundState) -> Result[bool]:
    """La PR de ce /code a-t-elle deja merge ?

    Seulement sur un round repris : sur un round neuf /code n'a jamais
    tourne, et la recherche de PR couterait un appel par round pour une
    reponse connue d'avance.
    """
    cfg = ctx.cfg
    if ctx.board.resuming is None or cfg.dry_run or cfg.restart:
        return Result.of(False)
    return gates.already_delivered(ctx.board.gh, int(st.task_num),
                                   cfg.integration_branch)


async def _run_code(ctx: RoundCtx, runner: StageRunner,
                    st: RoundState) -> Result[None]:
    """Planifie puis ecrit le changement, et ouvre sa PR."""
    cfg = ctx.cfg
    found = _spec(cfg.pipeline, "code")
    if found.failed:
        return st.record(found)
    spec = found.value
    if runner.filtered(spec):
        return Result.of(None)
    shipped = _already_shipped(ctx, st)
    if shipped.failed:
        return st.record(shipped)
    if shipped.value:
        ctx.log(f"#{st.task_num} est deja livree sur"
                f" {cfg.integration_branch} — /code saute plutot que d'etre"
                f" repaye (--restart pour le rejouer)")
        return Result.of(None)
    has_spec = gates.code_has_a_spec(cfg, st.task_num, st.task_body)
    if has_spec.failed:
        return st.record(has_spec)
    ran = await runner.run(spec, done=st.stages_done, extra=_extra("code", st))
    if ran.failed:
        return st.record(ran)
    return Result.of(None)


async def _run_create_test(ctx: RoundCtx, runner: StageRunner,
                           st: RoundState) -> Result[None]:
    """Ajoute la couverture que le lot merite."""
    found = _spec(ctx.cfg.pipeline, "create-test")
    if found.failed:
        return st.record(found)
    ran = await runner.run(found.value, done=st.stages_done,
                           extra=_extra("create-test", st))
    if ran.failed:
        return st.record(ran)
    return Result.of(None)


def build_flow(ctx: RoundCtx):
    """Construit la classe de flow de ce run.

    Une fabrique plutot qu'une classe au niveau du module, pour deux raisons :
    le contexte (config, journal) est tenu par le lanceur de stages au lieu de
    devoir vivre dans un etat qui reste serialisable, et la persistance est
    choisie a l'execution — un dry-run n'ecrit rien, comme avant.
    """
    quiet_panels(ctx.log)
    cfg = ctx.cfg
    runner = StageRunner(ctx)

    class RoundFlow(Flow[RoundState]):
        """business-analyst -> code -> create-test -> l'issue s'est fermee.

        Chaque noeud s'ouvre sur `if self.state.stopped: return`. Ce n'est pas
        de la ceinture et des bretelles : le moteur declenche le noeud suivant
        des que le precedent rend la main, quelle que soit sa valeur de
        retour. Sans cette garde, un `/code` qui s'arrete laisserait partir
        `/create-test` — une session payante de plus, sur une task qu'on vient
        justement de renoncer a livrer.
        """

        @start()
        def pick_task(self) -> None:
            _pick_task(ctx, runner, self.state)

        @router(pick_task)
        def route(self) -> str:
            """Le seul point de decision de la branche.

            Trois sorties, dont une muette : « stop » n'est ecoute par aucun
            noeud, donc le graphe s'arrete la. C'est la facon la plus courte
            de dire « ce round ne va nulle part » a un moteur qui, sinon,
            enchainerait.
            """
            if self.state.stopped:
                return "stop"
            return "rollover" if self.state.rollover else "task"

        @listen("rollover")
        async def planner(self) -> None:
            await _run_planner(ctx, runner, self.state)

        @listen("task")
        async def business_analyst(self) -> None:
            await _run_business_analyst(ctx, runner, self.state)

        @listen(business_analyst)
        async def code(self) -> None:
            if self.state.stopped:
                return
            await _run_code(ctx, runner, self.state)

        @listen(code)
        async def create_test(self) -> None:
            if self.state.stopped:
                return
            await _run_create_test(ctx, runner, self.state)

        @listen(create_test)
        def task_delivered(self) -> None:
            if self.state.stopped:
                return
            found = _spec(cfg.pipeline, "code")
            if found.failed:
                self.state.record(found)
                return
            delivered = gates.task_is_delivered(cfg, ctx.board.gh, ctx.log,
                                                self.state, found.value)
            if delivered.failed:
                self.state.record(delivered)

    if cfg.dry_run:
        # Un dry-run lit l'etat — pour prevoir les vrais sauts — mais ne
        # l'ecrit jamais, sinon la prevision detruirait le point de reprise
        # qu'elle decrit.
        return RoundFlow
    return persisted(RoundFlow, ctx.workspace.flow_db)
