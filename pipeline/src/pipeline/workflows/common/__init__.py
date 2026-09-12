"""Les portes que plusieurs workflows passent, ecrites une fois.

Il n'y a plus que ca ici. Le **contrat** — ce qu'un workflow est, la sequence
qu'il suit, ce qu'il rend — a rejoint `core/execution/contract/` : il decrit
une forme, et une forme n'appartient pas a ceux qui l'adoptent. La fabrique
d'adaptateurs a rejoint `core/adapters/hub.py`, parce que le launcher
l'importe aussi et qu'elle n'est donc commune a rien de particulier.

Ce qui reste est de la **politique** : quelles portes un run doit passer
avant de depenser. `TOOLING` et `BRANCH` sont composees pour les deux
workflows d'ici, et `ci_triggers_on_the_branch` encode la facon de
travailler de ce depot. Un troisieme workflow peut en exiger de tout autres
sans rien changer au contrat — c'est exactement la difference qui a fait
rester ce fichier.
"""
