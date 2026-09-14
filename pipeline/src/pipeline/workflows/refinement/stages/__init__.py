"""Le raffinage : la sequence, et le texte de chaque etape.

**La surface de design du workflow, et la seule.** L'ordre des entrees *est*
l'ordre d'execution : le routeur, les cinq sections dans l'ordre canonique du
corps, puis la publication — qui est une etape de la table sans etre une
session.

Une fonction de la config et non une table constante, comme la revue : chaque
section a son modele, et les six sont reglables a l'appel.
"""

from __future__ import annotations

from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.common import stages as common
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
    """La carte, le routeur, les cinq sections, la publication — dans l'ordre.

    Les deux entrees de tete etablissent ce que les six suivantes lisent :
    une lecture gratuite du depot, puis la session qui la condense. Elles sont
    **dans la table** parce que la table est la sequence — et parce que leur
    sortie voyage par `ctx.results`, comme celle du routeur.
    """
    table: list = [
        *common.entries(cfg),
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


def prompt_of(step, ctx, state) -> str:
    """Le texte de cette etape.

    L'exploration a le sien : elle ne travaille pas une section du corps, elle
    etablit ce que les six suivantes liront. `ground` ne passe pas par ici —
    c'est une etape locale, et une etape locale n'a pas de prompt.

    La carte prefixe le texte de chaque section, elle n'est **pas** un champ
    substitue dans le template : un `{repo_context}` que six templates
    portaient chacun se serait tu en silence si l'un l'avait perdu, la ou un
    prefixe ne peut pas manquer. C'est aussi la forme qu'a deja
    `prompts.build` pour le bloc EXECUTION CONTEXT de la boucle — la carte est
    ce meme genre de bloc, pas un ingredient d'un prompt de section. Et en
    tete, identique dans les six : c'est ce qui donne aux six sessions un
    prefixe de cache commun, que le placer par template aurait casse.
    """
    if step.skill == common.SKILL:
        return common.prompt(ctx, state)
    cfg, issue = ctx.cfg, state.issue
    template = (ROUTER_PROMPT if step.skill == ROUTER
                else PROMPTS[step.skill])
    said = prompts.fill(
        template,
        num=str(cfg.issue),
        round=str(state.round_no),
        keys="\n".join(sections.KEYS))
    # Le titre vient de l'issue lui aussi : il entre avec les autres. Pas la
    # carte du depot : elle cite des fichiers du depot, donc elle porte les
    # `{body}` et `{num}` des templates qu'elle a lus, et une substitution
    # l'y ferait rentrer — elle prefixe apres coup, en dehors de la passe.
    said = prompts.splice(
        said,
        title=issue.title if issue is not None else "",
        additional_context=additional_context(cfg.context),
        body=((issue.body.strip() if issue is not None else "")
              or prompts.EMPTY_BODY))
    return common.repo_context(ctx) + "\n\n" + said
