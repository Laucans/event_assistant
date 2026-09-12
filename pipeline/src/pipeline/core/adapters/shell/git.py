"""Le binaire `git`, emballe.

Une classe et non des fonctions de module : c'est ce qui permet a un test de
passer un double au lieu de monkeypatcher `subprocess` sur le module qui
l'appelle. Chaque appel nomme le depot (`-C <root>`) plutot que de dependre
du repertoire courant — la boucle tourne depuis n'importe ou, et un `git
status` qui repondrait sur un autre depot laisserait passer un arbre sale.

Rien ici ne decide : les portes vivent dans
`workflows.agentic_dev_loop.preconditions`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class Git:
    """Ce que la boucle demande a git, et rien de plus."""

    def __init__(self, root: Path, run=subprocess.run) -> None:
        self.root = root
        self._run = run

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(["git", "-C", str(self.root), *args],
                         capture_output=True, text=True)

    def current_branch(self) -> str:
        return self("symbolic-ref", "--short", "HEAD").stdout.strip()

    def head_sha(self) -> str:
        return self("rev-parse", "--short", "HEAD").stdout.strip()

    def dirty_files(self) -> list[str]:
        return [l for l in self("status", "--porcelain").stdout.splitlines() if l]

    def has_branch(self, name: str) -> bool:
        return self("rev-parse", "--verify", "--quiet", name).returncode == 0

    def origin_has_branch(self, name: str) -> bool:
        return self("ls-remote", "--exit-code", "--heads", "origin",
                    name).returncode == 0
