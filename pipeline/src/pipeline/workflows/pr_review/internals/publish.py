"""Le commentaire de synthese : monte, garde sur disque, puis poste.

Ecrit avant d'etre poste : si `gh` echoue, le texte existe encore et le
message d'erreur peut dire ou — deux passes payantes ne se perdent pas parce
qu'un appel reseau a rate.
"""

from __future__ import annotations

import datetime

from pipeline.adapters.shell.github import GitHub
from pipeline.adapters.store import ledger
from pipeline.domain.outcomes.result import Result
from pipeline.domain.pr_review import notes as review_notes
from pipeline.domain.prompts import prompt_builder as prompts
from pipeline.runtime.monitoring.logbook import Logbook
from pipeline.workflows.pr_review.settings import ReviewConfig


def _passes_line(cfg: ReviewConfig) -> str:
    """Ce que le pied de page dit des passes qui ont produit ces notes."""
    if cfg.no_inline:
        return f"notes `{cfg.brief_model}` (passe ligne à ligne désactivée)"
    return (f"findings `{cfg.inline_model}`/niveau `{cfg.level}`,"
            f" notes `{cfg.brief_model}`")


def publish(cfg: ReviewConfig, num: str, url: str, body: str, log: Logbook,
            hub: GitHub) -> Result[None]:
    """Monte le commentaire, le garde sur disque, puis le poste."""
    cost = ledger.review_cost(cfg.workspace.review_ledger, num)
    path = cfg.workspace.review_dir / f"{num}-comment.md"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    footer = prompts.fill(review_notes.FOOTER, passes=_passes_line(cfg),
                          cost=f", coût ${cost}" if cost else "")
    # Ecrit avant d'etre poste : si `gh` echoue, le texte existe encore et le
    # message d'erreur peut dire ou.
    path.write_text(review_notes.comment(review_notes.MARKER, stamp, body,
                                         footer), encoding="utf-8")
    posted, why = hub.post_comment(num, path)
    if not posted:
        # Deux passes payees : la raison dit ou est le texte et comment le
        # poster a la main. Elle n'est pas journalisee ici — le point
        # d'entree la dit une fois.
        return Result.fail(
            f"gh could not post the comment on PR #{num} ({why}) — the text"
            f" is kept at {cfg.workspace.rel(path)}; post it by hand:"
            f" gh pr comment {num} --body-file {cfg.workspace.rel(path)}")
    log(f"posted — {url}  (this review cost ${cost or '?'})")
    return Result.of(None)
