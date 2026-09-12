"""Ce qu'est une task, et laquelle vient ensuite.

Le suivi des tasks vit dans les issues GitHub, plus dans des fichiers
markdown. Ce module en porte la **forme** et les **regles de choix**, sans
jamais parler a GitHub : on lui passe des `Task` deja lues, il rend celle qui
peut tourner. C'est ce qui rend les quatre regles ci-dessous testables sans
reseau et sans double.

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
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Task:
    """Une issue, vue par la boucle.

    Le meme type sert pour un item de roadmap, un milestone, une task et une
    action humaine : ce qui les distingue est une etiquette, pas une classe.
    C'est ce qui permet a `blocked_by` de porter des issues de n'importe
    quelle sorte — une dependance ne demande pas ce qu'elle bloque.

    `blocked_by` porte les bloqueurs **avec leur etat** : savoir qu'une issue
    est bloquee ne suffit pas, il faut savoir si le bloqueur est encore
    ouvert.
    """

    number: int
    title: str = ""
    state: str = "open"
    labels: tuple[str, ...] = ()
    body: str = ""
    blocked_by: tuple["Task", ...] = ()

    @property
    def key(self) -> str:
        """L'identite de la task pour l'etat de reprise : son numero d'issue.

        C'etait `<num>|<titre>` du temps du markdown, ou rien d'autre ne
        designait une task de facon stable. Un numero d'issue, lui, ne change
        pas quand on reecrit le titre.
        """
        return str(self.number)

    @property
    def ref(self) -> str:
        return f"#{self.number}"

    @property
    def open(self) -> bool:
        return self.state != "closed"

    @property
    def closed(self) -> bool:
        return self.state == "closed"

    def has(self, label: str) -> bool:
        return label in self.labels

    @property
    def agent(self) -> bool:
        return self.has(AGENT)

    @property
    def human(self) -> bool:
        return self.has(HUMAN)

    @property
    def ready(self) -> bool:
        return self.has(READY)

    @property
    def spec_written(self) -> bool:
        return self.has(SPEC_WRITTEN)

    @property
    def kind(self) -> str:
        return "human" if self.human else "auto"

    @property
    def waiting_merge(self) -> bool:
        return self.has(WAITING_MERGE)

    @property
    def blockers_pending(self) -> tuple["Task", ...]:
        """Les bloqueurs qui bloquent encore.

        Une task en `waiting-merge` n'en fait pas partie : son code est sur
        la branche d'integration, donc la suivante peut batir dessus. Sans
        cette exception la chaine s'arreterait apres une seule task, et il
        faudrait une fusion dans `main` par round.

        Une action humaine n'a pas cet etat — elle ne se livre pas sur une
        branche, elle se ferme.
        """
        return tuple(b for b in self.blocked_by
                     if b.open and not b.waiting_merge)

    @property
    def runnable(self) -> bool:
        """Ouverte, prete, pas deja livree, et plus rien qui la bloque.

        `waiting_merge` est ce qui empeche de rejouer une task finie : elle
        reste ouverte jusqu'a la fusion, donc sans ce test le round suivant
        la choisirait et repayerait ses trois stages.
        """
        return (self.open and self.agent and self.ready
                and not self.waiting_merge and not self.blockers_pending)

    def why_not(self) -> str:
        """Pourquoi cette task ne peut pas tourner, dite a un humain.

        Un run qui s'arrete doit nommer le geste qui le debloque. « aucune
        task prete » n'en nomme aucun ; « #12 attend #11 (ouverte) » en nomme
        un.
        """
        if self.closed:
            return f"{self.ref} is closed"
        if self.waiting_merge:
            return (f"{self.ref} {self.title}: delivered on the integration"
                    f" branch, waiting for the merge that closes it")
        reasons = []
        if not self.ready:
            reasons.append(f"no {READY} label")
        for blocker in self.blockers_pending:
            kind = "human action" if blocker.human else "task"
            reasons.append(f"blocked by {blocker.ref} ({kind}, still open)")
        return f"{self.ref} {self.title}: " + ", ".join(reasons or ["ready"])


def current_milestone(issues: list[Task]) -> Task | None:
    """Regle 1 : le `pipeline:milestone` ouvert de plus petit numero."""
    return min((i for i in issues if i.open and i.has(MILESTONE)),
               key=lambda t: t.number, default=None)


def agent_tasks(tasks: list[Task]) -> list[Task]:
    """Les sous-issues qui sont des tasks d'agent, dans l'ordre des numeros."""
    return sorted((t for t in tasks if t.agent), key=lambda t: t.number)


def open_agent_tasks(tasks: list[Task]) -> list[Task]:
    return [t for t in agent_tasks(tasks) if t.open]


def next_task(tasks: list[Task]) -> Task | None:
    """Regle 2 : la plus petite task ouverte, prete et debloquee."""
    return min((t for t in open_agent_tasks(tasks) if t.runnable),
               key=lambda t: t.number, default=None)


def stuck_report(tasks: list[Task]) -> str:
    """Pourquoi aucune task ne peut tourner, task par task.

    Le cas que ce texte existe pour ne pas confondre avec le rollover : il
    reste des tasks ouvertes, donc le milestone n'est pas fini, donc appeler
    `/planner` serait payer un run opus pour ouvrir un milestone de plus.
    """
    lines = [t.why_not() for t in open_agent_tasks(tasks)]
    return "\n".join(f"  - {line}" for line in lines)


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
