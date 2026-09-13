"""Les etiquettes `pipeline:*`, partagees par les workflows qui les lisent."""

from __future__ import annotations

# Les etiquettes qui portent tout le modele. Elles sont creees a la main sur
# le depot, et `workflows.agentic_dev_loop.preconditions` verifie qu'elles
# existent avant de payer quoi que ce soit : une etiquette mal orthographiee
# rend le tableau vide, et un tableau vide se lit comme « plus rien a faire ».
ROADMAP = "pipeline:roadmap"
MILESTONE = "pipeline:milestone"
AGENT = "pipeline:agent"
HUMAN = "pipeline:human"
READY = "pipeline:ready"
SPEC_WRITTEN = "pipeline:spec-written"
# Livree sur la branche d'integration, pas encore fusionnee dans `main`.
# L'issue reste **ouverte** : la fermer dirait que le travail est integre,
# ce qui n'est vrai qu'apres la fusion. Ce troisieme etat est ce qui separe
# « l'agent a fini » de « c'est dans main ».
WAITING_MERGE = "pipeline:waiting-merge"
REFINEMENT = "pipeline:refinement"

# Les sept que la boucle exige. `REFINEMENT` n'en fait pas partie : la boucle
# ne la lit pas, et son preflight refuserait de tourner sans elle.
LOOP = (ROADMAP, MILESTONE, AGENT, HUMAN, READY, SPEC_WRITTEN, WAITING_MERGE)
