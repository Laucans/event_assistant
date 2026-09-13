"""Ce qui varie d'un run a l'autre : les flags, et leurs defauts d'environnement.

Separe de `stages/` a dessein : la table du round est un design qu'on relit,
`RunConfig` est un etat de run qu'on lit dans `os.environ`. Melanger les deux
faisait qu'on ne pouvait pas toucher a l'un sans relire l'autre.

**Ici et pas dans `runtime/`**, meme si les valeurs viennent de
l'environnement : `enabled`, `resolve`, `filtered_out` et `summary` parcourent
`PIPELINE` et rendent des `StageSpec`. C'est une politique appliquee a la
table, pas du support transverse — et c'etait le seul module de `runtime/` a
importer quoi que ce soit du paquet. `runtime/` est desormais une feuille, ce
que son docstring pretendait deja.

Ce qui est commun a toute config de workflow — le workspace, `--dry-run`, la
verbosite, le battement — vient de `WorkflowConfig`. Ce qui reste ici est ce
que la boucle seule connait : la table qu'elle fait tourner, la branche
d'integration, le budget de rounds.

Toute variable lue ici doit apparaitre dans un epilogue `--help` — un test
l'assere (`test_every_environment_variable_the_code_reads_is_in_a_help_epilog`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from pipeline.core.domain import prompts
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.stages import (
    INJECTOR, PIPELINE, ROLLOVER)
from pipeline.core.execution.contract.settings import WorkflowConfig


class ConfigError(Exception):
    """Une variable d'environnement illisible, vue avant tout le reste.

    La seule exception que ce paquet leve encore. Tout le reste rend un
    `Result` — mais une config qui ne se construit pas n'a pas d'objet a qui
    rendre quoi que ce soit : `RunConfig()` est ce qui echoue, et il n'y a
    pas de `cfg` de l'autre cote. Le point d'entree l'attrape, l'imprime sur
    stderr et rend le code d'un arret volontaire.
    """


def _number(name: str, default: str, cast):
    """Une variable numerique de l'environnement, ou son defaut.

    Deux comportements, et chacun repare quelque chose :

    - **le vide vaut absent**, comme le `${MAX_ROUNDS:-3}` du shell. Un
      `MAX_ROUNDS=` dans un fichier d'environnement est une variable qu'on a
      commentee a moitie, pas une demande de zero round ;
    - **une valeur illisible nomme la variable**. Un `int()` nu levait une
      `ValueError` qui ne disait ni laquelle ni ou la corriger — et comme la
      config est construite avant que le journal existe, cette trace partait
      sur un stderr que personne ne garde.
    """
    raw = os.environ.get(name, "").strip()
    try:
        return cast(raw or default)
    except ValueError:
        # La config est construite avant qu'un journal existe, et avant
        # qu'un `Result` ait un appelant a qui se rendre : c'est le seul
        # endroit du paquet ou lever reste la seule facon de se faire
        # entendre. Le point d'entree l'attrape et l'imprime.
        raise ConfigError(f"{name}={raw!r} is not a number — fix it in the"
                          f" environment, or unset it to use"
                          f" {default}") from None


@dataclass
class RunConfig(WorkflowConfig):
    """What varies from one run to the next."""

    integration_branch: str = field(
        default_factory=lambda: os.environ.get("INTEGRATION_BRANCH", "main_agent"))
    permission_mode: str = field(
        default_factory=lambda: os.environ.get("PERMISSION_MODE", "bypassPermissions"))
    max_rounds: int = field(
        default_factory=lambda: _number("MAX_ROUNDS", "3", int))
    stages: str = field(default_factory=lambda: os.environ.get("STAGES", ""))
    model: str = field(default_factory=lambda: os.environ.get("MODEL", ""))
    effort: str = field(default_factory=lambda: os.environ.get("EFFORT", ""))
    allow_dirty: bool = field(
        default_factory=lambda: os.environ.get("ALLOW_DIRTY") == "1")
    # Le battement de `WorkflowConfig`, mais reglable par l'environnement :
    # c'est la boucle, et elle seule, qui tourne sans personne devant.
    heartbeat_s: float = field(
        default_factory=lambda: _number("HEARTBEAT_SECONDS", "60", float))
    restart: bool = False
    run_id: str = ""
    # La table que ce run fait tourner, et l'entree de rollover qui la suit.
    pipeline: tuple[StageSpec, ...] = PIPELINE
    rollover: StageSpec | None = ROLLOVER

    def filtered_out(self) -> list[str]:
        """The stages `--stages`/`STAGES` is leaving out — never silently."""
        return [s.skill for s in self.pipeline if not self.enabled(s)]

    def enabled(self, stage: StageSpec) -> bool:
        """In the table, and not filtered out by --stages/STAGES."""
        return self.runs(stage.skill)

    def runs(self, skill: str) -> bool:
        """Ce skill fait-il partie de ce run ?

        Par nom et non par entree de table : une garde qui veut savoir si le
        stage qui livre la task a ete ecarte n'a pas a retrouver son
        `StageSpec` d'abord.
        """
        if not self.stages:
            return True
        return skill in self.stages.split()

    def resolve(self, stage: StageSpec) -> StageSpec:
        """MODEL/EFFORT are the blunt override: one value for the whole run.

        `replace` plutot qu'une reconstruction champ par champ : un champ
        ajoute a `StageSpec` — les consignes en sont un — serait sinon perdu
        des qu'un run donne `--model`, et le stage partirait sans son texte.
        """
        if not self.model and not self.effort:
            return stage
        return replace(stage, model=self.model or stage.model,
                       effort=self.effort or stage.effort)

    def prompt_for(self, stage: StageSpec, extra: str) -> str:
        """Le texte d'une session de ce stage, sur la branche d'integration."""
        return prompts.build(stage.command, self.integration_branch, extra,
                             injector=INJECTOR)

    def summary(self) -> str:
        """`business-analyst(opus/high) -> code(opus/high) -> ...`."""
        parts = []
        for stage in self.pipeline:
            if not self.enabled(stage):
                continue
            resolved = self.resolve(stage)
            parts.append(f"{stage.skill}({resolved.model}/{resolved.effort})")
        return " -> ".join(parts)
