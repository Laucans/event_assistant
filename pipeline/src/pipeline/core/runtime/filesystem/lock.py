"""Un verrou de fichiers : au plus un porteur d'un nom a la fois.

Un `mkdir` et non un fichier de garde : la creation d'un repertoire est
atomique sur tous les systemes de fichiers qui nous concernent, donc deux
processus partis en meme temps ne peuvent pas l'obtenir tous les deux.
"""

from __future__ import annotations

import contextlib
from pathlib import Path


@contextlib.contextmanager
def claim(where: Path, name: str):
    """Le verrou de `name` sous `where`. Rend False si quelqu'un le tient."""
    where.mkdir(parents=True, exist_ok=True)
    lock = where / f".lock-{name}"
    try:
        lock.mkdir()
    except FileExistsError:
        yield False
        return
    try:
        yield True
    finally:
        with contextlib.suppress(OSError):
            lock.rmdir()
