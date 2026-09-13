"""Une sequence d'etapes, et ce qui l'arrete.

Ce que le round etait avant : un graphe, avec un moteur pour l'executer. Il
n'avait jamais qu'une branche, et le moteur se payait en trois endroits — un
`if self.state.stopped: return` en tete de **chaque** noeud, parce qu'il
declenche le suivant quelle que soit la valeur de retour ; six membres de
l'etat qui n'existaient que pour porter cet arret ; et 1,6 s d'import que
tout le reste du paquet devait ensuite eviter.

Une boucle qui rend au premier echec n'a besoin d'aucun des trois. Ce module
est cette boucle, et il tient en une trentaine de lignes.

**Les trois moments** qu'une etape peut avoir, et ce que chacun repond :

- `skip` — « c'est deja fait » : rend la ligne a journaliser, ou la chaine
  vide pour continuer. Un echec ici arrete, parce que « je ne sais pas si
  c'est deja fait » et « ce n'est pas fait » valent une session d'ecart ;
- `before` — « ce que j'exige pour partir » ;
- `after` — « ce que je dois avoir obtenu ».

Generique par construction : ce module ne sait pas ce qu'est un stage. Il
recoit les etapes, le contexte que les gardes lisent, et la fonction qui fait
tourner une etape. C'est `execution`, donc il ne connait aucun workflow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol

from pipeline.core.domain.outcomes.result import Result


class Step(Protocol):
    """Ce qu'une sequence demande a une etape : un nom, et ses trois gardes.

    `StageSpec` le satisfait. Un `Protocol` plutot que l'import, pour que
    cette couche n'ait pas a savoir qu'une etape est un stage paye.
    """

    skill: str
    skip: Callable | None
    before: Callable | None
    after: Callable | None


async def run_sequence(steps: Iterable[Step], *, ctx, state,
                       run: Callable[[Step], Awaitable[Result]],
                       log: Callable[[str], None],
                       excluded: Callable[[Step], bool] | None = None,
                       save: Callable[[], None] | None = None
                       ) -> Result[None]:
    """Les etapes, dans l'ordre, jusqu'a la premiere qui echoue.

    L'ordre des etapes **est** l'ordre d'execution : il n'y a pas d'autre
    endroit ou le lire, et en reordonner la table reordonne la sequence.
    C'est ce que le graphe ne permettait pas — la sequence y vivait dans les
    decorateurs, et l'ordre de la table n'alimentait qu'un affichage.

    `excluded` dit qu'une etape n'est pas de ce run du tout (`--stages`) :
    elle est sautee **avec ses gardes**, parce qu'une garde de sortie n'a
    rien a verifier d'une session qui n'a pas tourne.

    `save` est appele apres chaque etape terminee, gardes comprises : c'est
    ce qui rend la sequence reprenable, et le point exact ou l'etat vaut la
    peine d'etre ecrit — une etape est atomique, une demi-etape ne se reprend
    pas.
    """
    for step in steps:
        if excluded is not None and excluded(step):
            continue
        if step.skip is not None:
            skip = step.skip(ctx, state)
            if skip.failed:
                return skip.recast()
            if skip.value:
                log(skip.value)
                continue
        if step.before is not None:
            before = step.before(ctx, state)
            if before.failed:
                return before
        ran = await run(step)
        if ran.failed:
            return ran
        if step.after is not None:
            after = step.after(ctx, state)
            if after.failed:
                return after
        if save is not None:
            save()
    return Result.of(None)
