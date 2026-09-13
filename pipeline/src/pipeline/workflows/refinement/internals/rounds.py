"""Le compteur de rounds, et ce qu'un round donne ecrit. Metier pur.

Le round courant se lit dans les commentaires de l'issue : le plus grand `N`
deja commente, plus un. Ni fichier d'etat, ni etiquette — le compteur vit ou
l'humain peut le voir et le corriger.
"""

from __future__ import annotations

import re

from pipeline.workflows.refinement.internals import sections

MARKER = "refinement round:"

# Le commentaire de fin de round, seul sur sa ligne. Insensible a la casse :
# c'est un marqueur, pas un mot de passe.
_COUNTER = re.compile(rf"^[ \t]*{re.escape(MARKER)}[ \t]*(\d+)[ \t]*$",
                      re.MULTILINE | re.IGNORECASE)

# Ce qu'un modele peut ecrire pour nommer une section : sa cle, ou son titre.
# Les plus longs d'abord — « Technical » est un prefixe de « Technical
# Implementation Plan », et « technical » de « technical-plan ».
#
# Les formes courtes sont nommees ici : sans « technical plan », un routeur
# qui ecrit ces deux mots fait rouvrir « technical », qui n'est pas la section
# qu'il demandait.
_ALIASES: tuple[tuple[str, str], ...] = (
    ("technical plan", "technical-plan"),
    ("implementation plan", "technical-plan"),
)

_TOKENS: tuple[tuple[str, str], ...] = tuple(sorted(
    (*((token, s.key) for s in sections.SECTIONS
       for token in (s.key, s.heading.casefold())), *_ALIASES),
    key=lambda pair: -len(pair[0])))


def counter(comments: list[str]) -> int:
    """Le plus grand round deja commente, 0 si aucun."""
    seen = [int(n) for body in comments or [] for n in _COUNTER.findall(body)]
    return max(seen, default=0)


def comment(round_no: int) -> str:
    """Le commentaire de fin de round : `refinement round: 3`."""
    return f"{MARKER} {round_no}"


def routed(round_no: int, has_context: bool) -> bool:
    """Ce round passe-t-il par le routeur ?"""
    return round_no >= 3 and has_context


def planned(round_no: int, found: dict[str, str],
            has_context: bool) -> tuple[str, ...]:
    """Les sections que ce round ecrit, hors decision du routeur.

    Round 1 les trois du round 1 ; round 2 les manquantes du round 1 puis les
    deux du round 2 ; round >= 3 les cinq, ou rien quand le routeur decide.
    """
    if round_no <= 1:
        return sections.keys_of_round(1)
    if round_no == 2:
        return sections.missing(found) + sections.keys_of_round(2)
    if routed(round_no, has_context):
        return ()
    return sections.KEYS


def _names(text: str, token: str) -> bool:
    """Ce texte nomme-t-il ce jeton, entier ?"""
    return re.search(rf"(?<![0-9a-z-]){re.escape(token)}(?![0-9a-z-])",
                     text) is not None


def wanted_from(answer: str) -> tuple[str, ...]:
    """Les cles de section que le routeur a nommees, dans l'ordre canonique.

    Vide quand rien n'est reconnu : le gate de sortie du routeur en fait un
    echec plutot qu'un round muet.
    """
    said = (answer or "").casefold()
    named: set[str] = set()
    for token, key in _TOKENS:
        if _names(said, token):
            named.add(key)
            # Consomme, pour qu'un jeton court ne se retrouve pas dans un
            # jeton long deja reconnu.
            said = said.replace(token, " ")
    return tuple(key for key in sections.KEYS if key in named)
