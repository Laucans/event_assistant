"""La table des routes : un nom, un protocole, un module cible, des regles."""

from __future__ import annotations


class Route:
    """Un point d'entree : son nom, son protocole, sa cible, ses regles.

    Ecrite a la main plutot qu'en dataclass : `dataclasses` tire `inspect` et
    coute ~7 ms d'import, payes par chaque hook a chaque appel d'outil.
    """

    __slots__ = ("name", "protocol", "target", "rules")

    def __init__(self, name: str, protocol: str, target: str,
                 rules: tuple[str, ...] = ()) -> None:
        self.name = name
        self.protocol = protocol
        self.target = target
        self.rules = rules

    def __repr__(self) -> str:
        return (f"Route({self.name!r}, {self.protocol!r}, {self.target!r},"
                f" rules={self.rules!r})")


ROUTES: tuple[Route, ...] = (
    Route("loop", "cli", "pipeline.launcher.cli.agentic_dev_loop",
          rules=("stages-exist", "rounds-positive", "effort-known",
                 "verbose-xor-quiet", "heartbeat-positive", "stages-deliver",
                 "migrate-ignores")),
    Route("pr-review", "cli", "pipeline.launcher.cli.pr_review",
          rules=("level-known", "review-efforts-known", "verbose-xor-quiet",
                 "heartbeat-positive")),
    Route("branch-guard", "hook", "pipeline.launcher.hooks.branch_guard"),
    Route("no-secret-paths", "hook", "pipeline.launcher.hooks.no_secret_paths"),
    Route("pr-review-trigger", "hook",
          "pipeline.launcher.hooks.pr_review_trigger"),
    Route("scratchpad-notice", "hook",
          "pipeline.launcher.hooks.scratchpad_notice"),
)

DEFAULT = "loop"


def find(name: str) -> Route | None:
    """La route de ce nom, ou None."""
    for route in ROUTES:
        if route.name == name:
            return route
    return None


def default() -> Route:
    """La route prise quand argv[0] ne nomme aucune route."""
    return next(route for route in ROUTES if route.name == DEFAULT)


def names() -> str:
    """Les noms de la table, pour un message d'erreur qui aide."""
    return " ".join(route.name for route in ROUTES)
