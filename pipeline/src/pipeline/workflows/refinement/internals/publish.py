"""Le corps de l'issue : assemble, garde sur disque, puis envoye.

Ecrit avant d'etre envoye : si `gh` echoue, le texte existe encore et le
message d'erreur dit ou — des sections payantes ne se perdent pas parce qu'un
appel reseau a rate.
"""

from __future__ import annotations

from pipeline.core.adapters import hub as adapters
from pipeline.core.domain.outcomes.result import Result
from pipeline.workflows.common import labels
from pipeline.workflows.refinement.internals import rounds, sections


def write(ctx, state) -> Result[None]:
    """L'etape de publication : le corps, le commentaire, les etiquettes."""
    cfg, log = ctx.cfg, ctx.log
    num, issue = cfg.issue, state.issue
    gh = adapters.gh(cfg.workspace)

    found = dict(state.found)
    for key in state.wanted:
        got = ctx.results.get(key)
        # Un stage qui n'a rien rendu laisse la section precedente en place
        # plutot que de l'effacer.
        text = (got.text.strip() if got is not None else "")
        if text:
            found[key] = text

    body = sections.render(found)
    if not body.strip():
        return Result.fail(
            f"nothing to write into #{num} — no stage produced a section and"
            f" the body carried none")

    path = cfg.workspace.refinement_dir / f"{num}-r{state.round_no:02d}-body.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    written = gh.set_body(num, body)
    if written.failed:
        return Result.fail(
            f"gh could not rewrite the body of #{num} ({written.reason}) —"
            f" the text is kept at {cfg.workspace.rel(path)}; write it by"
            f" hand: gh issue edit {num} --body-file"
            f" {cfg.workspace.rel(path)}")

    # Seulement si elle etait la : `gh` rend 404 en retirant une etiquette
    # absente, ce qui est le cas de tout round parti sur `--force`.
    if issue.has(labels.REFINEMENT):
        dropped = gh.remove_label(num, labels.REFINEMENT)
        if dropped.failed:
            return dropped.recast()

    # Trois sections suffisent a un humain pour agir : sa task est specifiee
    # des le round 1.
    due = 1 if issue.has(labels.HUMAN) else 2
    if state.round_no >= due:
        marked = gh.add_label(num, labels.SPEC_WRITTEN)
        if marked.failed:
            return marked.recast()

    # Le compteur en dernier : il est ce qui dit que ce round a eu lieu. Pose
    # avant une etiquette qui echoue, il ferait repartir la reprise au round
    # suivant — cinq sessions la ou il en fallait deux.
    posted = gh.post_issue_comment(num, rounds.comment(state.round_no))
    if posted.failed:
        return posted.recast()

    log(f"#{num} — round {state.round_no} written"
        f" ({' '.join(state.wanted)})")
    return Result.of(None)
