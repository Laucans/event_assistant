"""Ce qui est verifie avant que le premier stage soit paye.

Les portes qui ne sont propres a aucun workflow vivent dans
`common.utils.checks` : `claude` sur le PATH, `gh` authentifie, la branche
d'integration, l'arbre propre. Ce fichier ne garde que ce que **la boucle**
exige — les etiquettes du modele en issues, un milestone atteignable, les
skills que la table nomme — et compose les deux listes dans l'ordre ou elles
se verifient.

Une porte ne leve pas : elle rend un `Result`. `verify()` rend le premier
echec, et la sequence du contrat s'arrete la, avant qu'`execute()` ne depense
quoi que ce soit.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.domain import tasks
from pipeline.domain.outcomes.result import Result
from pipeline.runtime.monitoring.logbook import Logbook
from pipeline.workflows.agentic_dev_loop.internals import board
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.common.utils import checks, hub
from pipeline.workflows.common.utils.checks import Check


# --- ce que la boucle exige, et qu'elle seule exige ------------------------


def pipeline_labels_exist(cfg: RunConfig, log: Logbook) -> Result[None]:
    """The six labels the whole model is expressed in.

    A label that does not exist does not fail anywhere: querying it returns
    an empty list, and an empty list of tasks reads as "this milestone is
    finished" — the one input that makes the loop pay for a `/planner`. A
    typo in a label name is worth catching here, for free.
    """
    known = hub.gh(cfg.workspace).labels()
    if known.failed:
        return known.recast()
    missing = [l for l in tasks.LABELS if l not in known.value]
    if missing:
        return Result.halt(f"the repository is missing the label(s)"
                           f" {' '.join(missing)} — create them with:"
                           + "".join(f" gh label create {l};"
                                     for l in missing))
    return Result.of(None)


def current_milestone_is_reachable(cfg: RunConfig,
                                   log: Logbook) -> Result[None]:
    """There is an open milestone, and GitHub answered when asked.

    `board.read` fails on both counts, with the sentence that names the fix;
    running it here is what keeps those two failures from landing in the
    middle of a round, after a stage has been billed.
    """
    here = board.read(hub.gh(cfg.workspace))
    if here.failed:
        return here.recast()
    log.debug(f"milestone {here.value.milestone.ref}:"
              f" {here.value.milestone.title} —"
              f" {len(here.value.open_agents)} open task(s)")
    return Result.of(None)


def pipeline_skills_exist(cfg: RunConfig, log: Logbook) -> Result[None]:
    """The table names skills: they have to exist.

    `StageSpec`'s constructor already validated the effort at import time, so
    what is left to check is the file behind each name.
    """
    for stage in (*cfg.pipeline, *((cfg.rollover,) if cfg.rollover else ())):
        if not (cfg.workspace.skills / stage.skill / "SKILL.md").exists():
            return Result.halt(
                f"PIPELINE names /{stage.skill} but"
                f" .claude/skills/{stage.skill}/SKILL.md does not exist")
    return Result.of(None)


def lead_skills_exist(cfg: RunConfig, log: Logbook) -> Result[None]:
    """The opening commands (`lead`) are the name of no table entry.

    Which is why the loop above cannot see them missing.
    """
    for stage in cfg.pipeline:
        if stage.lead and cfg.enabled(stage):
            skill = stage.lead.lstrip("/")
            if not (cfg.workspace.skills / skill / "SKILL.md").exists():
                return Result.halt(
                    f"the {stage.skill} stage opens on {stage.lead} but"
                    f" .claude/skills/{skill}/SKILL.md does not exist")
    return Result.of(None)


# What preflight guarantees, in the order it guarantees it. Les trois
# premieres et les quatre de branche sont communes a tout workflow de ce
# paquet ; les quatre du milieu sont celles de la boucle.
CHECKS: tuple[Check, ...] = (
    *checks.TOOLING,
    Check("pipeline-labels", pipeline_labels_exist),
    Check("milestone", current_milestone_is_reachable),
    Check("pipeline-skills", pipeline_skills_exist),
    Check("lead-skills", lead_skills_exist),
    *checks.BRANCH,
    Check("clean-tree", checks.working_tree_is_clean),
)


def _announce(cfg: RunConfig, log: Logbook) -> None:
    """Say what this run is about to do, once every gate has passed."""
    sha = hub.repo(cfg.workspace).head_sha()
    log(f"run {cfg.run_id} — branch {cfg.integration_branch} @ {sha or '?'},"
        f" {cfg.max_rounds} round(s)")
    log(f"pipeline: {cfg.summary()}")
    # A run with `--stages code` used to say nothing about the three stages it
    # dropped, which reads afterwards like a pipeline that lost them.
    left_out = cfg.filtered_out()
    if left_out:
        log(f"filtered out by --stages: {' '.join(left_out)}")
    log(f"permission mode: {cfg.permission_mode} (the PreToolUse hooks in"
        f" .claude/settings.json still apply)")
    if cfg.heartbeat_s > 0:
        log.debug(f"heartbeat every {cfg.heartbeat_s:g}s; per-stage traces"
                  f" alongside run.log")


@dataclass
class LoopPreconditions:
    """Les portes de la boucle, dans la forme que le contrat appelle."""

    cfg: RunConfig
    log: Logbook

    def verify(self) -> Result[None]:
        """Rend la premiere condition qui empeche la boucle de tourner."""
        got = checks.verify_all(CHECKS, self.cfg, self.log)
        if got.failed:
            return got
        _announce(self.cfg, self.log)
        return Result.of(None)
