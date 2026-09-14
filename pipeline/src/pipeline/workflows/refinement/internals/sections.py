"""Les cinq sections du corps d'une issue raffinee : les lire, les rendre.

Metier pur : ni I/O, ni subprocess, ni reseau. Les titres sont en anglais
parce qu'ils sont ecrits tels quels dans le corps de l'issue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """Une section : la cle de son stage, son titre markdown, son round."""

    key: str
    heading: str
    round: int


# L'ordre canonique : celui dans lequel le corps est reecrit, et celui dans
# lequel les stages tournent.
SECTIONS: tuple[Section, ...] = (
    Section("business-goal", "Business Goal", 1),
    Section("technical", "Technical", 1),
    Section("acceptance-criteria", "Acceptance Criteria", 1),
    Section("business-rules", "Business Rules", 2),
    Section("technical-plan", "Technical Implementation Plan", 2),
)

KEYS: tuple[str, ...] = tuple(s.key for s in SECTIONS)

_BY_KEY = {s.key: s for s in SECTIONS}
_BY_HEADING = {s.heading.casefold(): s for s in SECTIONS}

# Une ligne `## <titre>`. L'espace apres `##` est exige : sans lui, un `###`
# du corps d'une section serait lu comme une frontiere et couperait la
# section en deux.
_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def by_key(key: str) -> Section | None:
    """La section de cette cle, ou None."""
    return _BY_KEY.get(key)


def keys_of_round(round_no: int) -> tuple[str, ...]:
    """Les cles des sections que ce round introduit."""
    return tuple(s.key for s in SECTIONS if s.round == round_no)


def parse(body: str) -> dict[str, str]:
    """Les sections canoniques du corps, par cle.

    Le texte avant le premier `##` et les titres inconnus sont ignores, mais
    un titre inconnu reste une frontiere : il ferme la section precedente.
    """
    found: dict[str, str] = {}
    marks = list(_HEADING.finditer(body or ""))
    for n, mark in enumerate(marks):
        section = _BY_HEADING.get(mark.group(1).strip().casefold())
        if section is None:
            continue
        end = marks[n + 1].start() if n + 1 < len(marks) else len(body)
        text = body[mark.end():end].strip()
        if text:
            found[section.key] = text
    return found


def render(found: dict[str, str]) -> str:
    """Le corps canonique : les sections non vides, dans l'ordre."""
    blocks = [f"## {s.heading}\n\n{found[s.key].strip()}\n"
              for s in SECTIONS if (found.get(s.key) or "").strip()]
    return "\n".join(blocks)


def missing(found: dict[str, str]) -> tuple[str, ...]:
    """Les cles du round 1 absentes du corps, ou vides."""
    return tuple(key for key in keys_of_round(1)
                 if not (found.get(key) or "").strip())


def merge(found: dict[str, str], wanted, results) -> dict[str, str]:
    """Le corps que ce round rendrait : `found`, remplace pour les cles visees.

    Un stage qui n'a rien rendu laisse la section precedente en place plutot
    que de l'effacer — `results` porte ce qu'une reprise ou un dry-run n'a pas
    paye aussi bien que ce qu'une session a rendu vide.
    """
    merged = dict(found)
    for key in wanted:
        got = results.get(key)
        text = (got.text.strip() if got is not None else "")
        if text:
            merged[key] = text
    return merged
