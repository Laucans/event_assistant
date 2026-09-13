"""The hooks: the same decisions as before, and they fail open.

`oracle/branch-guard.tsv` carries the decisions of the inline hook from
`.claude/settings.json`, captured before its migration: one command per line,
with the exit code it returned.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest
from conftest import ORACLE

from pipeline.launcher.hooks import (
    branch_guard, no_secret_paths, scratchpad_notice)

ENTRY = ORACLE.parents[2] / "scripts" / "hooks" / "branch-guard.py"


# `.claude/settings.json` invoque les hooks avec `python3` : le python du
# systeme, hors du venv. C'est lui qu'il faut utiliser ici, sinon le test
# s'appuie sur un `pipeline` installe que la production n'a pas.
def _system_python():
    venv_bin = os.path.realpath(os.path.join(sys.prefix, "bin"))
    path = os.pathsep.join(
        d for d in os.environ.get("PATH", "").split(os.pathsep)
        if d and os.path.realpath(d) != venv_bin)
    # Repli : `sys.executable`, le seul chemin dont on sait qu'il existe.
    # `base_prefix/bin/python3` n'existe pas partout (le framework Homebrew
    # n'a que `python3.13`) et donnait un FileNotFoundError illisible. Que le
    # repli soit le python du venv n'affaiblit rien : c'est `sans_pipeline`,
    # pas le choix de l'interpreteur, qui garantit l'echec d'import.
    return shutil.which("python3", path=path) or sys.executable


SYSTEM_PY = _system_python()


def run_entry(cmd):
    """The hook as Claude Code calls it: one process, JSON on stdin."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    return subprocess.run([SYSTEM_PY, str(ENTRY)], input=payload,
                          capture_output=True, text=True).returncode


ORACLE_CASES = [tuple(l.split("\t")) for l in
                (ORACLE / "branch-guard.tsv").read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("cmd, expected", ORACLE_CASES)
def test_branch_guard_decides_exactly_as_the_inline_hook_did(cmd, expected):
    assert run_entry(cmd) == int(expected)


@pytest.mark.parametrize("cmd", [
    "git push", "git push origin HEAD", "git push origin @",
])
def test_a_bare_push_follows_the_current_branch(cmd):
    assert branch_guard.targets_main(cmd, "main") is True
    assert branch_guard.targets_main(cmd, "feat/x") is False


def test_a_push_to_another_remote_branch_is_allowed():
    assert branch_guard.targets_main("git push origin maintenance", "main") is False
    assert branch_guard.targets_main("git push origin main-ish", "main") is False


def test_a_broken_payload_fails_open():
    r = subprocess.run([SYSTEM_PY, str(ENTRY)], input="pas du json",
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_a_non_bash_tool_is_ignored():
    r = subprocess.run([SYSTEM_PY, str(ENTRY)],
                       input=json.dumps({"tool_name": "Edit", "tool_input": {}}),
                       capture_output=True, text=True)
    assert r.returncode == 0


@pytest.mark.parametrize("token, blocked", [
    (".env", True), ("./.env", True), (".env.local", True),
    (".env.example", False), (".env.sample", False), (".env.template", False),
    ("secrets/key.pem", True), ("docs/PROJECT.md", False), ("", False),
])
def test_secret_paths_are_recognised(token, blocked):
    assert bool(no_secret_paths.offending(token, "/home/x")) is blocked


def test_a_quoted_heredoc_body_is_not_scanned():
    cmd = "cat > note.md <<'EOF'\non parle de .env.local ici\nEOF\n"
    stripped = no_secret_paths.strip_quoted_heredocs(cmd)
    assert ".env.local" not in stripped


def test_an_unquoted_heredoc_body_stays_in_scope():
    cmd = "cat > note.md <<EOF\n$(cat .env.local)\nEOF\n"
    assert ".env.local" in no_secret_paths.strip_quoted_heredocs(cmd)


def test_scratchpad_notice_shortens_a_long_command():
    msg = scratchpad_notice.notice(
        "Bash", {"command": "python3 /tmp/claude-501/xyz/scratchpad/a.py " + "x" * 200})
    assert msg.startswith("scratchpad: Bash") and msg.endswith("...")
    assert "/tmp/claude-501" not in msg


def test_scratchpad_notice_names_the_file_for_a_write():
    msg = scratchpad_notice.notice(
        "Write", {"file_path": "/tmp/claude-501/xyz/scratchpad/rapport.md"})
    assert msg == "scratchpad: Write .../rapport.md"


def test_a_path_outside_the_scratchpad_says_nothing():
    assert scratchpad_notice.notice("Write", {"file_path": "src/app/page.tsx"}) is None


ORPHANS = [("branch-guard.py", 2), ("no-secret-paths.py", 2),
           ("scratchpad-notice.py", 0), ("pr-review-trigger.py", 0)]


@pytest.fixture
def sans_pipeline(tmp_path):
    """L'environnement ou `import pipeline` echoue, sur n'importe quelle machine.

    Copier l'entree hors du depot casse son `sys.path.insert` — mais seulement
    si rien d'autre ne fournit le paquet. La CI fait `pip install -e pipeline`
    dans le python meme qui lance les hooks : l'orphelin s'y importait tres
    bien et la garde se taisait — trois tests verts en local, rouges sur la
    CI. Un `pipeline` qui leve, place en tete de PYTHONPATH, reproduit la
    panne partout au lieu de dependre de ce que la machine a installe.
    """
    shim = tmp_path / "shim"
    (shim / "pipeline").mkdir(parents=True)
    (shim / "pipeline" / "__init__.py").write_text(
        'raise ImportError("pipeline indisponible")\n', encoding="utf-8")
    return {**os.environ, "PYTHONPATH": str(shim)}


@pytest.mark.parametrize("name, expected", ORPHANS)
def test_a_hook_that_cannot_load_fails_the_right_way(name, expected, tmp_path,
                                                    sans_pipeline):
    """Revue du 2026-09-09, finding n°4.

    Copiee hors du depot, l'entree ne trouve plus `pipeline.launcher` : les hooks
    de securite doivent bloquer bruyamment (2), les hooks informatifs laisser
    passer (0). Un exit 1 ne bloque rien — c'etait la garde qui se taisait.
    """
    orphan = tmp_path / name
    orphan.write_text((ORACLE.parents[2] / "scripts" / "hooks" / name)
                      .read_text(encoding="utf-8"), encoding="utf-8")
    r = subprocess.run(
        [SYSTEM_PY, str(orphan)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        capture_output=True, text=True, env=sans_pipeline)
    assert r.returncode == expected, r.stderr


def test_the_orphan_really_cannot_import_the_package(sans_pipeline):
    """Guard for the test above: without this fact it would pass vacuously."""
    r = subprocess.run([SYSTEM_PY, "-c", "import pipeline"],
                       capture_output=True, text=True, cwd="/", env=sans_pipeline)
    assert r.returncode != 0
