"""Faire tourner un stage : une session d'agent, un resultat, une ligne de cout.

Ce module est de l'orchestration, pas du metier : il compose le prompt,
choisit les fichiers ou tomberont la trace et l'enveloppe, appelle le moteur
d'agent, ecrit la ligne de registre, et traduit ce qui est revenu en la bonne
facon de s'arreter. Le metier qu'il assemble vit ailleurs — la table dans
`domain.stage_spec`, le texte dans `domain.prompts`, la forme du resultat et les
marqueurs dans `domain.outcomes.results`.

Il ne connait aucun fournisseur : il parle a `AgentRunner`, et lequel se
branche derriere est la decision de `adapters.agent.default_runner`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.adapters.agent import AgentRunner, default_runner
from pipeline.adapters.agent import progress
from pipeline.adapters.store import envelope
from pipeline.adapters.store import ledger
from pipeline.domain.outcomes.result import Result
from pipeline.domain.outcomes.stage_result import StageResult, read_markers
from pipeline.domain.stage_spec import StageSpec
from pipeline.execution.context import StagePolicy
from pipeline.runtime.monitoring import metrics
from pipeline.runtime.monitoring.logbook import Logbook

# Ce qu'un stage garde sur disque : tout ce qu'une autopsie de ce stage peut
# demander. Ce sont des noms de champs du fournisseur, lus dans `result.raw` —
# un moteur qui n'en connaitrait pas certains les laisse a `null`.
ENVELOPE = ("subtype", "is_error", "duration_ms", "num_turns", "session_id",
            "total_cost_usd", "usage", "api_error_status", "stop_reason",
            "terminal_reason", "errors", "result")


@dataclass(frozen=True)
class Artifacts:
    """Les trois fichiers qu'un stage laisse derriere lui."""

    log: Path
    envelope: Path
    trace: Path

    @classmethod
    def of(cls, log_dir: Path, round_no: int, skill: str) -> "Artifacts":
        # Le numero de round, zero-padde, nomme les artefacts de ce stage — la
        # meme valeur que le registre ecrit dans sa colonne `round`.
        tag = f"{round_no:02d}"
        return cls(log_dir / f"{tag}-{skill}.log",
                   log_dir / f"{tag}-{skill}.json",
                   log_dir / f"{tag}-{skill}.trace.log")


def failure_of(reason: str | None, skill: str, subtype: str,
               where: str) -> Result[StageResult] | None:
    """La panne que vaut cette raison de n'avoir rien rendu, ou None.

    `where` nomme l'enveloppe et la session : l'identifiant de session est la
    seule cle qui rouvre exactement la session en panne, il voyage donc avec
    chaque raison — il atteignait le registre et l'enveloppe, jamais le
    journal.
    """
    if reason == "quota":
        return Result.quota(f"quota reached during /{skill} — come back"
                            f" later ({where})")
    if reason == "failed":
        return Result.fail(f"/{skill} failed ({subtype}) — {where}")
    if reason == "empty":
        return Result.fail(f"/{skill} returned an empty result — {where}")
    return None


def _keep(files: Artifacts, result, cfg: StagePolicy, *, round_no: int,
          task: str, stage: StageSpec, reason: str | None) -> None:
    """Ce que le stage laisse sur disque : l'enveloppe, sa reponse, sa ligne.

    Ecrit avant qu'aucune panne ne soit levee : un stage mort est justement
    celui dont on veut les traces.
    """
    envelope.write(files.envelope, result.raw, ENVELOPE)
    files.log.write_text(result.text + "\n", encoding="utf-8")
    ledger.append(
        cfg.workspace.ledger, run_id=cfg.run_id, round_no=round_no, task=task,
        stage=stage.skill,
        cache_read=result.usage.get("cache_read_input_tokens"),
        cache_write=result.usage.get("cache_creation_input_tokens"),
        outcome=reason or "ok",
        **result.ledger_fields(model=stage.model, effort=stage.effort))


def _marker_lines(log: Logbook, skill: str, text: str) -> tuple[str | None, str | None]:
    """Lit les deux marqueurs et dit ce qu'il faut en dire. Rend `(ok, stop)`."""
    ok, stop = read_markers(text)
    if ok:
        log(ok)
    elif not stop:
        log.warn(f"/{skill} produced no AGENT_LOOP_OK marker — relying on"
                 f" the structural checks")
    return ok, stop


def _stage_result(result, ok: str | None, stop: str | None) -> StageResult:
    """Le resultat du fournisseur, dans la forme que le round lit."""
    return StageResult(text=result.text, cost=result.cost_usd or 0.0,
                       session_id=result.session_id, ok_line=ok, stop_line=stop,
                       duration_ms=result.duration_ms or 0.0,
                       turns=result.turns, usage=result.usage)


async def run(stage: StageSpec, cfg: StagePolicy, *, round_no: int, task: str,
              extra: str = "", log_dir: Path, log: Logbook,
              runner: AgentRunner | None = None
              ) -> Result[StageResult | None]:
    """Fait tourner un stage.

    La valeur est `None` en dry-run, ou personne n'est appele — un succes qui
    ne porte rien, pas un echec.
    """
    prompt = cfg.prompt_for(stage, extra)
    files = Artifacts.of(log_dir, round_no, stage.skill)

    if cfg.dry_run:
        files.log.write_text(prompt + "\n", encoding="utf-8")
        log(f"dry-run {stage.label} ({stage.model}, effort {stage.effort}) —"
            f" prompt written to {cfg.workspace.rel(files.log)}")
        return Result.of(None)

    log(f"{stage.label} — {stage.model}, effort {stage.effort} ...")
    watch = progress.Progress(log, trace=files.trace,
                              heartbeat_s=cfg.heartbeat_s, verbose=cfg.verbose)
    result = await (runner or default_runner(cfg.workspace)).run(
        prompt, model=stage.model, effort=stage.effort,
        permission_mode=cfg.permission_mode, progress=watch)
    log(watch.census())
    if watch.trace is not None:
        log.debug(f"trace: {cfg.workspace.rel(files.trace)}")

    if result is None:
        return Result.fail(
            f"/{stage.skill} returned no result — the session stopped before"
            f" answering")

    reason = result.failure
    _keep(files, result, cfg, round_no=round_no, task=task, stage=stage,
          reason=reason)

    where = f"{cfg.workspace.rel(files.envelope)}, session {result.session_id}"
    failure = failure_of(reason, stage.skill, result.subtype, where)
    if failure is not None:
        return failure

    log(metrics.stage_line(stage.skill, result.cost_usd, result.duration_ms,
                           result.turns, result.usage))
    log.debug(f"session {result.session_id} —"
              f" {cfg.workspace.rel(files.envelope)}")
    return Result.of(
        _stage_result(result, *_marker_lines(log, stage.skill, result.text)))
