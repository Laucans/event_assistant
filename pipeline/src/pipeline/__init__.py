"""Le runner de la boucle documentaire, en Python.

Remplace `scripts/agent-loop.sh` et `scripts/pr-review.sh`.

Le paquet est range en couches, et le sens des dependances ne remonte jamais :

    launcher/   les points d'entree : le routeur, les commandes, les hooks
    workflows/  un sous-paquet par workflow : le round, la revue de PR
    execution/  faire tourner un stage, sans rien savoir du workflow
    adapters/   tout composant externe, emballe derriere une interface a nous
    runtime/    chemins, journal, mesures — une feuille, comme domain/
    domain/     le metier pur : la table, les textes, les regex, les arrets

Trois regles gouvernent les imports, et `tests/test_layering.py` en fait des
assertions plutot que des conventions :

1. **crewai n'existe que dans `adapters/engine/crewai_engine.py`.** Il coute
   ~1,3 s d'import a chaud et tire chromadb, openai et opentelemetry — 2331
   modules. `--status` et `--costs` repondent en ~0,08 s parce qu'ils ne le
   croisent jamais.
2. **Le SDK n'existe que dans `adapters/agent/claude_sdk.py`.** Le reste du
   paquet parle a `AgentRunner` et lit un `AgentResult` : aucun nom de champ
   d'un fournisseur ne circule ailleurs.
3. **Les hooks tournent sous le python du systeme**, hors du venv, a chaque
   appel d'outil. Bibliotheque standard seule — ils n'importent rien d'ici.
"""
