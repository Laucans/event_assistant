"""Les formes que prend le milieu d'un workflow.

Un workflow est un sandwich : les portes en haut, la post-verification en
bas, et entre les deux ce qui depense. Le haut et le bas sont les memes pour
tous — `contract.sequence` les tient. Le milieu ne l'est pas : la boucle
repete une unite reprenable, la revue enchaine ses passes une fois.

Deux formes suffisent a les dire, et elles sont ici parce qu'aucune n'est
propre a un workflow : `once` et `repeat`. Un workflow qui ne rentre dans
ni l'une ni l'autre ecrit son `execute()` a la main — `contract.Workflow`
reste un `Protocol`, donc l'echappatoire ne coute rien et le lanceur ne voit
pas la difference. C'est ce qui separe une facilite d'un carcan.

Ce que ces formes ne sont **pas** : un moteur. Elles n'ont ni noeuds, ni
declenchement, ni etat d'arret a se transmettre — une sequence rend au
premier echec, et une repetition s'arrete sur ce qu'une unite lui rend. Le
seul vrai branchement d'un workflow reste un `if` chez lui.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pipeline.core.domain.action import Action
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.runtime.monitoring.logbook import Logbook

if TYPE_CHECKING:      # `Ctx` et `StageRunner` tirent le moteur d'agent, et
    # ce module est sur le chemin rapide : un blueprint nomme `Shape`, donc
    # `--status` et `--costs` importent ceci. Les deux ne servent qu'a
    # l'annotation — les charger ferait payer le moteur pour imprimer deux
    # lignes.
    from pipeline.core.execution.context import Ctx
    from pipeline.core.execution.stage_runner import StageRunner


@runtime_checkable
class Shape(Protocol):
    """Comment le milieu d'un workflow tourne."""

    async def run(self, cfg: Any, log: Logbook, *,
                  log_dir: Path) -> WorkflowOutcome:
        """Le travail, entre les deux gardes du contrat."""
        ...


class Threaded(Protocol):
    """Ce qu'une sequence exige de l'etat qu'elle file entre ses etapes.

    Le lanceur de stages lit et allonge cette liste pour ne payer une etape
    qu'une fois par unite de travail, tous runs confondus.
    """

    stages_done: list[str]


async def perform(step, runner: "StageRunner", ctx: "Ctx", state: Threaded, *,
                  extra=None) -> Result[None]:
    """Fait tourner une etape, qu'elle paie une session ou non.

    Le seul endroit du paquet qui distingue les deux sortes. `run_sequence`
    ne les distingue pas — il recoit cette fonction — et c'est ce qui permet
    a une table de melanger un stage et un appel local sans que la sequence
    ait a le savoir.

    Ce qu'une etape payante rend est garde dans `ctx.results`, sous son nom :
    c'est par la qu'une passe alimente la suivante.
    """
    if isinstance(step, Action):
        got = step.do(ctx, state)
        # Une action locale est sync ou async selon ce qu'elle appelle : le
        # choix de la task ne rend la main a personne, le rollover paie une
        # session. Les deux sont des etapes de la meme table.
        if inspect.isawaitable(got):
            got = await got
        return got
    ran = await runner.run(step, done=state.stages_done,
                           extra=extra(step, ctx, state) if extra else "")
    if not ran.failed:
        ctx.results[step.skill] = ran.value
    return ran
