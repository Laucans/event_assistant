"""L'etat d'un round : ce qu'une reprise doit retrouver.

Six membres ont disparu avec le moteur de graphe — `stopped`, `stop_status`,
`stop_reason`, `record()`, `halt` et `starts_a_round()`. Aucun ne decrivait le
round : ils portaient son **arret**, parce qu'un noeud qui rendait un echec
n'arretait rien tout seul et que le noeud suivant devait pouvoir le lire pour
ne pas partir. Une sequence qui rend au premier echec n'a rien a se
transmettre.
"""

from __future__ import annotations

from pydantic import BaseModel


class RoundState(BaseModel):
    """L'etat d'un round, tel qu'une reprise le relit.

    Les corps des deux issues y sont : c'est la portee que chaque stage
    recoit, et une reprise doit la retrouver telle quelle plutot que
    dependre de ce que l'API repondra la prochaine fois.

    Ecrit apres chaque etape terminee — gardes comprises —, jamais au milieu
    de l'une : une etape est atomique, une demi-etape ne se reprend pas.
    """

    id: str = ""
    task_num: str = ""
    task_title: str = ""
    task_body: str = ""
    task_key: str = ""
    kind: str = "auto"
    milestone_num: str = ""
    milestone_title: str = ""
    milestone_body: str = ""
    spec_written: bool = False
    stages_done: list[str] = []
    rollover: bool = False
