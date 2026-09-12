"""The repository root. One place that knows where the checkout is.

It is resolved on first use, not at import. The root used to be computed at
module scope by shelling out to git, so importing *any* module of this
package — a hook, `--help`, a test collecting — spawned a subprocess, and
raised a bare `CalledProcessError` outside a git checkout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class NotARepository(RuntimeError):
    """The repository root could not be resolved — said in words, not in a
    non-zero exit status from a subprocess nobody saw run."""


_root: Path | None = None


def _resolve_root() -> Path:
    """Find the checkout this package lives in.

    Walking up from this file answers without a subprocess at all, and answers
    with *this* repository rather than with whatever repository the caller's
    working directory happened to be in. `git rev-parse` remains the fallback
    for a layout where the package is installed away from its checkout.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    root = out.stdout.strip()
    if out.returncode != 0 or not root:
        detail = (out.stderr or "").strip() or "no output"
        raise NotARepository(
            f"cannot locate the repository root: no .git above {__file__}, and"
            f" `git rev-parse --show-toplevel` failed (exit {out.returncode}:"
            f" {detail}). Run the loop from inside the checkout.")
    return Path(root)


def repo_root() -> Path:
    """The git repository root, resolved once and remembered."""
    global _root
    if _root is None:
        _root = _resolve_root()
    return _root
