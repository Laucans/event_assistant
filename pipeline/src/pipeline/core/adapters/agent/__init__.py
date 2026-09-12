"""Une session d'agent, quel que soit le fournisseur qui la rend.

`base` porte l'interface (`AgentRunner`) et le resultat neutre
(`AgentResult`) ; `claude_sdk` en est l'implementation, et le seul module du
paquet qui importe `claude_agent_sdk`.

`default_runner()` est le point ou une seconde implementation se brancherait.
Il n'y en a qu'une aujourd'hui, et elle est choisie ici plutot que lue dans
l'environnement : un reglage pour un choix qui n'existe pas encore serait un
bouton qui ne fait rien.
"""

from __future__ import annotations

from pipeline.core.adapters.agent.base import AgentResult, AgentRunner, failure_reason
from pipeline.core.runtime.filesystem.workspace import Workspace

__all__ = ["AgentResult", "AgentRunner", "default_runner", "failure_reason"]


def default_runner(workspace: Workspace) -> AgentRunner:
    """Le moteur d'agent que la boucle utilise faute d'en recevoir un autre.

    Import tardif : `adapters.agent` est sur le chemin rapide via `progress`,
    et `claude_sdk` ne doit etre charge que quand une session part vraiment.
    """
    from pipeline.core.adapters.agent.claude_sdk import ClaudeSdkRunner

    return ClaudeSdkRunner(workspace)
