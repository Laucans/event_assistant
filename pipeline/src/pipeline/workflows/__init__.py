"""Un sous-paquet par workflow, tous de la meme forme.

Chaque workflow porte les memes quatre modules a sa racine, sa definition
dans `stages/` et son code propre dans `internals/`. `common/` porte les
portes qu'ils passent tous ; le contrat qu'ils implementent, lui, n'est pas
ici — il est dans `core/execution/contract/`, parce qu'une forme
n'appartient pas a ceux qui l'adoptent.

**Pour en ajouter un : `how_to_design_a_workflow.md`, dans ce dossier.** Il
dit la forme, ce qui la tient (les tests de `tests/test_layering.py`), les
decisions qui ne se rouvrent pas, et les pieges qui coutent de l'argent.
"""
