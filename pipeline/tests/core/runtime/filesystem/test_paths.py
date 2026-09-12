"""Where the repository root comes from, and when it is resolved.

Resolving it at import time meant that importing *any* module of this package
spawned `git rev-parse`, and that doing so outside a git checkout raised a
`CalledProcessError` before a single line of the loop ran.
"""

import subprocess
import sys

import pytest

from pipeline.core.runtime.filesystem import paths

LAZY = """
import sys
from pipeline.launcher.cli import agentic_dev_loop   # the whole fast path
from pipeline.core.runtime.filesystem import paths
assert paths._root is None, "importing the package already resolved the root"
assert paths.repo_root().name, "resolving on demand did not work"
assert paths._root is not None, "the resolved root was not remembered"
print("LAZY-OK")
"""


def test_importing_the_package_resolves_no_root_and_spawns_no_git():
    r = subprocess.run([sys.executable, "-c", LAZY], capture_output=True,
                       text=True, cwd=str(paths.repo_root()))
    assert "LAZY-OK" in r.stdout, r.stderr


def test_an_unknown_attribute_still_raises_attribute_error():
    with pytest.raises(AttributeError, match="PAS_UN_CHEMIN"):
        paths.PAS_UN_CHEMIN


def test_the_derived_paths_are_no_longer_module_attributes():
    """Le workspace les porte. Un `paths.X` qui repondrait ferait revivre le global."""
    for name in ("ROOT", "STATE", "FLOW_DB", "LEDGER", "SKILLS", "LOOP_DIR",
                 "REVIEW_DIR", "REVIEW_LEDGER", "CI_WORKFLOW"):
        assert name not in dir(paths)
        with pytest.raises(AttributeError, match=name):
            getattr(paths, name)


def test_the_pipeline_documents_are_not_paths_any_more():
    """Le milestone, le SPEC et le suivi humain sont des issues.

    Les garder ici laisserait un lecteur croire qu'il reste un fichier a
    lire, et un test qui les monkeypatche passerait sans rien exercer.
    """
    for name in ("MILESTONE", "SPEC", "TRACKING"):
        with pytest.raises(AttributeError, match=name):
            getattr(paths, name)


def test_outside_a_repository_the_error_says_so(tmp_path, monkeypatch):
    """`CalledProcessError: returned non-zero exit status 128` explained nothing."""
    monkeypatch.setattr(paths, "_root", None)
    monkeypatch.setattr(paths, "__file__", str(tmp_path / "pipeline/src/pipeline/paths.py"))
    monkeypatch.setattr(paths.subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(
                            a[0], 128, "", "fatal: not a git repository"))
    with pytest.raises(paths.NotARepository) as exc:
        paths.repo_root()
    assert "git" in str(exc.value) and "not a git repository" in str(exc.value)


def test_the_root_is_resolved_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(paths, "_root", None)
    monkeypatch.setattr(paths, "_resolve_root",
                        lambda: (calls.append(1), tmp_path)[1])
    assert paths.repo_root() == tmp_path
    assert paths.repo_root() == tmp_path
    assert len(calls) == 1

