"""La table du pipeline, typee.

Une entree par stage, dans l'ordre d'execution. Ajouter une entree met un
skill dans le pipeline, en retirer une l'en sort. C'est la surface de design
du runner, comme l'etait le tableau PIPELINE du shell.

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

from pipeline.domain.stages.stage_spec import StageSpec


PIPELINE: tuple[StageSpec, ...] = (
    StageSpec("business-analyst", "opus", "high"),
    StageSpec("code", "opus", "high", lead="/tech-analyst"),
    StageSpec("create-test", "sonnet", "high"),
)

# `planner` ne tourne pas dans la sequence par task : il partirait une fois
# le milestone sans aucune issue `pipeline:agent` ouverte, pour ouvrir l'item
# de roadmap suivant. Laisse
# a None, la boucle s'arrete la — c'est le defaut, et c'est ce que faisait le
# shell, dont le tableau ne nommait pas planner non plus. Enchainer en non
# surveille depense un run opus/high et engage le projet sur un item de
# roadmap que personne n'a lu : c'est un choix, pas un defaut. Pour l'activer :
#     ROLLOVER = StageSpec("planner", "opus", "high")
ROLLOVER: StageSpec | None = None


def spec_of(skill: str, table: tuple[StageSpec, ...]) -> StageSpec | None:
    """L'entree de cette table que porte ce nom, ou None.

    Nommee plutot que supposee : `next()` sans defaut leve un `StopIteration`
    nu, et en lever un dans une methode async le transforme en
    `RuntimeError: coroutine raised StopIteration` — une forme qui ne dit rien
    d'une entree renommee dans la table, seule facon d'y arriver.
    """
    for spec in table:
        if spec.skill == skill:
            return spec
    return None


def names(table: tuple[StageSpec, ...]) -> str:
    """Les entrees de la table, pour un message d'erreur qui aide."""
    return " ".join(s.skill for s in table) or "(nothing)"
