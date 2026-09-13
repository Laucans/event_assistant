"""Un workflow, declare.

Ce que remplissaient jusqu'ici quatre modules a la racine d'un workflow,
dont trois ne portaient qu'une classe d'emballage recopiee d'un workflow a
l'autre. La config reste chez le workflow, parce qu'elle est du code ; ce que
les trois autres disaient tient maintenant dans les champs ci-dessous.

Rien ici n'importe un workflow : un `Blueprint` **recoit** ses portes et sa
forme. C'est ce qui permet a cette couche d'etre dans `core/` alors qu'elle
ne sert qu'a decrire des instances.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.core.execution.contract.gate import Check
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.core.execution.shapes import Shape
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook


@dataclass(frozen=True)
class Blueprint:
    """Tout ce qu'un workflow declare.

    `gates` sont ses preconditions, dans l'ordre ou elles se verifient.
    `obtained` est sa post-condition ; `None` veut dire « rien a verifier
    apres », ce qui est le cas des deux workflows en place et se lisait
    jusqu'ici en une classe vide plus un essai par workflow.

    `announce` est ce qui se dit une fois toutes les portes passees et avant
    que rien ne soit paye — ce que la boucle imprime sur sa branche, son
    budget et sa table.
    """

    name: str
    config: type
    shape: Shape
    # Ou tombent les artefacts de ce run. Une fonction de la config, parce que
    # celui de la boucle porte son `run_id` et celui de la revue non.
    artifacts: Callable[[Any], Path]
    gates: tuple[Check, ...] = ()
    obtained: Callable[[Any, Logbook, WorkflowOutcome], Result[None]] | None = None
    announce: Callable[[Any, Logbook], None] | None = None
