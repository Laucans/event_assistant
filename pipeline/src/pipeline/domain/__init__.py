"""Le metier : ce que la boucle *est*, independamment de ce qui la fait tourner.

La regle de cette couche, et c'est la seule : **aucun import vers l'exterieur
du domaine**. Pas de crewai, pas de SDK, pas de subprocess, pas de lecture de
fichier. Ce qui vit ici se teste en passant des chaines et en lisant ce qui
sort — la table du pipeline, les regex qui decident ce qu'est une task, le
texte envoye aux stages, les facons dont un run s'arrete.

`tests/test_layering.py` en fait une assertion plutot qu'une convention.
"""
