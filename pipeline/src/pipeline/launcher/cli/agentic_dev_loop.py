"""The loop's command-line entry point.

The fast commands (`--status`, `--costs`) answer without ever importing
crewai: 2.5s of import to print two lines would be a regression against the
shell, which answered in 10ms.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys
from pathlib import Path

# `claude -p` bills whatever the CLI is authenticated as. A key in the
# environment would silently move this loop off the subscription and onto an
# account billed by usage.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

# Set before any crewai import: this pipeline sends no telemetry.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_DISABLE_TRACKING", "true")
os.environ.setdefault("CREWAI_DISABLE_VERSION_CHECK", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from pipeline.adapters.shell.notify import notify  # noqa: E402
from pipeline.launcher.cli import reports  # noqa: E402
from pipeline.domain.outcomes.exit_codes import (  # noqa: E402
    EXIT_CRASH, EXIT_HALT, EXIT_INTERRUPTED, EXIT_OK)
from pipeline.runtime.filesystem.workspace import Workspace  # noqa: E402
from pipeline.runtime.monitoring import logbook  # noqa: E402
from pipeline.runtime.monitoring.logbook import Logbook  # noqa: E402
from pipeline.workflows.agentic_dev_loop.settings import (  # noqa: E402
    ConfigError, RunConfig)
from pipeline.workflows.agentic_dev_loop.workflow import (  # noqa: E402
    AgenticDevLoop)
from pipeline.workflows.legacy import migrate  # noqa: E402


def make_logger(log_dir: Path, *, run_id: str = "", level: int = logbook.NORMAL
                ) -> Logbook:
    """The run's journal: the terminal at `level`, `run.log` at full detail.

    The file always keeps DEBUG, so `--quiet` makes a cron job silent without
    also making its post-mortem useless.
    """
    return logbook.open_logbook("pipeline.loop", file=log_dir / "run.log",
                                level=level).bind(run_id)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="agent-loop",
        description="Run the docs pipeline unattended: one Claude Code session"
                    " per stage, the sequence expressed as a CrewAI Flow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="COMMAND — omit it to run the loop:\n"
               "  migrate   turn docs/ROADMAP.md and docs/current/ into GitHub\n"
               "            issues, once. Run it with --dry-run first: that\n"
               "            prints every issue it would open and writes\n"
               "            nothing. It is idempotent, and it gives nothing\n"
               "            the pipeline:ready label.\n"
               "\n"
               "Env overrides: INTEGRATION_BRANCH, PERMISSION_MODE, MAX_ROUNDS,\n"
               "STAGES, MODEL, EFFORT, ALLOW_DIRTY, HEARTBEAT_SECONDS.\n"
               "PIPELINE_CREWAI_PANELS=1 puts CrewAI's per-method ASCII panels\n"
               "back in the journal, for debugging the graph itself.\n"
               "The PR review has knobs of its own: scripts/pr-review --help.\n"
               "\n"
               "Exit codes — an outer scheduler reads these:\n"
               "  0    the run finished\n"
               "  1    stopped on purpose: a human has to look (a correct outcome)\n"
               "  2    a stage did not produce a usable result\n"
               "  3    subscription quota exhausted: re-run later, unchanged\n"
               "  4    unexpected error; the traceback is in run.log\n"
               "  130  interrupted")
    p.add_argument("command", nargs="?", choices=["migrate"], metavar="COMMAND",
                   help="`migrate` (see below); omit to run the loop")
    p.add_argument("--rounds", type=int, help="how many tasks to spend (default 3)")
    p.add_argument("--stages", help="run only these entries of the pipeline")
    p.add_argument("--branch", help="integration branch (default main_agent)")
    p.add_argument("--model", help="force one model on every stage")
    p.add_argument("--effort", help="force one effort level on every stage")
    p.add_argument("--costs", action="store_true", help="what this loop has spent, by stage")
    p.add_argument("--status", action="store_true", help="what a re-run would resume from")
    p.add_argument("--dry-run", action="store_true", help="write the prompts, call nothing")
    p.add_argument("--restart", action="store_true", help="forget the completed stages")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="every tool call on the terminal, not just the heartbeat")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="warnings and errors only (run.log keeps everything)")
    p.add_argument("--heartbeat", type=float, metavar="SECONDS",
                   help="how often a running stage reports in (default 60, 0 off)")
    # The register the loop already writes, read the two other ways a human
    # asks about it: per task, and per day.
    p.add_argument("--costs-by", choices=sorted(reports.GROUPS), metavar="FIELD",
                   help="break the ledger down by run|task|day|stage")
    p.add_argument("--costs-run", metavar="RUN_ID", default="",
                   help="restrict --costs-by to one run")
    p.add_argument("--costs-task", metavar="TEXT", default="",
                   help="restrict --costs-by to tasks matching this text")
    p.add_argument("--costs-since", metavar="YYYY-MM-DD", default="",
                   help="restrict --costs-by to rows from this date on")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> RunConfig:
    cfg = RunConfig(dry_run=args.dry_run, restart=args.restart,
                    workspace=Workspace.here())
    if args.rounds is not None:
        cfg.max_rounds = args.rounds
    if args.stages:
        cfg.stages = args.stages
    if args.branch:
        cfg.integration_branch = args.branch
    if args.model:
        cfg.model = args.model
    if args.effort:
        cfg.effort = args.effort
    if args.heartbeat is not None:
        cfg.heartbeat_s = args.heartbeat
    cfg.verbose = args.verbose
    cfg.quiet = args.quiet
    cfg.run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return cfg


def config_to_check(args: argparse.Namespace) -> RunConfig | None:
    """La config que la validation examine, ou None si ce run n'en batit pas.

    Les chemins rapides et `migrate` ne lisent aucune des valeurs validees :
    leur faire construire une config leur ferait payer une lecture
    d'environnement, et echouer sur une variable qu'ils n'utilisent pas.
    """
    if (args.command == "migrate" or args.status or args.costs
            or args.costs_by or args.costs_run or args.costs_task
            or args.costs_since):
        return None
    try:
        return build_config(args)
    except ConfigError:
        # Une config qui ne se construit pas ne se valide pas : `main` leve
        # la meme chose et l'imprime, comme avant.
        return None


def _verbosity(args: argparse.Namespace) -> int:
    """Le niveau auquel le terminal parle. Le fichier garde tout, toujours."""
    if args.verbose:
        return logbook.VERBOSE
    return logbook.QUIET if args.quiet else logbook.NORMAL


def _fast_path(args: argparse.Namespace) -> str | None:
    """Ce qu'un chemin rapide imprime, ou None si ce run doit vraiment tourner.

    Aucun de ces chemins ne construit de flow, ne charge le moteur, ni ne cree
    de repertoire de run.
    """
    if args.status:
        return reports.status_text(Workspace.here())
    if args.costs_by or args.costs_run or args.costs_task or args.costs_since:
        return reports.breakdown(Workspace.here().ledger,
                                 by=args.costs_by or "task",
                                 run=args.costs_run, task=args.costs_task,
                                 since=args.costs_since)
    if args.costs:
        return reports.report(Workspace.here().ledger)
    return None


def _stopped(log: Logbook, outcome, where: str) -> int:
    """Dit la fin du run au niveau qu'elle merite, previent, et rend son code.

    Le niveau vient du statut (`domain.outcomes.result`), pas d'un `if` par
    sorte : un arret volontaire est un resultat correct et ne se lit pas
    comme un avertissement, une panne de stage n'est pas un arret.
    """
    outcome.report(log)
    getattr(log, outcome.level)(f"logs: {where}")
    notify(outcome.reason)
    return outcome.exit_code


def _unbuildable(exc: ConfigError) -> int:
    """Un arret survenu avant qu'un journal existe : stderr est le seul canal.

    Une variable d'environnement illisible sortait ici en trace nue, avec un
    code 1 indistinguable d'un arret volontaire.
    """
    print(f"STOP — {exc}", file=sys.stderr)
    return EXIT_HALT


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # La migration ne fait pas tourner de round : elle traduit les documents
    # du pipeline en issues, une fois. Elle est ici, avec les chemins
    # rapides, parce qu'elle non plus n'a rien a faire du moteur.
    if args.command == "migrate":
        migrated = migrate.run(dry_run=args.dry_run,
                               workspace=Workspace.here())
        if migrated.failed:
            print(f"{migrated.prefix} — {migrated.reason}", file=sys.stderr)
            return migrated.exit_code
        print(migrated.value)
        return EXIT_OK

    quick = _fast_path(args)
    if quick is not None:
        print(quick)
        return EXIT_OK

    try:
        cfg = build_config(args)
    except ConfigError as exc:
        return _unbuildable(exc)

    log_dir = cfg.workspace.loop_dir / cfg.run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log = make_logger(log_dir, run_id=cfg.run_id, level=_verbosity(args))
    where = cfg.workspace.rel(log_dir)

    try:
        outcome = asyncio.run(AgenticDevLoop(cfg, log, log_dir).run())
    except KeyboardInterrupt:
        log.warn("interrupted")
        return EXIT_INTERRUPTED
    except Exception:
        # The worst case this exists for: a ValidationError, a crewai internal,
        # a sqlite or an OSError used to escape as a traceback on a stderr
        # nobody kept, and run.log simply stopped mid-round with no reason.
        # It goes into the journal first, and still fails loudly.
        log.exception("CRASH — the run died on an unexpected error")
        log.error(f"logs: {where}")
        notify(f"loop crashed — see {where}/run.log")
        return EXIT_CRASH

    # Le run s'est arrete : la raison est dans le resultat, pas dans une
    # exception qu'il aurait fallu attraper par sorte.
    if outcome.failed:
        return _stopped(log, outcome, where)
    log(outcome.summary)

    if not cfg.dry_run:
        for line in reports.report(cfg.workspace.ledger).splitlines():
            log("  " + line)
        # Combien de tasks sont fermees ne se compte plus ici : c'est GitHub
        # qui les ferme, et une notification n'a pas a coûter un appel d'API.
        notify(f"loop finished — logs in {where}")
    return EXIT_OK
