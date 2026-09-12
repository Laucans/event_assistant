"""Le round : ce qu'il fait, et qui le fait faire.

`workflow` porte `AgenticDevLoop` — la forme que tout workflow de ce paquet
a. `settings` porte `RunConfig` : ce qui varie d'un run a l'autre, y compris
la politique `--stages`/`--model`/`--effort` appliquee a la table.
`preconditions` et `postconditions` sont les deux gardes du contrat.

Ce qui fait le travail est dans `internals/` : `flow` porte la sequence — le
design metier du round —, `gates` ce qu'un noeud exige et doit obtenir,
`board` le cote lecture des issues, `loop` la repetition des rounds, et
`state` ce que le moteur persiste.
"""
