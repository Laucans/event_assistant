"""Ce que la revue lit d'une PR."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pr:
    """Ce que la revue lit d'une PR."""

    num: str
    base: str
    head: str
    title: str
    url: str

    @classmethod
    def of(cls, meta: dict) -> "Pr":
        return cls(str(meta["number"]), meta["baseRefName"],
                   meta["headRefName"], meta["title"], meta["url"])
