"""La table des routes, et le routeur qui la lit."""

import argparse
import subprocess
import sys
import types

import pytest

from pipeline.launcher import routes, validation
from pipeline.launcher.main import main
from pipeline.core.runtime.filesystem.workspace import Workspace

ROOT = Workspace.here().root
SRC = ROOT / "pipeline/src"


@pytest.fixture
def dispatched(monkeypatch):
    """Chaque cible de la table, remplacee par un temoin qui note ses appels."""
    seen: list[tuple[str, str, list[str]]] = []

    def witness(route):
        module = types.ModuleType(route.target)

        def parse_args(argv=None):
            seen.append((route.name, "parse_args", list(argv or [])))
            return argparse.Namespace(level="medium")

        def config_to_check(args):
            return argparse.Namespace(level="medium")

        def entry(argv=None):
            seen.append((route.name, "main", list(argv or [])))
            return 0

        module.parse_args = parse_args
        module.config_to_check = config_to_check
        module.main = entry
        return module

    for route in routes.ROUTES:
        monkeypatch.setitem(sys.modules, route.target, witness(route))
    return seen


# --- la table --------------------------------------------------------------


def test_every_route_has_a_unique_name_and_a_known_protocol():
    names = [route.name for route in routes.ROUTES]
    assert len(names) == len(set(names)), names
    assert {route.protocol for route in routes.ROUTES} == {"cli", "hook"}


def test_the_table_names_the_two_commands_and_the_four_hooks():
    assert [r.name for r in routes.ROUTES if r.protocol == "cli"] == [
        "loop", "pr-review"]
    assert [r.name for r in routes.ROUTES if r.protocol == "hook"] == [
        "branch-guard", "no-secret-paths", "pr-review-trigger",
        "scratchpad-notice"]


def test_migrate_is_not_a_route():
    assert routes.find("migrate") is None


def test_every_target_is_a_module_that_exists():
    for route in routes.ROUTES:
        path = SRC / (route.target.replace(".", "/") + ".py")
        assert path.exists(), route.target


def test_the_table_and_validation_name_exactly_the_same_rules():
    """Dans les deux sens : une regle que personne ne nomme ne s'applique pas."""
    named = {rule for route in routes.ROUTES for rule in route.rules}
    assert named == validation.RULES, {
        "nommees mais non implementees": sorted(named - validation.RULES),
        "implementees mais nommees par aucune route": sorted(
            validation.RULES - named)}


def test_the_default_route_is_the_loop():
    assert routes.DEFAULT == "loop"
    assert routes.default() is routes.find("loop")


def test_a_hook_route_carries_no_validation_rule():
    assert all(not route.rules
               for route in routes.ROUTES if route.protocol == "hook")


# --- le dispatch -----------------------------------------------------------


@pytest.mark.parametrize("name", [route.name for route in routes.ROUTES])
def test_the_router_dispatches_every_route_of_the_table(name, dispatched):
    assert main([name]) == 0
    assert (name, "main", []) in dispatched


def test_an_unknown_first_argument_falls_back_to_the_loop(dispatched):
    assert main(["--rounds", "1"]) == 0
    assert dispatched == [("loop", "parse_args", ["--rounds", "1"]),
                          ("loop", "main", ["--rounds", "1"])]


def test_no_argument_at_all_runs_the_loop(dispatched):
    assert main([]) == 0
    assert dispatched == [("loop", "parse_args", []), ("loop", "main", [])]


def test_the_route_name_is_not_passed_on_to_the_command(dispatched):
    assert main(["pr-review", "12", "--force"]) == 0
    assert dispatched == [("pr-review", "parse_args", ["12", "--force"]),
                          ("pr-review", "main", ["12", "--force"])]


def test_a_hook_is_never_asked_to_parse_arguments(dispatched):
    assert main(["branch-guard"]) == 0
    assert dispatched == [("branch-guard", "main", [])]


def test_a_hook_that_returns_nothing_lets_the_tool_call_through(monkeypatch):
    module = types.ModuleType("pipeline.launcher.hooks.scratchpad_notice")
    module.main = lambda: None
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert main(["scratchpad-notice"]) == 0


def test_a_hook_that_blocks_keeps_its_exit_code(monkeypatch):
    module = types.ModuleType("pipeline.launcher.hooks.branch_guard")

    def blocks():
        raise SystemExit(2)

    module.main = blocks
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(SystemExit) as exc:
        main(["branch-guard"])
    assert exc.value.code == 2


def test_a_refused_run_never_reaches_the_command(monkeypatch, dispatched,
                                                 capsys):
    monkeypatch.setattr(validation, "check",
                        lambda route, cfg, **_: (["un refus"], []))
    assert main(["loop", "--rounds", "0"]) == 1
    assert ("loop", "main", ["--rounds", "0"]) not in dispatched
    assert "un refus" in capsys.readouterr().err


def test_the_rules_really_reach_the_real_loop_parser(capsys):
    assert main(["loop", "--rounds", "0"]) == 1
    assert "--rounds" in capsys.readouterr().err


def test_a_warning_does_not_stop_the_run(monkeypatch, dispatched, capsys):
    monkeypatch.setattr(validation, "check",
                        lambda route, cfg, **_: ([], ["un avertissement"]))
    assert main(["loop"]) == 0
    assert ("loop", "main", []) in dispatched
    assert "un avertissement" in capsys.readouterr().err


# --- ce que le routeur ne fait surtout pas -------------------------------

ROUTER_FIRST = """
import os, sys
import pipeline.launcher.main as router

assert os.environ.get("ANTHROPIC_API_KEY"), "le routeur a touche a l'environnement"
assert "claude_agent_sdk" not in sys.modules, "le routeur a importe le SDK"
assert "claude_agent_sdk" not in sys.modules, "le routeur a importe le SDK"

sys.argv = ["agent-loop", "loop", "--costs"]
router.main()

assert os.environ.get("ANTHROPIC_API_KEY") is None, "la cle a survecu a la route"
assert "claude_agent_sdk" not in sys.modules, "le chemin rapide a importe le SDK"
assert "claude_agent_sdk" not in sys.modules, "le chemin rapide a importe le SDK"
print("ROUTER-OK")
"""


def test_the_router_costs_nothing_and_the_route_still_drops_the_api_key():
    """Les pop d'environnement du module cible passent avant tout import lourd."""
    r = subprocess.run(
        [sys.executable, "-c", ROUTER_FIRST], capture_output=True, text=True,
        cwd=str(ROOT),
        env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "sk-ne-doit-pas-survivre",
             "PYTHONPATH": str(ROOT / "pipeline" / "src")})
    assert "ROUTER-OK" in r.stdout, r.stderr
