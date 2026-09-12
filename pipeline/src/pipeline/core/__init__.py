"""Le framework : tout ce qui ne sait rien d'aucun workflow.

Quatre couches, et la fleche va toujours vers le bas :

    execution/   faire tourner un stage — filtrer, marquer, compter, arreter
    adapters/    l'exterieur emballe : gh, git, le SDK, crewai, le disque
    domain/      le vocabulaire : ce qu'est un stage, une issue, un arret
    runtime/     le support transverse : chemins, journal, mesures

`domain/` et `runtime/` sont deux feuilles et n'importent qu'elles-memes. Ce
qui les separe n'est pas leur place dans le graphe mais ce qu'elles ont le
droit de faire : `domain/` decide et ne touche jamais l'exterieur,
`runtime/` touche le disque (et un subprocess, dans `paths`) et ne decide
rien. Un module de `runtime/` qui se met a juger quelque chose n'a plus
d'excuse pour son acces disque — c'est ce qui a fait sortir `RunConfig`
d'ici.

**La regle qui justifie ce dossier : rien sous `core/` n'importe
`workflows/` ni `launcher/`.** Une seule assertion
(`test_nothing_under_core_knows_a_workflow_or_the_launcher`) la tient, la ou
il fallait sinon la lire dans quatre lignes d'une table. C'est ce qui rend un
troisieme workflow facile : il se branche sur le framework, le framework ne
se branche sur rien.
"""
