"""La table du round : un stage par entree, avec son modele et son texte.

**La surface de design du workflow.** Ajouter une entree met un skill dans le
round, en retirer une l'en sort. C'est le fichier qu'on ouvre pour changer ce
que la boucle fait — comme l'etait le tableau PIPELINE du shell.

Ici et pas dans `domain/` : `domain/stage_spec.py` dit ce qu'un stage *est*,
ce dossier dit quels stages *ce workflow-ci* fait tourner. Le vocabulaire est
partage, la definition ne l'est pas — un second workflow ecrit la sienne a
cote, sans rien toucher au domaine.

Les modeles sont repartis selon l'endroit ou une mauvaise reponse se paie
deux fois. /business-analyst ecrit le SPEC — le corps de l'issue — que tous
les stages suivants lisent, et le stage `code` planifie puis ecrit le
changement lui-meme : une erreur la revient en retravail. /create-test ecrit
du Vitest hermetique contre un spec qui existe deja : ce n'est pas un
probleme de raisonnement. Se reregler sur .llocal/agent-loop/costs.tsv, pas
sur l'intuition.

Il n'y a plus de stage d'archivage. Une task se fermait autrefois en
deplacant deux fichiers et en cochant une case ; elle se ferme maintenant
parce que la PR de /code a merge avec `Closes #N`. Un stage paye pour
deplacer des fichiers qui n'existent plus n'avait plus rien a faire dans la
table.

Metier pur : ce module ne lit ni l'environnement, ni le disque, ni git.
"""

from __future__ import annotations

from pipeline.domain.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.stages.business_analyst import (
    BUSINESS_ANALYST)
from pipeline.workflows.agentic_dev_loop.stages.code import CODE
from pipeline.workflows.agentic_dev_loop.stages.planner import PLANNER


# Ce que le preambule cite comme ayant injecte le prompt. Ici et pas dans
# `domain/prompts` : c'est le point d'entree de CE workflow, et un stage qui
# lit ce nom doit pouvoir aller voir le fichier.
INJECTOR = "pipeline/launcher/cli/agentic_dev_loop.py"


PIPELINE: tuple[StageSpec, ...] = (
    StageSpec("business-analyst", "opus", "high",
              instructions=BUSINESS_ANALYST),
    StageSpec("code", "opus", "high", lead="/tech-analyst",
              instructions=CODE),
    # /create-test n'a pas de consignes propres : il travaille contre un spec
    # deja ecrit, et le preambule plus la portee lui suffisent.
    StageSpec("create-test", "sonnet", "high"),
)

# L'entree que le rollover ferait tourner, prete mais pas branchee.
PLANNER_STAGE = StageSpec("planner", "opus", "high", instructions=PLANNER)

# `planner` ne tourne pas dans la sequence par task : il partirait une fois
# le milestone sans aucune issue `pipeline:agent` ouverte, pour ouvrir l'item
# de roadmap suivant. Laisse a None, la boucle s'arrete la — c'est le defaut,
# et c'est ce que faisait le shell, dont le tableau ne nommait pas planner non
# plus. Enchainer en non surveille depense un run opus/high et engage le
# projet sur un item de roadmap que personne n'a lu : c'est un choix, pas un
# defaut. Pour l'activer :
#     ROLLOVER = PLANNER_STAGE
ROLLOVER: StageSpec | None = None
