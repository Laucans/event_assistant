"""Ce qui varie d'une revue a l'autre.

Ce qui est commun a toute config de workflow — le workspace, `--dry-run`, la
verbosite, le battement — vient de `WorkflowConfig`. Ce qui reste ici est ce
que la revue seule connait : la PR, la branche qu'elle doit cibler, et les
modeles des deux passes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.workflows.common.contract.settings import WorkflowConfig


# `kw_only` restaure ce que l'heritage avait perdu : `pr` et `base` n'ont pas
# de defaut, et un champ sans defaut ne peut pas suivre les champs defautes de
# `WorkflowConfig`. Sans ca il aurait fallu leur inventer une valeur vide, et
# une revue sans numero de PR se serait construite sans rien dire.
@dataclass(kw_only=True)
class ReviewConfig(WorkflowConfig):
    """Ce qui varie d'une revue a l'autre. Rempli par `cli.pr_review`."""

    pr: str
    base: str
    level: str = "medium"
    force: bool = False
    no_inline: bool = False
    inline_model: str = "sonnet"
    inline_effort: str = "medium"
    brief_model: str = "sonnet"
    brief_effort: str = "low"
