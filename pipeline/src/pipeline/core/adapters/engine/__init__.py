"""Le moteur qui execute le graphe du round.

**La couture est ici** : c'est la seule ligne du paquet qui nomme une
implementation. Changer de moteur, c'est changer cet import —
`workflows.agentic_dev_loop.flow` decrit son graphe avec `Flow`, `start`,
`listen` et `router` sans savoir d'ou ils viennent.

Ce paquet importe crewai des qu'on le touche, donc rien sur le chemin rapide
ne doit l'importer. La lecture du magasin de reprise vit exprime ailleurs,
dans `adapters.store.resume`, en bibliotheque standard.
"""

from pipeline.core.adapters.engine.crewai_engine import (
    Flow, listen, persisted, quiet_panels, router, start)

__all__ = ["Flow", "listen", "persisted", "quiet_panels", "router", "start"]
