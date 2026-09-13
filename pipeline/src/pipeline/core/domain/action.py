"""Une etape qui ne paie rien.

Le pendant de `StageSpec` : une etape de sequence dont le travail est un
appel local — choisir la task, constater la livraison, poster le commentaire
— et non une session facturee. Les deux satisfont le meme `Step`, donc une
sequence les enchaine sans savoir laquelle elle tient.

Ici et pas dans `execution/` pour la meme raison que `StageSpec` : c'est le
vocabulaire d'une etape, pas la machinerie qui la fait tourner. `do` est
typee `Callable` et le domaine ne l'appelle jamais — ce qu'elle recoit est
l'affaire du workflow qui l'ecrit, et le coureur de sequence est le seul a
l'appeler.

Ce que ca remplace : ces etapes vivaient **hors** de la sequence, appelees a
la main de part et d'autre, avec leur `save()` autour. Dans la table, elles
heritent du journal, du dry-run et du point de reprise comme les autres.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """Une etape locale : son nom, ce qu'elle fait, et ses trois gardes."""

    skill: str
    do: Callable
    skip: Callable | None = None
    before: Callable | None = None
    after: Callable | None = None

    @property
    def label(self) -> str:
        """Comment l'etape est nommee dans les journaux."""
        return self.skill
