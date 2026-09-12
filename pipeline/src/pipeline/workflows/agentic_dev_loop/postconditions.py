"""Ce que la boucle doit avoir obtenu pour qu'on la dise terminee.

**Vide, et c'est un constat plutot qu'un oubli.** Ce que la boucle garantit
se garantit par round, pas par run : qu'une task soit livree, que `/planner`
ait ouvert de quoi travailler, que le SPEC soit dans le corps de l'issue.
Chacune est la post-condition d'un **noeud** du graphe, verifiee au moment ou
le noeud finit — donc avant que le suivant soit paye — et elles vivent avec
lui, dans `internals.gates`.

Les verifier une seconde fois ici ne dirait rien de plus : un run qui arrive
au bout est un run dont chaque round a deja passe les siennes, et un run qui
s'arrete n'atteint pas cette classe — la sequence du contrat ne verifie pas
les postconditions d'un travail qui a echoue.

La classe existe quand meme parce que tout workflow porte les memes classes a
sa racine. Le jour ou le run entier devra garantir quelque chose — que le
budget de rounds a ete depense, que rien n'est reste verrouille — c'est ici,
et l'endroit est deja nomme.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.common.contract.outcome import WorkflowOutcome


@dataclass
class LoopPostconditions:
    """Rien a verifier apres un run. Les post-conditions sont par round."""

    cfg: RunConfig
    log: Logbook

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        return Result.of(None)
