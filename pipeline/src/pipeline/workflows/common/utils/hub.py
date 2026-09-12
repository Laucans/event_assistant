"""Les adaptateurs, construits a l'appel plutot qu'a l'import.

Un passe-plat, et c'est voulu : `gh` et `git` sont emballes dans
`adapters.shell`, et rien ici ne les appelle. Ce que ce module apporte est
l'endroit unique ou ils sont **construits** — un objet de module figerait la
racine du depot, qui n'existe pas encore a l'import, et un test n'aurait plus
de couture ou glisser son double.

Une seule couture pour tous les workflows : remplacer `hub.github` met GitHub
sur papier pour le round, la revue, le preflight et `--status` a la fois.
Avant, `board.hub()` et `preconditions._git()` faisaient ce travail chacun de
son cote — et `legacy.migrate` importait le premier, ce qui reliait la
bascule au workflow vivant pour une fabrique de trois lignes.
"""

from __future__ import annotations

import subprocess

from pipeline.core.adapters.shell.git import Git
from pipeline.core.adapters.shell.github import GitHub
from pipeline.core.runtime.filesystem.workspace import Workspace

# Les deux classes, nommees ici pour qu'un test n'ait qu'un endroit a
# remplacer. `conftest` s'en sert.
github = GitHub
git = Git


def gh(workspace: Workspace) -> GitHub:
    """L'adaptateur `gh` de ce workspace."""
    return github(workspace.root)


def repo(workspace: Workspace) -> Git:
    """L'adaptateur `git` de ce workspace."""
    return git(workspace.root, run=subprocess.run)
