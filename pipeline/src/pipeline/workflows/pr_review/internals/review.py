"""Ce que la revue etablit avant de payer, et le verrou qu'elle tient.

Ce module ne fait plus tourner les passes : elles sont dans la table de
`stages/`, et la forme `Once` les enchaine. Ce qui reste ici est ce qui
entoure la sequence — lire la PR, decider qu'il n'y a rien a revoir, et ne
pas la revoir deux fois a la fois.

**Une revue sautee est un succes**, pas un manquement : une PR en brouillon
ou deja revue n'a rien a obtenir. C'est ce que le pre-controle d'une forme
rend en une phrase plutot qu'en un echec.
"""

from __future__ import annotations

from pipeline.core.adapters import hub as adapters
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.domain.pulls import Pr
from pipeline.core.runtime.filesystem.lock import claim
from pipeline.workflows.pr_review.internals.skip_rules import skip_reason


class ReviewState:
    """Ce que les etapes de la revue se transmettent."""

    def __init__(self) -> None:
        self.stages_done: list[str] = []
        self.pr: Pr | None = None


def _cannot(cfg, said: str, channel: str) -> Result[str]:
    """Une lecture qui n'a pas abouti.

    Rien n'est journalise ici : la raison voyage dans le `Result`, et le
    point d'entree la dit une fois, au bon niveau. Elle sortait deux fois —
    une fois posee ici, une fois par `report()`.

    `warn` reste, et c'est un autre canal : la revue tourne detachee d'un
    hook, donc ce qui ne va que dans le fichier de log n'apparait devant
    personne. C'est la ligne directe vers l'operateur.
    """
    if cfg.warn is not None:
        cfg.warn(channel)
    return Result.fail(said)


def precheck(cfg, log, state: ReviewState) -> Result[str]:
    """Y a-t-il quelque chose a revoir ? Pose la PR dans l'etat au passage."""
    gh = adapters.gh(cfg.workspace)

    pr, why = gh.pr(cfg.pr)
    if pr is None:
        return _cannot(cfg, f"cannot read PR {cfg.pr} — {why}",
                       f"pr-review: cannot read PR {cfg.pr}")
    state.pr = pr

    comments = ""
    if not cfg.force:
        comments, why = gh.comment_bodies(state.pr.num)
        if comments is None:
            return _cannot(
                cfg,
                f"cannot tell whether PR #{state.pr.num} was already reviewed"
                f" — {why}",
                f"pr-review: cannot read the comments of PR #{state.pr.num}")

    skip = skip_reason(cfg, pr, comments)
    if skip:
        return Result.of(f"skip — {skip}")
    log(f"reviewing #{pr.num}  {pr.head} -> {pr.base}  ({pr.title})")
    return Result.of("")


def one_at_a_time(cfg, state: ReviewState):
    """Le garde de la forme : au plus une revue de cette PR a la fois.

    Deux hooks qui partiraient sur la meme PR posteraient la revue deux fois.
    """
    return claim(cfg.workspace.review_dir, state.pr.num)


def already_running(cfg, state: ReviewState) -> str:
    return f"skip — a review of PR #{state.pr.num} is already running"


def summary(cfg, state: ReviewState) -> str:
    """La ligne qu'une revue arrivee au bout laisse derriere elle."""
    if cfg.dry_run:
        return "dry run — nothing posted"
    return f"reviewed #{state.pr.num}"
