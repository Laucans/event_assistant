"""Les textes des passes de la revue.

Pas de table ici, a la difference du round : les deux passes de la revue
portent leur modele et leur effort dans `ReviewConfig`, parce qu'ils sont
reglables a l'appel (`--level`, `PR_REVIEW_*_MODEL`) et non fixes par un
design. Ce qui reste propre a la revue et se relit sans rien faire tourner,
c'est la prose — elle est ici.
"""

from pipeline.workflows.pr_review.stages.brief import BRIEF_PROMPT

__all__ = ["BRIEF_PROMPT"]
