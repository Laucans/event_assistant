"""Le pattern Result : ce qu'une operation rend au lieu de lever.

Les arrets ne sont plus des exceptions. Une porte de preflight, une lecture
d'API qui n'aboutit pas, un stage qui repond `AGENT_LOOP_STOP` : chacun rend
un `Result` en echec, que son appelant propage. Le chemin d'arret est donc
visible dans les signatures au lieu de traverser silencieusement dix cadres
de pile.

**Ce que le statut porte n'a pas change** : les memes codes de sortie, les
memes prefixes de journal, les memes niveaux qu'avant. Un ordonnanceur
exterieur lit ces codes, et ils sont documentes dans `--help` — les deplacer
aurait ete un changement de contrat deguise en refactoring.

Quatre facons de ne pas aboutir, et l'ecart entre elles est ce qui dit quoi
faire ensuite :

- **halted** — l'arret volontaire. Un resultat correct : la boucle a refuse
  de deviner, un humain doit regarder ;
- **unreadable** — un magasin (GitHub, le point de reprise) n'a pas repondu.
  Un arret volontaire aussi, nomme a part parce que lire « illisible » comme
  « rien a faire » est ce qui ferait payer un `/planner` pour un jeton
  expire ;
- **failed** — un stage n'a rien rendu d'utilisable. Pas un resultat correct ;
- **quota** — la fenetre d'abonnement est epuisee. Ni « repare » ni
  « abandonne » : relancer le meme travail plus tard, inchange.

Metier pur : aucun I/O, aucune dependance hors des codes de sortie. C'est ce
qui permet d'en exercer toute la logique en lui passant des chaines.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from pipeline.domain.outcomes.exit_codes import (
    EXIT_HALT, EXIT_OK, EXIT_QUOTA, EXIT_STAGE_FAILED)


class Status(Enum):
    """Comment une operation s'est terminee."""

    OK = "ok"
    HALTED = "halted"
    UNREADABLE = "unreadable"
    FAILED = "failed"
    QUOTA = "quota"


# Ce que chaque statut vaut dehors : le code de sortie qu'un ordonnanceur lit,
# le prefixe qu'un humain voit dans le journal, et le niveau auquel la ligne
# est dite. Un arret volontaire est un resultat correct : il ne se lit pas
# comme un avertissement, et une panne de stage n'est pas un arret.
SAYS: dict[Status, tuple[int, str, str]] = {
    Status.OK:         (EXIT_OK, "OK", "info"),
    Status.HALTED:     (EXIT_HALT, "STOP", "info"),
    Status.UNREADABLE: (EXIT_HALT, "STOP", "info"),
    Status.FAILED:     (EXIT_STAGE_FAILED, "FAILED", "error"),
    Status.QUOTA:      (EXIT_QUOTA, "QUOTA", "warn"),
}


@dataclass(frozen=True)
class Result[T]:
    """Ce qu'une operation rend : une valeur, ou la raison de son absence.

    Frozen a dessein : un resultat qu'un appelant intermediaire pourrait
    requalifier en passant serait exactement l'arret silencieux que ce pattern
    existe pour rendre impossible.
    """

    value: T | None = None
    status: Status = Status.OK
    reason: str = ""

    # --- les fabriques : un verbe, un statut -------------------------------

    @classmethod
    def of(cls, value: T | None = None) -> "Result[T]":
        """Ce qui a abouti, et ce que ca rend."""
        return cls(value=value)

    @classmethod
    def halt(cls, reason: str) -> "Result[T]":
        """L'arret volontaire : la boucle refuse de deviner."""
        return cls(status=Status.HALTED, reason=reason)

    @classmethod
    def unreadable(cls, reason: str) -> "Result[T]":
        """Un magasin n'a pas repondu — ne jamais lire ca comme « rien »."""
        return cls(status=Status.UNREADABLE, reason=reason)

    @classmethod
    def fail(cls, reason: str) -> "Result[T]":
        """Un stage n'a rien rendu d'utilisable."""
        return cls(status=Status.FAILED, reason=reason)

    @classmethod
    def quota(cls, reason: str) -> "Result[T]":
        """La fenetre d'abonnement est epuisee — revenir plus tard."""
        return cls(status=Status.QUOTA, reason=reason)

    # --- ce qu'on lui demande ---------------------------------------------

    @property
    def ok(self) -> bool:
        return self.status is Status.OK

    @property
    def failed(self) -> bool:
        return self.status is not Status.OK

    @property
    def exit_code(self) -> int:
        return SAYS[self.status][0]

    @property
    def prefix(self) -> str:
        """`STOP`, `FAILED`, `QUOTA` — comment la ligne s'annonce."""
        return SAYS[self.status][1]

    @property
    def level(self) -> str:
        """Le niveau de journal que ce statut merite."""
        return SAYS[self.status][2]

    def __str__(self) -> str:
        return self.reason

    # --- la propagation ----------------------------------------------------

    def recast[U](self) -> "Result[U]":
        """Le meme echec, porte par un resultat d'un autre type.

        C'est la propagation, ecrite une fois : un appelant qui recoit un
        echec dont il ne sait rien faire le rend tel quel, et seule la valeur
        qu'il aurait portee change de type. Lever sur un `Result` qui a abouti
        serait une propagation d'un succes — donc un bug muet.
        """
        if self.ok:
            raise ValueError("recast() ne propage qu'un echec")
        return Result(status=self.status, reason=self.reason)

    def map[U](self, fn) -> "Result[U]":
        """Applique `fn` a la valeur si elle existe, propage l'echec sinon.

        Ce qui garde les adaptateurs aussi courts qu'avant : une methode qui
        lisait puis transformait s'ecrit toujours en une ligne, sans que la
        transformation ait a se demander si la lecture a abouti.
        """
        if self.failed:
            return self.recast()
        return Result.of(fn(self.value))

    def but(self, reason: str) -> "Result[T]":
        """Le meme echec, dit autrement — pour ajouter ce que l'appelant sait.

        La raison d'origine est gardee derriere la nouvelle : ce qui a casse
        en bas, et ce que ca empechait en haut, sont deux moities de la meme
        phrase et une autopsie a besoin des deux.
        """
        if self.ok:
            raise ValueError("but() ne requalifie qu'un echec")
        return replace(self, reason=f"{reason} ({self.reason})")
