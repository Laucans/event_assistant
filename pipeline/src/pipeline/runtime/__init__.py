"""Le support transverse : ce que tout le monde importe et qui ne decide rien.

Les chemins du depot, le journal, les mesures. Bibliotheque standard seule, et
**aucun import du paquet** — une feuille, au meme titre que `domain`, ce que
`tests/test_layering.py` assere.

Les reglages d'un run ne sont pas ici : `RunConfig` parcourt `PIPELINE` et
rend des `StageSpec`, donc c'est une politique appliquee a la table et non un
reglage inerte. Elle vit dans `workflows/agentic_dev_loop/settings.py`.
"""
