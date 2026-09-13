"""Faire tourner — un stage, et le workflow qui les enchaine.

Deux granularites du meme verbe, et c'est pourquoi elles vivent ensemble :

- `session` et `stage_runner` font tourner **un stage** : composer le prompt,
  appeler le moteur d'agent, filtrer, marquer, compter, arreter ;
- `contract/` dit ce qu'un **workflow** est — sa forme (`Workflow`), ce qu'il
  rend (`WorkflowOutcome`), ce que toute config porte (`WorkflowConfig`) — et
  `sequence()` le fait tourner : garder, faire, verifier.

Rien ici ne connait un workflow en particulier. `context.StagePolicy` dit ce
que l'execution **exige** d'une config, `contract.WorkflowConfig` ce dont
cette config **herite** : deux faces du meme objet, et elles se lisent
maintenant cote a cote. C'est le `Protocol` qui tient les deux — aucun import
ne relie cette couche a `workflows/`, dans aucun sens.
"""
