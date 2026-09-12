"""La mecanique d'un stage, independante du workflow qui l'enchaine.

`stage_runner` et `session` portent l'orchestration : filtrer, marquer,
compter, arreter. Elle est separee du design d'un workflow parce qu'on relit
celui-la pour comprendre le pipeline, et celle-ci pour comprendre une panne.
"""
