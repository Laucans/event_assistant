"""Le tableau : le milestone en cours, ses tasks, et laquelle vient ensuite.

Le cote **lecture** du modele en issues, a un seul endroit. Le round en a
besoin pour choisir, la boucle pour savoir sous quelle cle reprendre, le
preflight pour verifier que le tableau est atteignable, `--status` pour dire
ou on en est. Quatre lecteurs, une seule facon de lire.

Ici et pas dans `adapters/` : composer « le milestone ouvert de plus petit
numero, puis ses sous-issues, puis leurs bloqueurs » est une politique, et
`adapters.shell.github` ne decide de rien. Ici et pas dans `tasks.py`, a
cote : ce module appelle `gh`, et les regles de ce voisin se relisent en leur
passant des issues. La fabrique de l'adaptateur, elle, a quitte ce module pour
`core.adapters.hub` — construire un client n'est la politique de personne, et
`legacy.migrate` importait ce workflow-ci rien que pour l'obtenir.

Rien dans ce module n'importe le moteur de graphe. C'est ce qui laisse
`--status` repondre en quelques dizaines de millisecondes, et le preflight
echouer avant qu'un flow soit construit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.domain.issues import Issue
from pipeline.core.domain.outcomes.result import Result
from pipeline.workflows.agentic_dev_loop.internals import tasks


@dataclass
class Board:
    """Ce que la boucle voit du tableau, a un instant donne.

    Le client est garde a cote de ce qu'il a lu : les stages doivent
    reetiqueter l'issue et relire son corps, et ouvrir une seconde connexion
    pour ca reposerait la question « quel depot, quelles etiquettes » deja
    tranchee ici.
    """

    gh: GitHub
    milestone: Issue
    tasks: list[Issue] = field(default_factory=list)
    # La task que le point de reprise designe, quand la boucle en a trouve
    # une. Elle prime sur le choix du tableau, et c'est ce qui permet de
    # finir un round dont le `/code` a deja merge : l'issue est fermee, donc
    # plus rien ne l'offrirait, et `/create-test` serait perdu.
    resuming: Issue | None = None

    @property
    def open_agents(self) -> list[Issue]:
        """Les tasks d'agent encore ouvertes — ce qui decide du rollover."""
        return tasks.open_agent_tasks(self.tasks)

    @property
    def next(self) -> Issue | None:
        return tasks.next_task(self.tasks)

    def find(self, key: str | int) -> Issue | None:
        """La sous-issue de ce milestone qui porte ce numero, ouverte ou non.

        Fermee comprise, a dessein : un round interrompu apres le merge de
        `/code` doit pouvoir se terminer, et l'issue qu'il finit est deja
        fermee.
        """
        try:
            number = int(key)
        except (TypeError, ValueError):
            return None
        return next((t for t in self.tasks if t.number == number), None)

    def stuck(self) -> str:
        """Le message d'arret quand il reste des tasks mais aucune jouable.

        Ce cas n'est **pas** un rollover, et les confondre coute un run opus :
        le milestone n'est pas fini, il attend un humain. Reste a dire
        **lequel** des gestes il attend, parce qu'ils n'ont rien a voir :
        tout livrer et attendre une fusion n'a pas la meme reponse qu'une
        case `pipeline:ready` que personne n'a cochee.
        """
        head = (f"milestone {self.milestone.ref} has"
                f" {len(self.open_agents)} open task(s) but none can run:\n"
                f"{tasks.stuck_report(self.tasks)}\n")
        if all(tasks.waiting_merge(t) for t in self.open_agents):
            return (head + "Everything is delivered on the integration"
                    " branch and waiting for you to merge it and close"
                    " these issues. Nothing here is the loop's to do.")
        return (head + f"Add {tasks.READY} to the one to work on next, or"
                f" close what blocks it, then re-run.")


def read(gh: GitHub) -> Result[Board]:
    """Le tableau, lu maintenant. En echec s'il n'y a pas de milestone.

    Une lecture qui n'aboutit pas rend un echec depuis l'adaptateur et il est
    propage tel quel : elle ne se rend jamais en tableau vide, qui se lirait
    « milestone termine » et declencherait `/planner`.
    """
    found = gh.issues_labelled(tasks.MILESTONE)
    if found.failed:
        return found.recast()
    milestone = tasks.current_milestone(found.value)
    if milestone is None:
        return Result.halt(
            f"no open {tasks.MILESTONE} issue — there is nothing to work"
            f" from. Open one (or let /planner open one from a"
            f" {tasks.ROADMAP} issue) before running the loop.")
    subs = gh.sub_issues(milestone.number)
    if subs.failed:
        return subs.recast()
    held = gh.with_blockers(subs.value)
    if held.failed:
        return held.recast()
    return Result.of(Board(gh=gh, milestone=milestone, tasks=held.value))
