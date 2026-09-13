"""Ce qu'on lit d'une PR.

Metier pur : ni I/O, ni subprocess, ni bibliotheque externe.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pr:
    """Ce qu'on lit d'une PR."""

    num: str
    base: str
    head: str
    title: str
    url: str
    state: str = "OPEN"
    draft: bool = False
