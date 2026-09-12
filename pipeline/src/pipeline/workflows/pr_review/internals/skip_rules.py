"""Quelles PR la revue laisse passer sans rien depenser.

Une revue par task, pas par PR : /code et /create-test ouvrent chacun une PR,
et revoir celle des tests reverrait deux fois le meme changement. Les branches
`test/*` sont sautees.
"""

from __future__ import annotations

from pipeline.workflows.pr_review.internals import notes as review_notes
from pipeline.workflows.pr_review.settings import ReviewConfig

# Les metadonnees dont les regles de saut ont besoin, en un appel.
PR_FIELDS = "number,baseRefName,headRefName,title,url,state,isDraft"


def skip_reason(cfg: ReviewConfig, meta: dict, comments: str) -> str | None:
    """Pourquoi cette PR n'a pas a etre revue, ou None.

    Les quatre regles au meme endroit : c'est ce qui permet de les lire comme
    une politique plutot que comme une suite de retours anticipes noyes dans
    l'orchestration. `--force` les leve toutes.
    """
    if cfg.force:
        return None
    num, base = str(meta["number"]), meta["baseRefName"]
    if base != cfg.base:
        return (f"PR #{num} targets '{base}', not '{cfg.base}'"
                " (--force to override)")
    if meta["isDraft"]:
        return f"PR #{num} is a draft"
    if meta["headRefName"].startswith("test/"):
        return (f"#{num} is the test PR for a change already reviewed on its"
                " /code PR (--force to review it anyway)")
    if review_notes.MARKER in comments:
        return f"PR #{num} already carries an agent review (--force to redo)"
    return None
