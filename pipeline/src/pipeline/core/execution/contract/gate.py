"""Ce qu'est une porte, et comment une liste de portes se verifie.

Le **vocabulaire** d'un preflight, pas ses portes : ce qu'une porte est, ce
qu'elle lit, et l'ordre dans lequel une liste se parcourt. Les portes
elles-memes — `claude` sur le PATH, un arbre propre, une branche qui existe —
sont la facon de travailler d'un depot et vivent dans `workflows/common`.

C'est la meme ligne que partout ailleurs sous `core/` : le framework porte la
forme, l'usage porte l'instance. Sans elle, rien sous `core/` ne pourrait
nommer le type d'une porte, puisque rien sous `core/` n'a le droit
d'importer un workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring.logbook import Logbook


class Checked(Protocol):
    """Le minimum qu'une porte commune lit dans une config de workflow."""

    workspace: Workspace


@dataclass(frozen=True)
class Check:
    """Une porte : un nom pour la nommer, et ce qu'elle verifie.

    Le nom est la pour qu'un lecteur liste ce qui est verifie sans lire les
    corps — et pour qu'une passe d'observabilite ait quelque chose a
    journaliser quand chacune passe.
    """

    name: str
    verify: Callable[[Checked, Logbook], Result[None]]


def verify_all(checks: tuple[Check, ...], cfg: Checked,
               log: Logbook) -> Result[None]:
    """Les portes, dans l'ordre, jusqu'a la premiere qui echoue.

    S'arreter a la premiere est le comportement voulu : les portes se
    supposent les unes les autres — demander a `gh` quelles etiquettes existe
    n'a pas de sens tant qu'on ne sait pas s'il est authentifie.
    """
    for check in checks:
        got = check.verify(cfg, log)
        if got.failed:
            return got
    return Result.of(None)
