"""Les regles inter-arguments qu'argparse ne sait pas exprimer, par route.

Une regle est une fonction pure : elle recoit la config resolue (et les
arguments bruts, pour ce qui porte sur un flag donne ou non) et rend les
lignes qu'elle a a dire. `check` ne fait que parcourir la table.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Callable

from pipeline.domain import stage_spec

if TYPE_CHECKING:
    from pipeline.launcher.routes import Route

LEVELS = ("low", "medium", "high", "max")

# Les flags que `migrate` ne lit pas, avec leur valeur « pas donne ».
MIGRATE_UNUSED = (("--rounds", "rounds", None), ("--stages", "stages", None),
                  ("--model", "model", None), ("--effort", "effort", None),
                  ("--restart", "restart", False),
                  ("--heartbeat", "heartbeat", None))

# Les deux passes de la revue, et la variable qui regle l'effort de chacune.
REVIEW_EFFORTS = (("PR_REVIEW_INLINE_EFFORT", "inline_effort"),
                  ("PR_REVIEW_BRIEF_EFFORT", "brief_effort"))

EFFORTS = "|".join(stage_spec.EFFORTS)


def _named_stages(cfg: object) -> list[str]:
    return (getattr(cfg, "stages", None) or "").split()


# --- les regles, une fonction pure chacune ---------------------------------


def _stages_exist(cfg: object, args: argparse.Namespace) -> list[str]:
    pipeline = getattr(cfg, "pipeline", ())
    return [f"--stages/STAGES: {name!r} is not an entry of the pipeline"
            f" — known entries: {stage_spec.names(pipeline)}"
            for name in _named_stages(cfg)
            if stage_spec.spec_of(name, pipeline) is None]


def _rounds_positive(cfg: object, args: argparse.Namespace) -> list[str]:
    rounds = getattr(cfg, "max_rounds", None)
    if rounds is None or rounds > 0:
        return []
    return [f"--rounds/MAX_ROUNDS: {rounds} would run no task at all"
            f" — give 1 or more"]


def _effort_known(cfg: object, args: argparse.Namespace) -> list[str]:
    effort = getattr(cfg, "effort", None)
    if not effort or effort in stage_spec.EFFORTS:
        return []
    return [f"--effort/EFFORT: {effort!r} is not an effort level"
            f" — known levels: {EFFORTS}"]


def _level_known(cfg: object, args: argparse.Namespace) -> list[str]:
    level = getattr(cfg, "level", None)
    if level in LEVELS:
        return []
    return [f"--level/PR_REVIEW_LEVEL: {level!r} is not a /code-review level"
            f" — known levels: {'|'.join(LEVELS)}"]


def _review_efforts_known(cfg: object, args: argparse.Namespace) -> list[str]:
    return [f"{variable}: {effort!r} is not an effort level"
            f" — known levels: {EFFORTS}"
            for variable, attribute in REVIEW_EFFORTS
            if (effort := getattr(cfg, attribute, None))
            and effort not in stage_spec.EFFORTS]


def _verbose_xor_quiet(cfg: object, args: argparse.Namespace) -> list[str]:
    if not (getattr(cfg, "verbose", False) and getattr(cfg, "quiet", False)):
        return []
    return ["--verbose and --quiet ask for opposite things — give one"]


def _heartbeat_positive(cfg: object, args: argparse.Namespace) -> list[str]:
    heartbeat = getattr(cfg, "heartbeat_s", None)
    if heartbeat is None or heartbeat >= 0:
        return []
    return [f"--heartbeat: {heartbeat} is not a number of seconds"
            " — give 0 or more (0 turns the heartbeat off)"]


def _stages_deliver(cfg: object, args: argparse.Namespace) -> list[str]:
    named = _named_stages(cfg)
    if not named or "code" in named:
        return []
    return ["--stages leaves out `code`: no stage will deliver the task, so"
            " the round will end on « nothing marks it delivered »."]


def _migrate_ignores(cfg: object, args: argparse.Namespace) -> list[str]:
    if getattr(args, "command", None) != "migrate":
        return []
    unused = [flag for flag, attr, unset in MIGRATE_UNUSED
              if getattr(args, attr, unset) != unset]
    if not unused:
        return []
    return [f"migrate ignores {', '.join(unused)}: it turns the documents"
            " into issues once, it runs no round."]


# --- la table --------------------------------------------------------------

Check = Callable[[object, argparse.Namespace], list[str]]

# Dans l'ordre ou les lignes sortent. Les refus d'abord, les avertissements
# ensuite : `check` ne fait que filtrer cette table par les regles de la route,
# donc l'ordre des messages ne depend pas de l'ordre ou une route les nomme.
ERRORS: tuple[tuple[str, Check], ...] = (
    ("stages-exist", _stages_exist),
    ("rounds-positive", _rounds_positive),
    ("effort-known", _effort_known),
    ("level-known", _level_known),
    ("review-efforts-known", _review_efforts_known),
    ("verbose-xor-quiet", _verbose_xor_quiet),
    ("heartbeat-positive", _heartbeat_positive),
)

WARNINGS: tuple[tuple[str, Check], ...] = (
    ("stages-deliver", _stages_deliver),
    ("migrate-ignores", _migrate_ignores),
)

# Les noms de regle que `check` sait appliquer. Derive de la table plutot que
# tenu a la main : une regle implementee que personne ne nomme, ou l'inverse,
# ne peut plus passer inapercue.
RULES = frozenset(name for name, _ in ERRORS + WARNINGS)


def _apply(table: tuple[tuple[str, Check], ...], rules: frozenset[str],
           cfg: object, args: argparse.Namespace) -> list[str]:
    return [line for name, rule in table if name in rules
            for line in rule(cfg, args)]


def check(route: Route, cfg: object,
          *, args: argparse.Namespace | None = None
          ) -> tuple[list[str], list[str]]:
    """Les erreurs et les avertissements de cette route sur cette config.

    `args` ne sert qu'aux regles qui portent sur un flag donne ou non.
    """
    rules = frozenset(route.rules)
    args = args if args is not None else argparse.Namespace()
    return (_apply(ERRORS, rules, cfg, args),
            _apply(WARNINGS, rules, cfg, args))
