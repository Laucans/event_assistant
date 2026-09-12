"""La revue consultative d'une PR, de bout en bout.

Deux passes `claude -p` sur la meme PR, toutes deux livrees sur la PR :

1. `/code-review <niveau> <pr> --comment` — les findings postes en ligne, sur
   le fichier:ligne qu'ils concernent ;
2. les notes du relecteur — un commentaire de synthese : ce que fait le lot,
   ou regarder d'abord, ce que l'agent a suppose, ce qui merite une question.

Consultative : elle ne bloque rien, ne merge rien, ne touche aucune branche.
La boucle peut merger la PR pendant que la revue s'ecrit encore.

Les regles qui decident qu'une PR n'a pas a etre revue vivent dans
`skip_rules`, les deux passes dans `passes`, le commentaire dans `publish`.
Ce module est l'orchestration, et rien d'autre.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from pipeline.core.adapters.agent import AgentRunner
from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common.contract.outcome import WorkflowOutcome
from pipeline.workflows.common.utils import hub as adapters
from pipeline.workflows.pr_review.internals import passes, publish
from pipeline.workflows.pr_review.internals.pr import Pr
from pipeline.workflows.pr_review.internals.skip_rules import (
    PR_FIELDS, skip_reason)
from pipeline.workflows.pr_review.settings import ReviewConfig


def _cannot(warn: Callable[[str], None] | None, said: str,
            channel: str) -> Result[None]:
    """Une lecture qui n'a pas abouti.

    Rien n'est journalise ici : la raison voyage dans le `Result`, et le
    point d'entree la dit une fois, au bon niveau. Elle sortait deux fois —
    une fois posee ici, une fois par `report()`.

    `warn` reste, et c'est un autre canal : la revue tourne detachee d'un
    hook, donc ce qui ne va que dans le fichier de log n'apparait devant
    personne. C'est la ligne directe vers l'operateur.
    """
    if warn is not None:
        warn(channel)
    return Result.fail(said)


@contextlib.contextmanager
def claim(review_dir: Path, num: str):
    """Le verrou d'une PR. Rend False si une autre revue la tient deja.

    Deux hooks qui partiraient sur la meme PR posteraient la revue deux fois.
    """
    review_dir.mkdir(parents=True, exist_ok=True)
    lock = review_dir / f".lock-{num}"
    try:
        lock.mkdir()
    except FileExistsError:
        yield False
        return
    try:
        yield True
    finally:
        with contextlib.suppress(OSError):
            lock.rmdir()


async def _both_passes(cfg: ReviewConfig, pr: Pr, log: Logbook, gh: GitHub,
                       runner: AgentRunner | None) -> WorkflowOutcome:
    """Les deux passes et la publication, une fois le verrou tenu."""
    log(f"reviewing #{pr.num}  {pr.head} -> {pr.base}  ({pr.title})")

    found = await passes.findings(cfg, pr, log, runner)
    if found.failed:
        return WorkflowOutcome.of_result(found)

    body = await passes.brief(cfg, pr, found.value, log, runner)
    if body.failed:
        return WorkflowOutcome.of_result(body)
    if cfg.dry_run:
        log("dry run — nothing posted")
        return WorkflowOutcome.done("dry run — nothing posted")

    posted = publish.publish(cfg, pr.num, pr.url, body.value, log, gh)
    if posted.failed:
        return WorkflowOutcome.of_result(posted)
    return WorkflowOutcome.done(f"reviewed #{pr.num}")


async def run(cfg: ReviewConfig, log: Logbook, *, gh: GitHub | None = None,
              runner: AgentRunner | None = None,
              warn: Callable[[str], None] | None = None) -> WorkflowOutcome:
    """Fait la revue, et rend ce que le CLI propage en code de sortie."""
    gh = gh or adapters.gh(cfg.workspace)

    meta, why = gh.pr(cfg.pr, PR_FIELDS)
    if meta is None:
        return WorkflowOutcome.of_result(_cannot(
            warn, f"cannot read PR {cfg.pr} — {why}",
            f"pr-review: cannot read PR {cfg.pr}"))
    pr = Pr.of(meta)

    comments = ""
    if not cfg.force:
        comments, why = gh.comment_bodies(pr.num)
        if comments is None:
            return WorkflowOutcome.of_result(_cannot(
                warn,
                f"cannot tell whether PR #{pr.num} was already reviewed"
                f" — {why}",
                f"pr-review: cannot read the comments of PR #{pr.num}"))

    skip = skip_reason(cfg, meta, comments)
    if skip:
        log(f"skip — {skip}")
        return WorkflowOutcome.done(f"skip — {skip}")

    with claim(cfg.workspace.review_dir, pr.num) as mine:
        if not mine:
            said = f"skip — a review of PR #{pr.num} is already running"
            log(said)
            return WorkflowOutcome.done(said)
        return await _both_passes(cfg, pr, log, gh, runner)
