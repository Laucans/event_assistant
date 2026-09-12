"""Ce qu'un workflow est, et la sequence que tous suivent.

Un `Protocol` plutot qu'une classe de base : un workflow n'herite de rien, il
expose ce qui est decrit ici. C'est le duck typing de Python, avec un nom.

Mais un `Protocol` seul n'impose aucune sequence — il decrit une forme. Ce qui
tient la sequence est `sequence()` ci-dessous : les quatre lignes qu'aucun
workflow ne reecrit. Chacun implemente `run()` en delegant, et l'oubli qu'on
veut rendre impossible — livrer un workflow dont les postconditions ne sont
jamais verifiees — demande alors d'ecrire explicitement le contraire.

**Preconditions et postconditions sont communes a tous**, meme vides. Un
workflow qui n'a rien a verifier apres coup le dit en rendant un
`WorkflowOutcome` inchange, ce qui se lit — et se relit, la premiere fois
qu'il aura quelque chose a y mettre.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline.core.domain.outcomes.result import Result
from pipeline.core.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common.contract.outcome import WorkflowOutcome
from pipeline.workflows.common.contract.settings import WorkflowConfig


@runtime_checkable
class Preconditions(Protocol):
    """Ce qui doit tenir avant qu'un workflow depense quoi que ce soit."""

    def verify(self) -> Result[None]:
        """Rend le premier echec rencontre, ou un succes."""
        ...


@runtime_checkable
class Postconditions(Protocol):
    """Ce qu'un workflow doit avoir obtenu pour qu'on le dise termine."""

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        """Rend le premier echec rencontre, ou un succes."""
        ...


@runtime_checkable
class Workflow(Protocol):
    """Ce que le lanceur appelle, quel que soit le workflow derriere.

    Quatre attributs et deux methodes : c'est tout le contrat. `run()` est la
    porte d'entree — toujours la meme sequence, obtenue en deleguant a
    `sequence()`.
    """

    config: WorkflowConfig
    log: Logbook
    preconditions: Preconditions
    postconditions: Postconditions

    async def run(self) -> WorkflowOutcome:
        """Le workflow entier. Delegue a `sequence(self)`."""
        ...

    async def execute(self) -> WorkflowOutcome:
        """Le travail propre a ce workflow, entre les deux gardes."""
        ...


async def sequence(workflow: Workflow) -> WorkflowOutcome:
    """La sequence que tout workflow suit : garder, faire, verifier.

    Ecrite une fois, ici. Les trois etapes rendent un `Result` plutot que de
    lever : le chemin d'arret est donc visible dans ces quinze lignes au lieu
    de traverser silencieusement la pile — et un workflow qui s'arrete tot ne
    paie pas ce qui suit.

    Les postconditions ne sont pas verifiees apres un echec : elles disent ce
    qu'un travail **fait** doit avoir obtenu, et les faire tourner sur un
    workflow qui s'est arrete en chemin ne pourrait produire qu'un second
    message, moins juste que le premier.
    """
    before = workflow.preconditions.verify()
    if before.failed:
        return WorkflowOutcome.of_result(before)

    outcome = await workflow.execute()
    if outcome.failed:
        return outcome

    after = workflow.postconditions.verify(outcome)
    if after.failed:
        return WorkflowOutcome.of_result(after)
    return outcome


class NoPreconditions:
    """Rien a verifier avant. Le dire est ce qui le rend relisible."""

    def verify(self) -> Result[None]:
        return Result.of(None)


class NoPostconditions:
    """Rien a verifier apres. Idem."""

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        return Result.of(None)
