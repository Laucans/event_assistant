"""Ce qu'est une task pour ce round, et laquelle vient ensuite.

La lecture que **ce workflow** fait d'une `Issue` : ses sept etiquettes, les
questions qu'elles permettent de poser, et les quatre regles qui choisissent
la task suivante. On lui passe des `Issue` deja lues, il rend celle qui peut
tourner — c'est ce qui rend les regles testables sans reseau et sans double.

Ici et pas dans `domain/` : `pipeline:ready` ne veut rien dire pour une issue
en general, seulement pour le round. Le domaine porte la forme d'une issue
(`domain/issues.py`), ce module porte ce que ce workflow-ci en fait.

Des fonctions et non des proprietes, a dessein : elles s'appliquent a
n'importe quelle `Issue`, d'ou qu'elle vienne — y compris a celle que
l'adaptateur vient de lire, qui n'a aucune raison d'avoir ete convertie en
quoi que ce soit d'abord.

Les regles, et ce que chacune empeche :

1. **le milestone en cours** est l'issue `pipeline:milestone` ouverte de plus
   petit numero. Un ordre total, pour qu'un second milestone ouvert par
   megarde ne rende pas le choix dependant de l'ordre de l'API ;
2. **la task suivante** est une issue `pipeline:agent` ouverte, sous-issue de
   ce milestone, portant `pipeline:ready`, et dont **tous** les `blocked_by`
   sont fermes. Un vrai parcours de graphe, pas « l'issue N-1 est-elle
   fermee » : le parallelisme est prevu, et il ne doit pas demander une
   migration de donnees pour arriver ;
3. **une issue `pipeline:human` n'est pas un mecanisme a part.** Elle bloque
   parce qu'elle est dans les `blocked_by`, comme n'importe quelle autre
   dependance — la porte humaine du round a disparu dans cette regle-ci ;
4. **`pipeline:ready` commande tout.** Une task ouverte mais pas prete arrete
   le run ; elle ne le fait surtout pas basculer en rollover, qui depense un
   run opus pour ouvrir un item de roadmap que personne n'a demande.

Metier pur : ni I/O, ni subprocess, ni bibliotheque externe.
"""

from __future__ import annotations

import re

from pipeline.core.domain.issues import Issue

# Les etiquettes qui portent tout le modele. Elles sont creees a la main sur
# le depot, et `workflows.agentic_dev_loop.preconditions` verifie qu'elles
# existent avant de payer quoi que ce soit : une etiquette mal orthographiee
# rend le tableau vide, et un tableau vide se lit comme « plus rien a faire ».
ROADMAP = "pipeline:roadmap"
MILESTONE = "pipeline:milestone"
AGENT = "pipeline:agent"
HUMAN = "pipeline:human"
READY = "pipeline:ready"
SPEC_WRITTEN = "pipeline:spec-written"
# Livree sur la branche d'integration, pas encore fusionnee dans `main`.
# L'issue reste **ouverte** : la fermer dirait que le travail est integre,
# ce qui n'est vrai qu'apres la fusion. Ce troisieme etat est ce qui separe
# « l'agent a fini » de « c'est dans main ».
WAITING_MERGE = "pipeline:waiting-merge"

LABELS = (ROADMAP, MILESTONE, AGENT, HUMAN, READY, SPEC_WRITTEN,
          WAITING_MERGE)


# --- ce qu'une etiquette veut dire pour ce round ---------------------------


def agent(issue: Issue) -> bool:
    return issue.has(AGENT)


def human(issue: Issue) -> bool:
    return issue.has(HUMAN)


def ready(issue: Issue) -> bool:
    return issue.has(READY)


def spec_written(issue: Issue) -> bool:
    return issue.has(SPEC_WRITTEN)


def waiting_merge(issue: Issue) -> bool:
    return issue.has(WAITING_MERGE)


def kind(issue: Issue) -> str:
    return "human" if human(issue) else "auto"


def blockers_pending(issue: Issue) -> tuple[Issue, ...]:
    """Les bloqueurs qui bloquent encore.

    Une task en `waiting-merge` n'en fait pas partie : son code est sur la
    branche d'integration, donc la suivante peut batir dessus. Sans cette
    exception la chaine s'arreterait apres une seule task, et il faudrait une
    fusion dans `main` par round.

    Une action humaine n'a pas cet etat — elle ne se livre pas sur une
    branche, elle se ferme.
    """
    return tuple(b for b in issue.blocked_by
                 if b.open and not waiting_merge(b))


