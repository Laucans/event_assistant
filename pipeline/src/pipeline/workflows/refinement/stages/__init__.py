"""Le raffinage : la sequence, et le texte de chaque etape.

**La surface de design du workflow, et la seule.** L'ordre des entrees *est*
l'ordre d'execution : le routeur, les cinq sections dans l'ordre canonique du
corps, puis la publication — qui est une etape de la table sans etre une
session.

Une fonction de la config et non une table constante, comme la revue : chaque
section a son modele, et les six sont reglables a l'appel.
"""

from __future__ import annotations

import re

from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.refinement.internals import gates, publish, sections
from pipeline.workflows.refinement.stages.acceptance_criteria import (
    ACCEPTANCE_CRITERIA_PROMPT)
from pipeline.workflows.refinement.stages.business_goal import (
    BUSINESS_GOAL_PROMPT)
from pipeline.workflows.refinement.stages.business_rules import (
    BUSINESS_RULES_PROMPT)
from pipeline.workflows.refinement.stages.router import ROUTER_PROMPT
from pipeline.workflows.refinement.stages.technical import TECHNICAL_PROMPT
from pipeline.workflows.refinement.stages.technical_plan import (
    TECHNICAL_PLAN_PROMPT)

__all__ = ["ACCEPTANCE_CRITERIA_PROMPT", "BUSINESS_GOAL_PROMPT",
           "BUSINESS_RULES_PROMPT", "PROMPTS", "ROUTER", "ROUTER_PROMPT",
           "TECHNICAL_PLAN_PROMPT", "TECHNICAL_PROMPT",
           "additional_context", "passes", "prompt_of"]

ROUTER = gates.ROUTER
PUBLISH = "publish"

# Le prompt de chaque section, par cle de stage.
PROMPTS: dict[str, str] = {
    "business-goal": BUSINESS_GOAL_PROMPT,
    "technical": TECHNICAL_PROMPT,
    "acceptance-criteria": ACCEPTANCE_CRITERIA_PROMPT,
    "business-rules": BUSINESS_RULES_PROMPT,
    "technical-plan": TECHNICAL_PLAN_PROMPT,
}

# Le modele et l'effort de chaque section, par cle : les noms des champs que
# la config porte. Une paire par section, lue par `passes`.
KNOBS: dict[str, tuple[str, str]] = {
    "business-goal": ("goal_model", "goal_effort"),
    "technical": ("technical_model", "technical_effort"),
    "acceptance-criteria": ("criteria_model", "criteria_effort"),
    "business-rules": ("rules_model", "rules_effort"),
    "technical-plan": ("plan_model", "plan_effort"),
}


def passes(cfg) -> tuple:
    """Le routeur, les cinq sections, puis la publication — dans l'ordre."""
    table: list = [
        StageSpec(ROUTER, cfg.router_model, cfg.router_effort,
                  skip=gates.router_is_off,
                  after=gates.router_named_sections),
    ]
    for key in sections.KEYS:
        model, effort = KNOBS[key]
        table.append(StageSpec(key, getattr(cfg, model), getattr(cfg, effort),
                               skip=gates.section_is_wanted(key)))
    table.append(Action(PUBLISH, publish.write, skip=gates.nothing_is_written))
    return tuple(table)


def additional_context(text: str) -> str:
    """Ce que l'humain a demande pour ce round, verbatim.

    Vide quand il n'a rien dit.
    """
    if not text:
        return ""
    return ("--- additional_context ---\n"
            "What the human asked for in this round, verbatim:\n"
            f"{text}\n"
            "--- end additional_context ---")


def splice(template: str, **untrusted: str) -> str:
    """Substitue ces champs en une seule passe.

    `prompts.fill` remplace l'un apres l'autre : un `{body}` ecrit dans le
    `--context` d'un humain, ou un `{additional_context}` present dans le
    corps de l'issue, se ferait remplacer par la passe suivante. Ces deux
    valeurs-la ne viennent pas de nous, donc elles entrent ensemble.
    """
    pattern = re.compile("|".join(rf"\{{{name}\}}" for name in untrusted))
    return pattern.sub(lambda m: untrusted[m.group(0)[1:-1]], template)


def prompt_of(step, ctx, state) -> str:
    """Le texte de cette etape."""
    cfg, issue = ctx.cfg, state.issue
    template = (ROUTER_PROMPT if step.skill == ROUTER
                else PROMPTS[step.skill])
    said = prompts.fill(
        template,
        num=str(cfg.issue),
        round=str(state.round_no),
        keys="\n".join(sections.KEYS))
    # Le titre vient de l'issue lui aussi : il entre avec les deux autres.
    return splice(
        said,
        title=issue.title if issue is not None else "",
        additional_context=additional_context(cfg.context),
        body=((issue.body.strip() if issue is not None else "")
              or prompts.EMPTY_BODY))
