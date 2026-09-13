"""Le runner de la boucle documentaire, en Python.

Remplace `scripts/agent-loop.sh` et `scripts/pr-review.sh`.

Le paquet est range en couches, et le sens des dependances ne remonte jamais :

    launcher/   les points d'entree : le routeur, les commandes, les hooks
    workflows/  un sous-paquet par workflow : le round, la revue de PR
    execution/  faire tourner un stage, sans rien savoir du workflow
    core/       le framework : vocabulaire, support, adaptateurs, execution
    workflows/  la definition : un sous-paquet par workflow
    launcher/   le declenchement : un routeur, les commandes, les hooks

Trois regles gouvernent les imports, et `tests/test_layering.py` en fait des
assertions plutot que des conventions :

1. **Rien sous `core/` n'importe `workflows/` ni `launcher/`.** C'est la
   frontiere framework/usage : ce qui est dans `core/` se branche sous
   n'importe quel workflow, donc un troisieme n'oblige a toucher a rien.
2. **Le SDK n'existe que dans `core/adapters/agent/claude_sdk.py`.** Le reste du
   paquet parle a `AgentRunner` et lit un `AgentResult` : aucun nom de champ
   d'un fournisseur ne circule ailleurs.
3. **Les hooks tournent sous le python du systeme**, hors du venv, a chaque
   appel d'outil. Bibliotheque standard seule — ils n'importent rien d'ici.
"""
