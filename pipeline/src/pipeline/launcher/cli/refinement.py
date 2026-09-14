"""L'entree du raffinage : les flags, l'environnement, le code de sortie.

Aucune decision ici. Les flags et les defauts d'environnement deviennent un
`RefinementConfig`, l'orchestration part dans `workflows.refinement`, et ce
qui remonte devient un code de sortie.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback

# Meme raison que la boucle et la revue : `claude -p` facture ce sous quoi la
# CLI est authentifiee, et une cle dans l'environnement sortirait le raffinage
# de l'abonnement.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

from pipeline.core.domain.outcomes.exit_codes import (  # noqa: E402
    EXIT_CRASH, EXIT_INTERRUPTED)
from pipeline.core.runtime.filesystem.workspace import Workspace  # noqa: E402
from pipeline.core.runtime.monitoring import logbook  # noqa: E402
from pipeline.core.runtime.monitoring.logbook import Logbook  # noqa: E402
from pipeline.core.design import build  # noqa: E402
from pipeline.workflows.refinement.settings import RefinementConfig  # noqa: E402
from pipeline.workflows.refinement.workflow import WORKFLOW  # noqa: E402


def make_logger(issue: str, workspace: Workspace, *,
                level: int = logbook.NORMAL) -> Logbook:
    """Le journal d'un round — sur le terminal et sur disque.

    Le tampon `refinement#25` est ce qui rend ses lignes separables de celles
    de la boucle quand les deux ecrivent dans le meme terminal.
    """
    return logbook.open_logbook(
        "pipeline.refinement", file=workspace.refinement_dir / f"{issue}.log",
        level=level).bind(f"refinement#{issue}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="refinement",
        description="Refine one GitHub issue: rewrite its body as the five"
                    " canonical sections, one round per run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Env overrides — an undiscoverable knob is a knob nobody turns:\n"
               "  REFINEMENT_MODEL             force one model on every stage\n"
               f"  REFINEMENT_GOAL_MODEL        model of Business Goal"
               f" (default {RefinementConfig.goal_model})\n"
               f"  REFINEMENT_GOAL_EFFORT       effort of Business Goal"
               f" (default {RefinementConfig.goal_effort})\n"
               f"  REFINEMENT_TECHNICAL_MODEL   model of Technical"
               f" (default {RefinementConfig.technical_model})\n"
               f"  REFINEMENT_TECHNICAL_EFFORT  effort of Technical"
               f" (default {RefinementConfig.technical_effort})\n"
               f"  REFINEMENT_CRITERIA_MODEL    model of Acceptance Criteria"
               f" (default {RefinementConfig.criteria_model})\n"
               f"  REFINEMENT_CRITERIA_EFFORT   effort of Acceptance Criteria"
               f" (default {RefinementConfig.criteria_effort})\n"
               f"  REFINEMENT_RULES_MODEL       model of Business Rules"
               f" (default {RefinementConfig.rules_model})\n"
               f"  REFINEMENT_RULES_EFFORT      effort of Business Rules"
               f" (default {RefinementConfig.rules_effort})\n"
               f"  REFINEMENT_PLAN_MODEL        model of Technical Implementation Plan"
               f" (default {RefinementConfig.plan_model})\n"
               f"  REFINEMENT_PLAN_EFFORT       effort of Technical Implementation Plan"
               f" (default {RefinementConfig.plan_effort})\n"
               f"  REFINEMENT_ROUTER_MODEL      model of the round >= 3 router"
               f" (default {RefinementConfig.router_model})\n"
               f"  REFINEMENT_ROUTER_EFFORT     effort of the round >= 3 router"
               f" (default {RefinementConfig.router_effort})\n"
               f"  REFINEMENT_COHERENCE_MODEL   model of the closing coherence pass"
               f" (default {RefinementConfig.coherence_model})\n"
               f"  REFINEMENT_COHERENCE_EFFORT  effort of the closing coherence pass"
               f" (default {RefinementConfig.coherence_effort})\n"
               f"  REFINEMENT_EXPLORE_MODEL     model of the repo map"
               f" (default {RefinementConfig.explore_model})\n"
               f"  REFINEMENT_EXPLORE_EFFORT    effort of the repo map"
               f" (default {RefinementConfig.explore_effort})\n"
               "\n"
               "One session reads the repository before the round and writes a\n"
               "map; the sections work from it instead of exploring on their own.\n"
               "--explore drops the map and gives every section the repository\n"
               "back — more thorough, and several times the tokens.\n"
               "\n"
               "A last session reads every section this round wrote, together,\n"
               "and retouches whichever ones disagree with each other before\n"
               "anything is published.\n"
               "\n"
               "The issue must carry pipeline:refinement (or --force) and either\n"
               "pipeline:agent or pipeline:human. Issues are public: never write\n"
               "the value of a secret into one.\n"
               "\n"
               "Exit codes — a trigger may launch this detached, so they are the\n"
               "only signal an outer caller gets:\n"
               "  0    the round was written\n"
               "  1    stopped on purpose — a human has to act\n"
               "  2    a stage produced nothing usable, or the body could not be posted\n"
               "  3    subscription quota exhausted: re-run later, unchanged\n"
               "  4    unexpected error; the traceback is in the refinement log\n"
               "  130  interrupted")
    p.add_argument("issue", type=int, help="issue number to refine")
    p.add_argument("--context", default="",
                   help="what this round asks for; injected into every stage prompt")
    p.add_argument("--force", action="store_true",
                   help="refine an issue that does not carry pipeline:refinement")
    p.add_argument("--explore", action="store_true",
                   help="no repo map: let every section read the repository"
                        " itself (thorough, and several times the tokens)")
    p.add_argument("--dry-run", action="store_true",
                   help="write the prompts, call nothing")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="every tool call on the terminal, not just the heartbeat")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="warnings and errors only (the log file keeps everything)")
    p.add_argument("--heartbeat", type=float, default=60.0, metavar="SECONDS",
                   help="how often a running stage reports in (default 60, 0 off)")
    return p.parse_args(argv)


def _env(name: str, default: str) -> str:
    """Une variable de l'environnement, le vide valant absente.

    Un `REFINEMENT_GOAL_EFFORT=` est une variable commentee a moitie, pas une
    demande d'effort vide : la validation le laisse passer, et `StageSpec`
    leve ensuite — apres le preflight, deux appels `gh` et le verrou.
    """
    return os.environ.get(name, "").strip() or default


def build_config(args: argparse.Namespace) -> RefinementConfig:
    """Les flags et l'environnement, resolus en une config de raffinage.

    `REFINEMENT_MODEL` force les sept stages ; les `REFINEMENT_*_MODEL/EFFORT`
    les reglent separement, parce que ce ne sont pas le meme travail.
    """
    forced = _env("REFINEMENT_MODEL", "")
    return RefinementConfig(
        issue=args.issue,
        context=args.context,
        force=args.force,
        explore=args.explore,
        dry_run=args.dry_run,
        verbose=args.verbose,
        quiet=args.quiet,
        heartbeat_s=args.heartbeat,
        goal_model=forced or _env("REFINEMENT_GOAL_MODEL", RefinementConfig.goal_model),
        goal_effort=_env("REFINEMENT_GOAL_EFFORT", RefinementConfig.goal_effort),
        technical_model=forced or _env("REFINEMENT_TECHNICAL_MODEL",
                                        RefinementConfig.technical_model),
        technical_effort=_env("REFINEMENT_TECHNICAL_EFFORT",
                               RefinementConfig.technical_effort),
        criteria_model=forced or _env("REFINEMENT_CRITERIA_MODEL",
                                       RefinementConfig.criteria_model),
        criteria_effort=_env("REFINEMENT_CRITERIA_EFFORT",
                              RefinementConfig.criteria_effort),
        rules_model=forced or _env("REFINEMENT_RULES_MODEL", RefinementConfig.rules_model),
        rules_effort=_env("REFINEMENT_RULES_EFFORT", RefinementConfig.rules_effort),
        plan_model=forced or _env("REFINEMENT_PLAN_MODEL", RefinementConfig.plan_model),
        plan_effort=_env("REFINEMENT_PLAN_EFFORT", RefinementConfig.plan_effort),
        router_model=forced or _env("REFINEMENT_ROUTER_MODEL", RefinementConfig.router_model),
        router_effort=_env("REFINEMENT_ROUTER_EFFORT", RefinementConfig.router_effort),
        coherence_model=forced or _env("REFINEMENT_COHERENCE_MODEL",
                                        RefinementConfig.coherence_model),
        coherence_effort=_env("REFINEMENT_COHERENCE_EFFORT",
                               RefinementConfig.coherence_effort),
        explore_model=forced or _env("REFINEMENT_EXPLORE_MODEL",
                                      RefinementConfig.explore_model),
        explore_effort=_env("REFINEMENT_EXPLORE_EFFORT",
                             RefinementConfig.explore_effort),
        workspace=Workspace.here(),
        # Un raffinage lance par un declencheur tourne detache : stderr est la
        # seule chose qu'un appelant qui n'ouvre pas le log verra passer.
        warn=lambda msg: print(msg, file=sys.stderr),
    )


def config_to_check(args: argparse.Namespace) -> RefinementConfig:
    """La config que la validation examine."""
    return build_config(args)


def main(argv: list[str] | None = None) -> int:
    """Fait tourner le round, et ne laisse rien sortir en trace nue.

    Un declencheur peut lancer ceci detache : une exception non rattrapee
    partirait la ou le declencheur a redirige, c'est-a-dire nulle part.
    """
    try:
        return asyncio.run(_main(argv))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception:
        try:
            make_logger(_issue_arg(argv), Workspace.here()).exception(
                "CRASH — le raffinage est mort sur une erreur inattendue")
        except Exception:
            # Rapporter le crash ne doit pas devenir le crash.
            traceback.print_exc()
        return EXIT_CRASH


def _issue_arg(argv: list[str] | None) -> str:
    """L'issue dont parlait le run qui a plante, pour nommer son log.

    On redemande a argparse plutot que de deviner : un balayage qui rend le
    premier jeton sans tiret rend la valeur d'un flag des que celui-ci
    precede le positionnel.
    """
    args = sys.argv[1:] if argv is None else argv
    try:
        return str(parse_args(args).issue)
    except BaseException:      # argparse sort par SystemExit, pas Exception
        for arg in args:
            if not arg.startswith("-"):
                return arg
    return "unknown"


async def _main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = build_config(args)
    level = (logbook.VERBOSE if args.verbose
             else logbook.QUIET if args.quiet else logbook.NORMAL)
    log = make_logger(str(args.issue), cfg.workspace, level=level)
    outcome = await build.workflow(WORKFLOW, cfg, log).run()
    return outcome.report(log).exit_code
