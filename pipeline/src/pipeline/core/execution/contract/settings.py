"""Ce que toute configuration de workflow porte.

Le sous-ensemble que `RunConfig` et `ReviewConfig` avaient en commun, ecrit
une fois. Ce qui reste propre a chacun — la table du pipeline d'un cote, les
modeles des deux passes de l'autre — reste chez lui : cette classe est ce que
la sequence et les portes communes savent lire, pas un fourre-tout.

Elle satisfait `execution.context.StagePolicy` a une methode pres. C'est ce
qui a change : `StagePolicy` decrit ce que `core/execution` exige pour lancer
une session, et seul `RunConfig` le fournissait — d'ou une revue qui n'a pas
pu se servir du lanceur de stages et a reecrit le sien. Les defauts sont ceux
d'un workflow qui ne filtre rien et ne surcharge rien ; celui qui veut le
contraire les redefinit, comme `RunConfig` le fait.

`prompt_for` n'a pas de defaut : le preambule d'un workflow est ce qu'il a de
plus propre, et en inventer un vide ferait partir une session sans son texte.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pipeline.core.adapters.store import ledger
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.runtime.filesystem.workspace import Workspace


class ConfigError(Exception):
    """Une variable d'environnement illisible, vue avant tout le reste.

    La seule exception que ce paquet leve encore. Tout le reste rend un
    `Result` — mais une config qui ne se construit pas n'a pas d'objet a qui
    rendre quoi que ce soit : `RunConfig()` est ce qui echoue, et il n'y a
    pas de `cfg` de l'autre cote. Le point d'entree l'attrape, l'imprime sur
    stderr et rend le code d'un arret volontaire.
    """


def env_number(name: str, default: str, cast):
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
class WorkflowConfig:
    """Ce qui varie d'un run a l'autre, quel que soit le workflow."""

    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    # A quelle frequence un travail long dit qu'il est encore vivant, en
    # secondes. Un stage peut passer des minutes dans un seul appel d'outil,
    # donc le battement est sur une horloge et non sur l'arrivee d'un message ;
    # 0 l'eteint.
    heartbeat_s: float = 60.0
    workspace: Workspace = field(default_factory=Workspace.here)
    # L'identite de ce run, et sous quel mode ses sessions tournent. Les deux
    # etaient chez la boucle seule, alors que toute session payante en a une
    # et un : le registre ecrit `run_id`, et `permission_mode` etait code en
    # dur du cote de la revue faute d'avoir ou le lire.
    run_id: str = ""
    permission_mode: str = "bypassPermissions"
    # Les etapes que ce run fait tourner, vide voulant dire toutes.
    stages: str = ""

    def runs(self, skill: str) -> bool:
        """Ce skill fait-il partie de ce run ?"""
        if not self.stages:
            return True
        return skill in self.stages.split()

    def enabled(self, stage: StageSpec) -> bool:
        """Dans la table, et pas ecarte par --stages/STAGES."""
        return self.runs(stage.skill)

    def resolve(self, stage: StageSpec) -> StageSpec:
        """L'entree telle qu'elle tournera. Inchangee, sauf surcharge."""
        return stage

    def prompt_for(self, stage: StageSpec, extra: str) -> str:
        """Le texte d'une session de cette etape. Sans defaut, a dessein."""
        raise NotImplementedError(
            f"{type(self).__name__} ne dit pas comment monter le prompt d'une"
            f" session — definis prompt_for(stage, extra)")

    def artifact_tag(self, round_no: int) -> str:
        """Ce qui prefixe les artefacts d'une etape sur le disque."""
        return f"{round_no:02d}"

    def record(self, stage: StageSpec, result, *, round_no: int, task: str,
               outcome: str) -> None:
        """La ligne de registre qu'une session laisse derriere elle.

        Ici et pas dans `session` : quel registre, avec quelles colonnes, est
        la politique d'un workflow. La revue en tient un a part — d'autres
        colonnes, et son cout n'a rien a faire dans le total d'un round.
        """
        ledger.append(
            self.workspace.ledger, run_id=self.run_id, round_no=round_no,
            task=task, stage=stage.skill,
            cache_read=result.usage.get("cache_read_input_tokens"),
            cache_write=result.usage.get("cache_creation_input_tokens"),
            outcome=outcome,
            **result.ledger_fields(model=stage.model, effort=stage.effort))
