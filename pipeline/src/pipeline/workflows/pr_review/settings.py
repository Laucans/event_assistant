"""Ce qui varie d'une revue a l'autre, et la politique qu'elle applique.

Ce qui est commun a toute config de workflow — le workspace, `--dry-run`, la
verbosite, le battement, l'identifiant de run, le mode de permission — vient
de `WorkflowConfig`. Ce qui reste ici est ce que la revue seule connait : la
PR, la branche qu'elle doit cibler, et les modeles des deux passes.

Les trois methodes redefinies sont la politique que `core/execution` lui
demande pour lancer une session : comment monter un prompt, comment nommer
les artefacts, et dans quel registre ecrire. La revue tient le sien — d'autres
colonnes, et son cout n'a rien a faire dans le total d'un round.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pipeline.core.adapters.store import ledger
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.execution.contract.settings import WorkflowConfig


def token(pr: str) -> str:
    """A filename-safe handle for a PR given as a number or as a URL."""
    match = re.search(r"(\d+)\s*$", pr)
    return match.group(1) if match else re.sub(r"[^0-9A-Za-z._-]", "-", pr)[:40]


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
    # Le hook lance la revue **detachee** : stderr est le seul canal qu'un
    # appelant qui n'ouvre pas le fichier de log verra passer.
    warn: Callable[[str], None] | None = None

    @property
    def handle(self) -> str:
        """Le nom de fichier que cette PR porte sur le disque."""
        return token(self.pr)

    def prompt_for(self, stage: StageSpec, extra: str) -> str:
        """Le prompt d'une passe **est** son texte.

        La boucle monte un preambule commun autour de la commande de chaque
        stage ; une revue n'en a pas — chaque passe est un texte complet, et
        `stages.prompt_of` le rend.
        """
        return extra

    def artifact_tag(self, round_no: int) -> str:
        """Les artefacts d'une revue portent le numero de sa PR."""
        return self.handle

    def record(self, stage: StageSpec, result, *, round_no: int, task: str,
               outcome: str) -> None:
        """La ligne du registre des revues."""
        ledger.append_review(
            self.workspace.review_ledger, pr=self.handle, label=stage.skill,
            outcome=outcome,
            **result.ledger_fields(model=stage.model, effort=stage.effort))
