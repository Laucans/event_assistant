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

# Le nom du stage de coherence, defini ici et re-exporte par
# `stages/__init__.py` (`COHERENCE = publish.COHERENCE`) — comme `ROUTER` vit
# dans `gates.py` : cette valeur n'a besoin d'aucun import de `stages`, qui
# lui importe deja ce module.
COHERENCE = "coherence"


def write(ctx, state) -> Result[None]:
    """L'etape de publication : le corps, le commentaire, les etiquettes."""
    cfg, log = ctx.cfg, ctx.log
    num, issue = cfg.issue, state.issue
    gh = adapters.gh(cfg.workspace)

    found = sections.merge(state.found, state.wanted, ctx.results)

    # La coherence a lu ce merge et peut l'avoir retouche. `None` couvre le
    # dry-run et toute reprise qui l'a saute — rien a appliquer. Une sortie
    # qui ne garde pas toutes les cles (vide, sans titres reconnus, une
    # section perdue) est ignoree en bloc plutot qu'appliquee en partie :
    # retoucher trois sections entre elles puis perdre la quatrieme creerait
    # une incoherence de plus au lieu d'en resoudre une. Les sessions ont
    # deja ete payees, donc ce round publie quand meme — au pire sans ses
    # retouches, jamais en echouant sur elles.
    reconciled = ctx.results.get(COHERENCE)
    if reconciled is not None:
        retouched = sections.parse(reconciled.text)
        dropped = [key for key in found if not (retouched.get(key) or "").strip()]
        if dropped:
            log.warn(f"the coherence pass dropped {' '.join(dropped)} from"
                     f" the body — publishing without its retouches")
        else:
            found = retouched

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
