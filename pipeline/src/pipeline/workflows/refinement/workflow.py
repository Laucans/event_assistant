"""Le raffinage d'une issue, declare.

Meme forme que les deux autres `workflow.py` : la declaration entiere, et
rien d'autre. Un round est une sequence d'etapes qui s'arrete, donc la forme
`once`.
"""

from __future__ import annotations

from pipeline.core.design.blueprint import Blueprint
from pipeline.core.execution.shapes.once import Once
from pipeline.workflows.refinement import preconditions, stages
from pipeline.workflows.refinement.internals import refine
from pipeline.workflows.refinement.settings import RefinementConfig

WORKFLOW = Blueprint(
    name="refinement",
    config=RefinementConfig,
    gates=preconditions.CHECKS,
    # Un dossier par issue : les rounds d'une meme issue s'y empilent, et le
    # tag d'artefact les separe par numero de round.
    artifacts=refine.artifacts,
    shape=Once(
        plan=stages.passes,
        state=refine.RefinementState,
        extra=stages.prompt_of,
        precheck=refine.precheck,
        guard=refine.one_at_a_time,
        held=refine.already_running,
        summary=refine.summary,
        tally_as="refinement",
    ),
    # Rien a verifier apres : ce qu'un round garantit, il le garantit en
    # chemin — le gate de sortie du routeur, et l'etape de publication qui
    # propage chaque echec d'ecriture.
    obtained=None,
)
