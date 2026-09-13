"""La revue : la sequence, et ce qu'on sait de chaque etape.

**La surface de design du workflow, et la seule.** L'ordre des entrees *est*
l'ordre d'execution. Deux passes payantes, puis la publication — qui est une
etape de la table sans etre une session, parce que la sequence enchaine les
deux sortes.

Une fonction de la config et non une table constante, a la difference du
round : les modeles des deux passes sont reglables a l'appel (`--level`,
`PR_REVIEW_*`) et non fixes par un design. C'est ce qui laissait ce dossier
sans table du tout, et donc la revue sans surface de design lisible.

Les modeles sont repartis selon ce qu'est le travail. /code a deja fait
tourner une revue adverse avant de merger : la passe 1 est un second avis en
contexte neuf, pas la seule ligne de defense. La passe 2 resume ce que la
passe 1 et le diff disent deja — c'est de la redaction, pas une chasse.
"""

from __future__ import annotations

from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.pr_review.internals import gates, publish
from pipeline.workflows.pr_review.stages.brief import BRIEF_PROMPT

__all__ = ["BRIEF_PROMPT", "passes", "prompt_of"]

INLINE = "inline"
BRIEF = "brief"


def passes(cfg) -> tuple:
    """Les deux passes et la publication, dans l'ordre."""
    return (
        StageSpec(INLINE, cfg.inline_model, cfg.inline_effort,
                  skip=gates.inline_pass_is_off),
        StageSpec(BRIEF, cfg.brief_model, cfg.brief_effort),
        Action("publish", publish.post, skip=gates.nothing_is_posted),
    )


def prompt_of(step, ctx, state) -> str:
    """Le texte de cette passe.

    Celui de la passe 2 contient ce que la passe 1 a rendu : c'est le seul
    endroit du paquet ou une etape lit la sortie de la precedente, et elle la
    lit dans `ctx.results`, sous le nom de l'etape qui l'a produite.
    """
    pr = state.pr
    if step.skill == INLINE:
        return f"/code-review {ctx.cfg.level} {pr.num} --comment"
    return prompts.fill(BRIEF_PROMPT, num=pr.num, title=pr.title, head=pr.head,
                        base=pr.base, findings=gates.findings(ctx))
