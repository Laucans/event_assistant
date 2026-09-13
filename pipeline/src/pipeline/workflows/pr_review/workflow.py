"""La revue consultative d'une PR, declaree.

Meme fichier, meme forme que `agentic_dev_loop/workflow.py` : la declaration
entiere, et rien d'autre. Ce qui l'entoure est monte par
`core/design/build.py`.

Elle ne charge aucun moteur : une revue est une sequence de deux passes et
d'une publication, et c'est exactement ce que la forme `once` exprime.
"""

from __future__ import annotations

from pipeline.core.design.blueprint import Blueprint
from pipeline.core.execution.shapes.once import Once
from pipeline.workflows.pr_review import preconditions, stages
from pipeline.workflows.pr_review.internals import gates, review
from pipeline.workflows.pr_review.settings import ReviewConfig

WORKFLOW = Blueprint(
    name="pr-review",
    config=ReviewConfig,
    gates=preconditions.CHECKS,
    # Toutes les revues ecrivent dans le meme dossier : leurs artefacts sont
    # prefixes par le numero de la PR, pas par un identifiant de run.
    artifacts=lambda cfg: cfg.workspace.review_dir,
    shape=Once(
        plan=stages.passes,
        state=review.ReviewState,
        extra=stages.prompt_of,
        precheck=review.precheck,
        guard=review.one_at_a_time,
        held=review.already_running,
        tolerate=gates.a_silent_inline_pass_is_not_fatal,
        summary=review.summary,
        tally_as="review",
    ),
    # Rien a verifier apres : ce qu'une revue garantit, elle le garantit en
    # chemin — ne pas payer la passe 2 quand la 1 a epuise le quota, ne rien
    # poster quand la 2 n'a rien rendu. Et une revue **sautee** est un succes :
    # une post-condition qui exigerait un commentaire poste ferait echouer
    # exactement les cas que les regles de saut existent pour laisser passer.
    obtained=None,
)
