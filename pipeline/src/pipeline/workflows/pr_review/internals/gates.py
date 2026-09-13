"""Ce qu'une etape de la revue exige, et ce qui la fait sauter.

A ne pas confondre avec les portes de `preconditions.py` : celles-la sont
celles du **workflow**, verifiees une fois avant tout. Celles-ci n'ont de
sens que dans la sequence de la revue, et vivent donc avec elle.

Aucune ne leve : chacune rend un `Result` que la sequence propage.
"""

from __future__ import annotations

from pipeline.core.domain.outcomes.result import Result, Status

# Ce que la passe 2 recoit quand la passe 1 n'a rien laisse. Les deux cas se
# distinguent, parce qu'ils ne veulent pas dire la meme chose au relecteur.
NOT_ASKED = "(inline pass skipped)"
NOTHING_BACK = "(the inline pass did not run; no findings were posted)"


def inline_pass_is_off(ctx, state) -> Result[str]:
    """`--no-inline` : le commentaire de synthese, et rien d'autre."""
    if not ctx.cfg.no_inline:
        return Result.of("")
    return Result.of("pass 1/2 skipped — --no-inline")


def nothing_is_posted(ctx, state) -> Result[str]:
    """Un dry-run ne poste rien : il a ecrit les prompts et s'arrete la."""
    if not ctx.cfg.dry_run:
        return Result.of("")
    return Result.of("dry run — nothing posted")


def findings(ctx) -> str:
    """Ce que la passe 1 a rendu, ou pourquoi il n'y a rien."""
    got = ctx.results.get("inline")
    if got is None:
        return NOT_ASKED if ctx.cfg.no_inline else NOTHING_BACK
    return got.text


def a_silent_inline_pass_is_not_fatal(step, failed) -> str | None:
    """La passe 1 peut ne rien rendre sans que les notes perdent leur valeur.

    Un quota epuise est l'exception, et c'est pourquoi ce n'est pas un
    booleen : la passe 2 depenserait la meme fenetre et reviendrait pareil.
    """
    if step.skill != "inline" or failed.status is Status.QUOTA:
        return None
    return "  inline pass produced no review — continuing without it"
