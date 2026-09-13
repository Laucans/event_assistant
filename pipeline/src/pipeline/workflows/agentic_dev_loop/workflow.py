"""La boucle de developpement agentique, declaree.

Ce fichier est la declaration entiere du workflow : sa config, ses portes, la
forme de son milieu, et ou tombent ses artefacts. Ce qui l'entoure — parcourir
les portes, annoncer, appeler la forme, verifier ce qui devait etre obtenu —
est monte par `core/design/build.py` et n'est plus recopie ici.

Ce qu'il n'y a plus : la classe, ses deux champs `init=False`, son
`__post_init__` qui cablait les deux gardes, et son `run()` qui deleguait a
`contract.sequence`. Les quatre etaient identiques d'un workflow a l'autre.

L'import du round reste tardif, dans `_round` : `internals.loop` tire
`adapters.agent` et coute ~100 ms. Le declarer au niveau module ferait payer
cette somme a `--status` et `--costs`, qui repondent en quelques dizaines de
millisecondes et n'ouvrent jamais un round.
"""

from __future__ import annotations

from pipeline.core.design.blueprint import Blueprint
from pipeline.core.execution.shapes.repeat import Repeat
from pipeline.workflows.agentic_dev_loop import preconditions
from pipeline.workflows.agentic_dev_loop.settings import RunConfig


async def _round(cfg: RunConfig, turn: int, log, log_dir, tally):
    """Un round. Importe le moteur ici, et nulle part avant."""
    from pipeline.workflows.agentic_dev_loop.internals import loop

    return await loop.one_round(cfg, turn, log, log_dir, tally)


WORKFLOW = Blueprint(
    name="loop",
    config=RunConfig,
    gates=preconditions.CHECKS,
    announce=preconditions.announce,
    # Chaque run a son dossier, nomme par son identifiant.
    artifacts=lambda cfg: cfg.workspace.loop_dir / cfg.run_id,
    shape=Repeat(
        unit=_round,
        budget=lambda cfg: cfg.max_rounds,
        exhausted="nothing left to open — stopping rather than replaying"
                  " the rollover",
        summary=lambda cfg, log_dir:
            f"loop finished — logs in {cfg.workspace.rel(log_dir)}",
    ),
    # Rien a verifier apres un run : ce que la boucle garantit se garantit par
    # round, dans `internals.gates`, au moment ou le round finit — donc avant
    # que le suivant soit paye. Le reverifier ici ne dirait rien de plus.
    obtained=None,
)
