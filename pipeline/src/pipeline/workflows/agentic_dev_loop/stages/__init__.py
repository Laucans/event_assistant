"""Le round : la sequence, et tout ce qu'on sait de chaque etape.

**La surface de design du workflow, et la seule.** L'ordre des entrees *est*
l'ordre d'execution — `run_sequence` parcourt cette table, donc en reordonner
deux lignes reordonne le round. Ajouter une entree ajoute une etape, en
retirer une la retire.

Ca n'a pas toujours ete vrai. La sequence a vecu dans les decorateurs
`@listen` d'un graphe, et cette table n'etait qu'un annuaire de reglages
indexe par nom de skill : on pouvait l'inverser entierement sans que le round
change d'un iota, et le test qui verifiait l'ordre d'execution passait quand
meme. Une entree porte maintenant les quatre choses qu'on veut savoir d'une
etape sans ouvrir un autre fichier — **qui la fait tourner** (modele, effort),
**ce qu'elle dit** (les consignes), **ce qui la fait sauter**, et **ce qu'elle
exige et doit obtenir**.

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

from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.internals import gates
from pipeline.workflows.agentic_dev_loop.stages.business_analyst import (
    BUSINESS_ANALYST)
from pipeline.workflows.agentic_dev_loop.stages.code import CODE
from pipeline.workflows.agentic_dev_loop.stages.planner import PLANNER


# Ce que le preambule cite comme ayant injecte le prompt. Ici et pas dans
# `domain/prompts` : c'est le point d'entree de CE workflow, et un stage qui
# lit ce nom doit pouvoir aller voir le fichier.
INJECTOR = "pipeline/launcher/cli/agentic_dev_loop.py"


PIPELINE: tuple[StageSpec, ...] = (
    StageSpec(
        "business-analyst", "opus", "high",
        instructions=BUSINESS_ANALYST,
        # Deja ecrit : un run interrompu reprend apres, il ne repaie pas une
        # seconde redaction par-dessus la premiere.
        skip=gates.spec_already_written,
        # Le corps de l'issue *est* le SPEC. Relu, pas suppose.
        after=gates.spec_is_in_the_issue,
    ),
    StageSpec(
        "code", "opus", "high", lead="/tech-analyst",
        instructions=CODE,
        skip=gates.code_already_delivered,
        before=gates.code_has_a_spec,
    ),
    # /create-test n'a ni consignes propres ni gardes : il travaille contre un
    # spec deja ecrit, le preambule et la portee lui suffisent, et rien de ce
    # qu'il produit ne conditionne la suite — c'est la derniere etape.
    StageSpec("create-test", "sonnet", "high"),
)

# La post-condition du round, apres la sequence : la task est livree. Pas une
# etape — elle ne paie aucune session — et pas non plus la post-condition du
# *workflow*, qui est vide parce que ce que la boucle garantit se garantit par
# round. C'est ce que `postconditions.py` dit en toutes lettres.
DELIVERED = gates.task_is_delivered

# L'entree que le rollover ferait tourner, prete mais pas branchee. Elle n'est
# pas dans la sequence : le rollover est une branche, pas une etape de plus —
# il part quand il n'y a **aucune** task, donc quand la sequence n'a rien a
# faire.
PLANNER_STAGE = StageSpec("planner", "opus", "high", instructions=PLANNER,
                          after=gates.planner_opened_a_task)

# `planner` ne tourne pas dans la sequence par task : il partirait une fois
# le milestone sans aucune issue `pipeline:agent` ouverte, pour ouvrir l'item
# de roadmap suivant. Laisse a None, la boucle s'arrete la — c'est le defaut,
# et c'est ce que faisait le shell, dont le tableau ne nommait pas planner non
# plus. Enchainer en non surveille depense un run opus/high et engage le
# projet sur un item de roadmap que personne n'a lu : c'est un choix, pas un
# defaut. Pour l'activer :
#     ROLLOVER = PLANNER_STAGE
ROLLOVER: StageSpec | None = None
