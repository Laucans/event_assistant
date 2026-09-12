"""Ce que tout workflow partage : son contrat, et ce qu'il reutilise.

`contract/` dit ce qu'un workflow **est** — la forme que le lanceur appelle,
la sequence qu'il suit, ce qu'il rend. `utils/` porte ce que plusieurs
workflows **font** : les fabriques d'adaptateurs, et les portes de preflight
qui ne sont propres a aucun d'eux.

La regle qui tient l'ensemble : un workflow importe `common`, jamais un autre
workflow. `tests/test_layering.py` en fait une assertion.
"""
