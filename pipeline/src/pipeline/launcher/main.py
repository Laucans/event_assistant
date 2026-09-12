"""Le routeur : il lit argv, choisit la route, valide, et dispatche."""

from __future__ import annotations

import sys

REFUSED = 1


def main(argv: list[str] | None = None) -> int:
    """Dispatche argv vers la route qu'il nomme, `loop` a defaut."""
    from pipeline.launcher import routes

    args = list(sys.argv[1:] if argv is None else argv)
    route = routes.find(args[0]) if args else None
    if route is None:
        route = routes.default()
    else:
        args = args[1:]
    if route.protocol == "hook":
        return _hook(route)
    return _cli(route, args)


def _hook(route) -> int:
    """Le protocole hook : JSON sur stdin, JSON ou rien sur stdout, 2 bloque."""
    import importlib

    return importlib.import_module(route.target).main() or 0


def _cli(route, args: list[str]) -> int:
    """Le protocole CLI : argparse, les regles par route, un code de sortie."""
    import importlib

    module = importlib.import_module(route.target)
    parsed = module.parse_args(args)

    from pipeline.launcher import validation

    errors, warnings = validation.check(route, module.config_to_check(parsed),
                                        args=parsed)
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return REFUSED
    for line in warnings:
        print(line, file=sys.stderr)
    return module.main(args)