def runnable(issue: Issue) -> bool:
    """Ouverte, prete, pas deja livree, et plus rien qui la bloque.

    `waiting_merge` est ce qui empeche de rejouer une task finie : elle reste
    ouverte jusqu'a la fusion, donc sans ce test le round suivant la
    choisirait et repayerait ses trois stages.
    """
    return (issue.open and agent(issue) and ready(issue)
            and not waiting_merge(issue) and not blockers_pending(issue))


def why_not(issue: Issue) -> str:
    """Pourquoi cette task ne peut pas tourner, dite a un humain.

    Un run qui s'arrete doit nommer le geste qui le debloque. « aucune task
    prete » n'en nomme aucun ; « #12 attend #11 (ouverte) » en nomme un.
    """
    if issue.closed:
        return f"{issue.ref} is closed"
    if waiting_merge(issue):
        return (f"{issue.ref} {issue.title}: delivered on the integration"
                f" branch, waiting for the merge that closes it")
    reasons = []
    if not ready(issue):
        reasons.append(f"no {READY} label")
    for blocker in blockers_pending(issue):
        said = "human action" if human(blocker) else "task"
        reasons.append(f"blocked by {blocker.ref} ({said}, still open)")
    return f"{issue.ref} {issue.title}: " + ", ".join(reasons or ["ready"])


# --- les quatre regles de choix --------------------------------------------


def current_milestone(issues: list[Issue]) -> Issue | None:
    """Regle 1 : le `pipeline:milestone` ouvert de plus petit numero."""
    return min((i for i in issues if i.open and i.has(MILESTONE)),
               key=lambda t: t.number, default=None)


def agent_tasks(issues: list[Issue]) -> list[Issue]:
    """Les sous-issues qui sont des tasks d'agent, dans l'ordre des numeros."""
    return sorted((t for t in issues if agent(t)), key=lambda t: t.number)


def open_agent_tasks(issues: list[Issue]) -> list[Issue]:
    return [t for t in agent_tasks(issues) if t.open]


def next_task(issues: list[Issue]) -> Issue | None:
    """Regle 2 : la plus petite task ouverte, prete et debloquee."""
    return min((t for t in open_agent_tasks(issues) if runnable(t)),
               key=lambda t: t.number, default=None)


def stuck_report(issues: list[Issue]) -> str:
    """Pourquoi aucune task ne peut tourner, task par task.

    Le cas que ce texte existe pour ne pas confondre avec le rollover : il
    reste des tasks ouvertes, donc le milestone n'est pas fini, donc appeler
    `/planner` serait payer un run opus pour ouvrir un milestone de plus.
    """
    lines = [why_not(t) for t in open_agent_tasks(issues)]
    return "\n".join(f"  - {line}" for line in lines)


# --- la preuve qu'une task est livree --------------------------------------

# GitHub ne ferme une issue liee qu'au merge dans la branche **par defaut**
# du depot. La boucle merge dans `INTEGRATION_BRANCH` (`main_agent`), donc le
# `Closes #N` de `/code` pose bien le lien mais ne ferme rien : c'est le
# round qui doit le constater et fermer. Cette regexp est la regle de lecture
# de ce constat.
#
# Elle exige la ligne entiere, alors que GitHub accepte le mot-cle n'importe
# ou dans le corps. C'est volontairement plus strict que GitHub, et dans le
# bon sens : `/code` a pour consigne de la mettre sur sa propre ligne, et
# lire plus large ferait fermer une issue sur une phrase qui la mentionne.
# Rater une fermeture que GitHub aurait faite est sans consequence — l'issue
# est alors deja fermee, et on n'arrive jamais jusqu'ici.
CLOSES = re.compile(r"^[ \t]*(?:closes|fixes|resolves)[ \t]+#(\d+)[ \t]*$",
                    re.IGNORECASE | re.MULTILINE)


def closes(body: str | None, number: int) -> bool:
    """Le corps de PR declare-t-il fermer `#number` ?"""
    return any(int(found) == number for found in CLOSES.findall(body or ""))


def first_closing(prs: list[Issue], number: int) -> Issue | None:
    """La premiere PR de la liste qui declare fermer `#number`.

    Ici et non dans l'adaptateur : `closes` est la convention donnee a
    /code, pas une propriete de l'API GitHub. `adapters.shell.github` rend
    les PR mergees, ce module decide laquelle vaut preuve de livraison.
    """
    return next((pr for pr in prs if closes(pr.body, number)), None)
