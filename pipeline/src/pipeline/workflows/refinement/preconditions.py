"""Ce qui doit tenir avant qu'un round de raffinage depense une session.

Les trois portes communes, plus l'etiquette que le raffinage lit. Pas de
porte de branche ni d'arbre propre : le raffinage n'ecrit rien dans l'arbre
de travail, et l'exiger refuserait de raffiner une issue pour une raison qui
ne la concerne pas.
"""

from __future__ import annotations

from pipeline.core.adapters import hub
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common import checks, labels
from pipeline.workflows.common.checks import Check


def refinement_label_exists(cfg, log: Logbook) -> Result[None]:
    """L'etiquette que le raffinage lit doit exister sur le depot.

    Une etiquette absente ne fait echouer personne : la porte d'entree la
    trouverait simplement absente de l'issue et refuserait chaque round, sans
    dire que c'est le depot qui ne la porte pas.
    """
    known = hub.gh(cfg.workspace).labels()
    if known.failed:
        return known.recast()
    if labels.REFINEMENT not in known.value:
        return Result.halt(
            f"the repository is missing the label {labels.REFINEMENT} —"
            f" create it with: gh label create {labels.REFINEMENT}")
    return Result.of(None)


CHECKS: tuple[Check, ...] = (
    *checks.TOOLING,
    Check("refinement-label", refinement_label_exists),
)
