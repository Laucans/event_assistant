"""Ce qui doit tenir avant qu'une revue depense une passe.

La revue n'avait **aucune** porte : elle lisait la PR, et decouvrait qu'elle
ne pouvait pas parler a GitHub une fois `claude` deja facture. Les trois
portes communes coutent trois appels locaux et evitent exactement ca.

Elles viennent de `common.checks`, et c'est tout l'interet de les y
avoir mises : la boucle les exigeait deja, la revue les exige maintenant
aussi, et personne n'a eu a les reecrire.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common import checks
from pipeline.workflows.common.checks import Check
from pipeline.workflows.pr_review.settings import ReviewConfig

# Ce qu'une revue exige : les outils, et rien de plus. Elle ne touche aucune
# branche et n'ecrit rien dans l'arbre de travail — exiger un arbre propre ou
# une branche d'integration a jour refuserait de relire une PR pour une raison
# qui ne la concerne pas.
CHECKS: tuple[Check, ...] = checks.TOOLING


@dataclass
class ReviewPreconditions:
    """Les portes de la revue, dans la forme que le contrat appelle."""

    cfg: ReviewConfig
    log: Logbook

    def verify(self) -> Result[None]:
        """Rend la premiere condition qui empeche la revue de tourner."""
        return checks.verify_all(CHECKS, self.cfg, self.log)
