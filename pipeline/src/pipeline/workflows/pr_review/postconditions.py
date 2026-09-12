"""Ce que la revue doit avoir obtenu pour qu'on la dise terminee.

**Vide, et c'est un constat plutot qu'un oubli.** Ce qu'une revue garantit,
elle le garantit en chemin : que la passe 1 ait rendu quelque chose, que la
passe 2 ait produit un corps, que `gh` ait accepte le commentaire. Chacune est
verifiee la ou elle peut encore changer la suite — ne pas payer la passe 2
quand la 1 a epuise le quota, ne rien poster quand la 2 n'a rien rendu — et
les reverifier ici ne dirait rien de plus.

Une revue **sautee** est un succes, pas un manquement : une PR en brouillon
ou deja revue n'a rien a obtenir. Une post-condition qui exigerait un
commentaire poste ferait echouer exactement les cas que les regles de saut
existent pour laisser passer.

La classe existe quand meme parce que tout workflow porte les memes classes a
sa racine. Le jour ou la revue devra garantir quelque chose apres coup — que
le verrou est bien retombe, par exemple — c'est ici.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common.contract.outcome import WorkflowOutcome
from pipeline.workflows.pr_review.settings import ReviewConfig


@dataclass
class ReviewPostconditions:
    """Rien a verifier apres une revue : tout l'est en chemin."""

    cfg: ReviewConfig
    log: Logbook

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        return Result.of(None)
