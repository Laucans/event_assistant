"""Ce que toute configuration de workflow porte.

Le sous-ensemble que `RunConfig` et `ReviewConfig` avaient en commun, ecrit
une fois. Ce qui reste propre a chacun — la table du pipeline d'un cote, les
modeles des deux passes de l'autre — reste chez lui : cette classe est ce que
la sequence et les portes communes savent lire, pas un fourre-tout.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.core.runtime.filesystem.workspace import Workspace


@dataclass
class WorkflowConfig:
    """Ce qui varie d'un run a l'autre, quel que soit le workflow."""

    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    # A quelle frequence un travail long dit qu'il est encore vivant, en
    # secondes. Un stage peut passer des minutes dans un seul appel d'outil,
    # donc le battement est sur une horloge et non sur l'arrivee d'un message ;
    # 0 l'eteint.
    heartbeat_s: float = 60.0
    workspace: Workspace = field(default_factory=Workspace.here)
