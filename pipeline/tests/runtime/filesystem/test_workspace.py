"""Le workspace : une racine, et les chemins que la boucle en derive."""

from pathlib import Path

from pipeline.runtime.filesystem.workspace import Workspace


def test_every_derived_path_hangs_off_the_root_it_was_given():
    ws = Workspace(Path("/un/depot"))
    assert ws.loop_dir == Path("/un/depot/.llocal/agent-loop")
    assert ws.state == Path("/un/depot/.llocal/agent-loop/state")
    assert ws.ledger == Path("/un/depot/.llocal/agent-loop/costs.tsv")
    assert ws.flow_db == Path("/un/depot/.llocal/agent-loop/flow_states.db")
    assert ws.review_dir == Path("/un/depot/.llocal/pr-review")
    assert ws.review_ledger == Path("/un/depot/.llocal/pr-review/costs.tsv")
    assert ws.skills == Path("/un/depot/.claude/skills")
    assert ws.ci_workflow == Path("/un/depot/.github/workflows/ci.yml")
    # Et les trois qui partagent un repertoire le partagent encore.
    assert ws.state.parent == ws.loop_dir
    assert ws.ledger.parent == ws.loop_dir
    assert ws.review_ledger.parent == ws.review_dir


def test_rel_answers_relative_inside_the_root(tmp_path):
    assert Workspace(tmp_path).rel(tmp_path / "docs" / "x.md") == "docs/x.md"


def test_rel_never_raises_on_a_path_outside_the_root(tmp_path):
    """Un message de journal ne fait pas tomber un run."""
    outside = tmp_path.parent / "ailleurs.md"
    assert Workspace(tmp_path).rel(outside) == str(outside)


def test_here_finds_the_checkout_this_package_lives_in():
    root = Workspace.here().root
    assert (root / ".git").exists()
    assert (root / "pipeline" / "src" / "pipeline").is_dir()

