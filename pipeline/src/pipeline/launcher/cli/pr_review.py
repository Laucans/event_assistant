"""L'entree de la revue de PR : les flags, l'environnement, le code de sortie.

Aucune decision ici. Les flags et les defauts d'environnement deviennent un
`ReviewConfig`, l'orchestration part dans `workflows.pr_review`, et ce
qui remonte devient un code de sortie — le seul signal qu'un appelant
exterieur recoit, puisque le hook PostToolUse lance ceci **detache**.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import traceback

# Meme raison que la boucle : `claude -p` facture ce sous quoi la CLI est
# authentifiee, et une cle dans l'environnement sortirait la revue de
# l'abonnement.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
# Lu par le hook PostToolUse qui lance cette revue : les appels `gh` faits
# *dans* la revue ne doivent pas en declencher une seconde.
os.environ["PR_REVIEW_ACTIVE"] = "1"

from pipeline.domain.outcomes.exit_codes import (  # noqa: E402
    EXIT_CRASH, EXIT_INTERRUPTED)
from pipeline.runtime.filesystem.workspace import Workspace  # noqa: E402
from pipeline.runtime.monitoring import logbook  # noqa: E402
from pipeline.runtime.monitoring.logbook import Logbook  # noqa: E402
from pipeline.workflows.pr_review.settings import ReviewConfig  # noqa: E402
from pipeline.workflows.pr_review.workflow import PrReview  # noqa: E402


def token(pr: str) -> str:
    """A filename-safe handle for a PR given as a number or as a URL."""
    match = re.search(r"(\d+)\s*$", pr)
    return match.group(1) if match else re.sub(r"[^0-9A-Za-z._-]", "-", pr)[:40]


def make_logger(pr: str, workspace: Workspace, *,
                level: int = logbook.NORMAL) -> Logbook:
    """Le journal de la revue — sur le terminal et, desormais, sur disque.

    Une revue lancee a la main ne laissait aucune trace : seul le chemin
    lance par le hook redirigeait stdout vers un fichier, donc
    `scripts/pr-review 12` depensait deux passes payantes et ne gardait rien.
    Le tampon de contexte dit `pr-review#12`, et c'est ce qui rend les lignes
    d'une revue separables de celles de la boucle quand les deux ecrivent
    dans le meme terminal.
    """
    handle = token(pr)
    return logbook.open_logbook(
        "pipeline.review", file=workspace.review_dir / f"{handle}.log",
        level=level).bind(f"pr-review#{handle}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a PR opened against the integration branch and leave"
                    " the notes a human needs to read it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Env overrides — an undiscoverable knob is a knob nobody turns:\n"
               "  INTEGRATION_BRANCH        the base a PR must target to be reviewed\n"
               "  PR_REVIEW_LEVEL           /code-review level for pass 1\n"
               "  PR_REVIEW_MODEL           force one model on both passes\n"
               "  PR_REVIEW_INLINE_MODEL    model of pass 1 (default sonnet)\n"
               "  PR_REVIEW_INLINE_EFFORT   effort of pass 1 (default medium)\n"
               "  PR_REVIEW_BRIEF_MODEL     model of pass 2 (default sonnet)\n"
               "  PR_REVIEW_BRIEF_EFFORT    effort of pass 2 (default low)\n"
               "PR_REVIEW_ACTIVE is exported to the sessions this launches, so the\n"
               "PostToolUse hook does not start a second review from inside one.\n"
               "\n"
               "Exit codes — the hook launches this detached, so they are the\n"
               "only signal an outer caller gets:\n"
               "  0    reviewed, or deliberately skipped\n"
               "  2    the review could not be produced or could not be posted\n"
               "  3    subscription quota exhausted: re-run later, unchanged\n"
               "  4    unexpected error; the traceback is in the review log\n"
               "  130  interrupted")
    p.add_argument("pr", help="PR number or URL")
    p.add_argument("--level", default=os.environ.get("PR_REVIEW_LEVEL", "medium"),
                   help="/code-review level: low|medium|high|max")
    p.add_argument("--base", default=os.environ.get("INTEGRATION_BRANCH", "main_agent"))
    p.add_argument("--model", default=os.environ.get("PR_REVIEW_MODEL", ""),
                   help="force one model on both passes")
    p.add_argument("--force", action="store_true",
                   help="review a PR whose base is not the integration branch,"
                        " whose head is a test/* branch, or one already reviewed")
    p.add_argument("--no-inline", action="store_true", help="summary comment only")
    p.add_argument("--dry-run", action="store_true", help="write the prompts, call nothing")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="every tool call on the terminal, not just the heartbeat")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="warnings and errors only (the log file keeps everything)")
    p.add_argument("--heartbeat", type=float, default=60.0, metavar="SECONDS",
                   help="how often a running pass reports in (default 60, 0 off)")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> ReviewConfig:
    """Les flags et l'environnement, resolus en une config de revue.

    `--model` force les deux passes ; les quatre `PR_REVIEW_*_MODEL/EFFORT`
    les reglent separement, parce que ce ne sont pas le meme travail.
    """
    return ReviewConfig(
        pr=args.pr,
        base=args.base,
        level=args.level,
        force=args.force,
        no_inline=args.no_inline,
        dry_run=args.dry_run,
        verbose=args.verbose,
        quiet=args.quiet,
        heartbeat_s=args.heartbeat,
        inline_model=args.model or os.environ.get("PR_REVIEW_INLINE_MODEL", "sonnet"),
        inline_effort=os.environ.get("PR_REVIEW_INLINE_EFFORT", "medium"),
        brief_model=args.model or os.environ.get("PR_REVIEW_BRIEF_MODEL", "sonnet"),
        brief_effort=os.environ.get("PR_REVIEW_BRIEF_EFFORT", "low"),
        workspace=Workspace.here(),
    )


def config_to_check(args: argparse.Namespace) -> ReviewConfig:
    """La config que la validation examine."""
    return build_config(args)


def main(argv: list[str] | None = None) -> int:
    """Run the review, and let nothing escape as a traceback nobody reads.

    The loop grew this handler after a crash left `run.log` stopping mid-round
    with no reason. The review needs it more, not less: the PostToolUse hook
    launches it **detached**, so an unhandled exception goes to whatever the
    hook redirected — which is to say, to nobody.
    """
    try:
        return asyncio.run(_main(argv))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception:
        try:
            make_logger(_pr_arg(argv), Workspace.here()).exception(
                "CRASH — the review died on an unexpected error")
        except Exception:
            # Reporting the crash must not become the crash.
            traceback.print_exc()
        return EXIT_CRASH


def _pr_arg(argv: list[str] | None) -> str:
    """La PR dont parlait le run qui a plante, pour nommer son log.

    On redemande a argparse plutot que de deviner : un balayage qui rend le
    premier jeton sans tiret rend la *valeur* d'un flag des qu'un flag value
    precede le positionnel, et `--level high 12` ecrivait la trace du crash
    dans `high.log`. Comme le hook lance la revue detachee, ce fichier mal
    nomme est la seule trace qui reste.

    Le repli garde l'ancien balayage : ce code tourne dans un gestionnaire de
    crash, ou ne rien rendre du tout serait pire qu'un nom approximatif.
    """
    args = sys.argv[1:] if argv is None else argv
    try:
        return parse_args(args).pr
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
    log = make_logger(args.pr, cfg.workspace, level=level)
    # Le hook lance ceci detache : stderr est la seule chose qu'un appelant
    # qui n'ouvre pas le fichier de log verra passer. Le workflow dit ce qui
    # merite ce canal-la, le CLI decide que ce canal est stderr.
    outcome = await PrReview(
        cfg, log, warn=lambda msg: print(msg, file=sys.stderr)).run()
    return outcome.report(log).exit_code
