"""Ce que le raffinage etablit avant de payer, et le verrou qu'il tient.

Les quatre refus sont ici, avant toute session : une issue fermee, une issue
qui n'est pas une task, une issue non etiquetee, et une lecture de
commentaires qui n'aboutit pas — celle-la surtout, parce qu'une liste vide
ferait repartir le compteur a 1 et reecrirait le corps entier.
"""

from __future__ import annotations

from pipeline.core.adapters import hub as adapters
from pipeline.core.domain.issues import Issue
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.filesystem.lock import claim
from pipeline.workflows.common import labels
from pipeline.workflows.refinement.internals import rounds, sections


class RefinementState:
    """Ce que les etapes du raffinage se transmettent."""

    def __init__(self) -> None:
        self.stages_done: list[str] = []
        self.issue: Issue | None = None
        self.round_no: int = 0
        self.found: dict[str, str] = {}
        self.wanted: list[str] = []


def _unread(cfg, got: Result, channel: str) -> Result[str]:
    """Une lecture qui n'a pas abouti : le meme echec, dit aussi a l'appelant.

    La raison voyage dans le `Result`, inchangee. `warn` est un autre canal :
    un round lance par un declencheur tourne detache, donc ce qui ne va que
    dans le fichier de log n'apparait devant personne.
    """
    if cfg.warn is not None:
        cfg.warn(channel)
    return got.recast()


def precheck(cfg, log, state: RefinementState) -> Result[str]:
    """Ce que l'issue doit etre, et a quel round elle en est.

    Rend toujours la chaine vide quand ca passe : un round a toujours quelque
    chose a ecrire.
    """
    gh = adapters.gh(cfg.workspace)

    got = gh.issue(cfg.issue)
    if got.failed:
        return _unread(cfg, got, f"refinement: cannot read issue #{cfg.issue}")
    issue = got.value
    state.issue = issue

    if issue.closed:
        return Result.halt(f"#{cfg.issue} is closed — reopen it, or refine"
                           f" another issue")
    if not (issue.has(labels.AGENT) or issue.has(labels.HUMAN)):
        return Result.halt(
            f"#{cfg.issue} carries neither {labels.AGENT} nor {labels.HUMAN}"
            f" — refinement works a task: add one of the two to it, or refine"
            f" another issue")
    if not issue.has(labels.REFINEMENT) and not cfg.force:
        return Result.halt(
            f"#{cfg.issue} does not carry {labels.REFINEMENT} — add it with"
            f" `gh issue edit {cfg.issue} --add-label {labels.REFINEMENT}`,"
            f" or re-run with --force")

    # Une lecture ratee n'est jamais lue comme « aucun commentaire » : le
    # round repartirait a 1 et reecrirait le corps par-dessus deux rounds.
    comments = gh.issue_comments(cfg.issue)
    if comments.failed:
        return _unread(cfg, comments,
                       f"refinement: cannot read the comments of issue"
                       f" #{cfg.issue}")

    state.round_no = rounds.counter(comments.value) + 1
    cfg.round_no = state.round_no
    state.found = sections.parse(issue.body)
    state.wanted = list(rounds.planned(state.round_no, state.found,
                                       bool(cfg.context)))
    said = " ".join(state.wanted) or "router decides"
    log(f"refining #{cfg.issue} — round {state.round_no} ({said})")
    # Ou tombent les prompts et les enveloppes de ce round.
    artifacts(cfg).mkdir(parents=True, exist_ok=True)
    return Result.of("")


def artifacts(cfg):
    """Le dossier des artefacts de cette issue."""
    return cfg.workspace.refinement_dir / str(cfg.issue)


def one_at_a_time(cfg, state: RefinementState):
    """Le garde de la forme : au plus un raffinage de cette issue a la fois."""
    return claim(cfg.workspace.refinement_dir, str(cfg.issue))


def already_running(cfg, state: RefinementState) -> str:
    return f"skip — a refinement of issue #{cfg.issue} is already running"


def summary(cfg, state: RefinementState) -> str:
    """La ligne qu'un round arrive au bout laisse derriere lui."""
    if cfg.dry_run:
        return "dry run — nothing written"
    return f"refined #{cfg.issue} — round {state.round_no}"
