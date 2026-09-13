"""Ce qu'une etape du raffinage exige, et ce qui la fait sauter.

A ne pas confondre avec la porte de `preconditions.py`, qui est celle du
workflow et se verifie une fois avant tout. Aucune ne leve : chacune rend un
`Result` que la sequence propage.
"""

from __future__ import annotations

from pipeline.core.domain.outcomes.result import Result
from pipeline.workflows.refinement.internals import rounds

ROUTER = "router"


def section_is_wanted(key: str):
    """La fabrique du `skip` d'un stage de section : ce round l'ecrit-il ?"""

    def skip(ctx, state) -> Result[str]:
        if key in state.wanted:
            return Result.of("")
        return Result.of(f"{key} — not in this round")

    return skip


def router_is_off(ctx, state) -> Result[str]:
    """Le routeur ne tourne qu'a partir du round 3, et avec un `--context`."""
    if rounds.routed(state.round_no, bool(ctx.cfg.context)):
        return Result.of("")
    return Result.of(f"{ROUTER} — this round writes a fixed set of sections")


def router_named_sections(ctx, state) -> Result[None]:
    """Ce que le routeur doit avoir obtenu : les sections a rouvrir.

    Un dry-run ne fait tourner personne et ne laisse donc rien a lire :
    `state.wanted` reste ce que le precontrole a pose.
    """
    got = ctx.results.get(ROUTER)
    if got is None:
        return Result.of(None)
    state.wanted = list(rounds.wanted_from(got.text))
    if not state.wanted:
        return Result.fail(
            "the router named no section to reopen, so this round would write"
            " nothing — re-run with a --context that names what to rework, or"
            " without --context to rewrite all five sections")
    return Result.of(None)


def nothing_is_written(ctx, state) -> Result[str]:
    """Un dry-run n'ecrit rien : il a ecrit les prompts et s'arrete la."""
    if not ctx.cfg.dry_run:
        return Result.of("")
    return Result.of("dry run — nothing written")
