"""Les deux passes payantes d'une revue, et ce qu'une passe muette vaut.

Chaque passe porte son modele et son effort, parce que ce n'est pas le meme
travail. /code a deja fait tourner une revue adverse avant de merger : la
passe 1 est un second avis en contexte neuf, pas la seule ligne de defense.
La passe 2 resume ce que la passe 1 et le diff disent deja — c'est de la
redaction, pas une chasse.
"""

from __future__ import annotations

from pipeline.core.adapters.agent import AgentRunner, default_runner, progress
from pipeline.core.adapters.store import envelope, ledger
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.domain import prompts
from pipeline.workflows.pr_review.stages import BRIEF_PROMPT
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.pr_review.internals.pr import Pr
from pipeline.workflows.pr_review.settings import ReviewConfig

# Ce qu'une passe garde sur disque : la poignee qui lui sert a s'expliquer,
# la ou un stage garde tout. Noms de champs du fournisseur, lus dans `raw`.
ENVELOPE = ("subtype", "is_error", "total_cost_usd", "api_error_status",
            "result")


# Ce qu'une passe qui n'a rien rendu vaut : le niveau auquel le journal le
# dit, et la ligne. Le quota est un avertissement et non une erreur — la passe
# n'a pas casse, elle a ete coupee, et relancer maintenant ne ferait que
# redepenser la meme fenetre.
#
# L'identifiant de session voyage dans chacune : il atteignait le registre et
# l'enveloppe, jamais le journal, alors que c'est la seule cle qui rouvre
# exactement la passe en panne.
PASS_FAILURES = {
    "quota": ("warn", "  the {label} pass ran out of subscription quota —"
                      " retry later (session {session})"),
    "failed": ("error", "  the {label} pass failed ({subtype}) —"
                        " session {session}"),
    "empty": ("error", "  the {label} pass returned an empty result —"
                       " session {session}"),
}


def pass_failure(reason: str | None, *, label: str, subtype: str,
                 session: str) -> tuple[str, str] | None:
    """`(niveau, ligne)` quand la passe n'a rien rendu, ou None."""
    said = PASS_FAILURES.get(reason or "")
    if said is None:
        return None
    level, template = said
    return level, template.format(label=label, subtype=subtype,
                                  session=session)


async def run_pass(prompt: str, label: str, model: str, effort: str, num: str,
                   dry_run: bool, log: Logbook, *, workspace: Workspace,
                   heartbeat_s: float = 60.0,
                   verbose: bool = False, runner: AgentRunner | None = None
                   ) -> tuple[str | None, str | None]:
    """Une passe. Rend `(texte, raison)`.

    La raison est `None` quand la passe a repondu, et dit sinon quelle sorte
    de rien est revenue — `"quota"`, `"failed"`, `"empty"`, `"no-result"`,
    `"dry-run"`. L'appelant en fait un `Result`, et « reviens plus tard »
    n'est pas la meme consigne que « c'est casse ».
    """
    if dry_run:
        print(f"--- prompt ({label}, model={model} effort={effort}) ---"
              f"\n{prompt}\n--- end ---")
        return None, "dry-run"

    # Une passe de revue est aussi opaque qu'un stage l'etait : meme
    # battement, meme trace, gardee a cote du commentaire qu'elle a produit.
    watch = progress.Progress(log.bind(label), heartbeat_s=heartbeat_s,
                              verbose=verbose,
                              trace=workspace.review_dir
                              / f"{num}-{label}.trace.log")
    result = await (runner or default_runner(workspace)).run(
        prompt, model=model, effort=effort,
        permission_mode="bypassPermissions", progress=watch)
    log(f"  {watch.census()}")
    if result is None:
        log.error(f"  the {label} pass returned no result at all")
        return None, "no-result"

    envelope.write(workspace.review_dir / f"{num}-{label}.json", result.raw,
                   ENVELOPE)

    ledger.append_review(workspace.review_ledger, pr=num, label=label,
                         **result.ledger_fields(model=model, effort=effort))

    reason = result.failure
    said = pass_failure(reason, label=label, subtype=result.subtype,
                        session=result.session_id)
    if said is not None:
        level, line = said
        getattr(log, level)(line)
        return None, reason
    log.debug(f"  {label} pass session {result.session_id}")
    return result.text, None


async def findings(cfg: ReviewConfig, pr: Pr, log: Logbook,
                   runner: AgentRunner | None) -> Result[str]:
    """La passe 1 : les findings, postes en ligne sur la PR.

    Un quota epuise arrete la revue ici : la seconde passe depenserait la
    meme fenetre et reviendrait pareil.
    """
    if cfg.no_inline:
        return Result.of("(inline pass skipped)")
    log(f"pass 1/2 — /code-review {cfg.level} {pr.num} --comment"
        f"  ({cfg.inline_model}, effort {cfg.inline_effort})")
    got, why = await run_pass(
        f"/code-review {cfg.level} {pr.num} --comment", "inline",
        cfg.inline_model, cfg.inline_effort, pr.num, cfg.dry_run, log,
        workspace=cfg.workspace, heartbeat_s=cfg.heartbeat_s,
        verbose=cfg.verbose, runner=runner)
    if why == "quota":
        # Dire « plus tard », et le dire dans le code de sortie. La phrase
        # part dans le `Result` plutot que dans le journal : le point
        # d'entree la dit une fois, au niveau que le statut merite.
        return Result.quota(f"the inline pass of PR #{pr.num} ran out of"
                            f" subscription quota — re-run once the window"
                            f" resets: scripts/pr-review {pr.num} --force")
    if got is None:
        log.warn("  inline pass produced no review — continuing without it")
        return Result.of("(the inline pass did not run; no findings were"
                         " posted)")
    return Result.of(got)


async def brief(cfg: ReviewConfig, pr: Pr, found: str, log: Logbook,
                runner: AgentRunner | None) -> Result[str]:
    """La passe 2 : les notes de synthese, qui deviennent le commentaire."""
    log(f"pass 2/2 — reviewer's brief  ({cfg.brief_model},"
        f" effort {cfg.brief_effort})")
    prompt = prompts.fill(BRIEF_PROMPT, num=pr.num, title=pr.title,
                          head=pr.head, base=pr.base, findings=found)
    got, why = await run_pass(prompt, "brief", cfg.brief_model,
                              cfg.brief_effort, pr.num, cfg.dry_run, log,
                              workspace=cfg.workspace,
                              heartbeat_s=cfg.heartbeat_s,
                              verbose=cfg.verbose, runner=runner)
    if cfg.dry_run:
        return Result.of("")
    if got is None:
        said = (f"the brief pass of PR #{pr.num} produced no review, so"
                f" nothing was posted — re-run once you have capacity:"
                f" scripts/pr-review {pr.num} --force")
        return Result.quota(said) if why == "quota" else Result.fail(said)
    return Result.of(got)
