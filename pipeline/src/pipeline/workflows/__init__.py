"""Un sous-paquet par workflow, tous de la meme forme.

`common/` porte le contrat et ce que les workflows reutilisent ; chaque
workflow porte les memes quatre modules a sa racine et son code propre dans
`internals/`.

**Pour en ajouter un : `how_to_design_a_workflow.md`, dans ce dossier.** Il
dit la forme, ce qui la tient (les tests de `tests/test_layering.py`), les
decisions qui ne se rouvrent pas, et les pieges qui coutent de l'argent.
"""
