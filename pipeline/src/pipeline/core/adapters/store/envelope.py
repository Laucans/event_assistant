"""L'enveloppe JSON qu'un stage ou une passe laisse a cote de son log.

Ce qu'un post-mortem relit quand le terminal est ferme. Chaque appelant
choisit ses champs : un stage garde tout ce qu'une autopsie peut vouloir, une
passe de revue la poignee qui lui sert a s'expliquer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path


def write(path: Path, raw: dict, fields: Sequence[str]) -> None:
    """Ecrit les champs nommes de `raw` dans `path`, en JSON indente.

    Un champ que le fournisseur ne connait pas sort a `null` plutot que de
    faire echouer l'ecriture : l'enveloppe est une trace, jamais une raison
    d'arreter un run qui marche.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({name: raw.get(name) for name in fields},
                   indent=2, default=str),
        encoding="utf-8")
