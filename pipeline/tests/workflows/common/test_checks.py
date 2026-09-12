"""Les portes communes : ce qu'elles verifient, et par ou elles le demandent.

Elles etaient les portes de la boucle, et elles sont desormais celles de tout
workflow — la revue de PR les a gagnees sans que personne les reecrive. Ces
tests-la portent sur elles seules ; leur composition en listes vit avec chaque
workflow.

Aucun appel externe ici non plus : la couture est dans `core.adapters.hub`,
qui est le seul endroit du paquet qui construit un client.
"""

import subprocess
import types

import pytest

from pipeline.core.adapters.shell import binaries
from pipeline.core.adapters.shell.git import Git
from pipeline.core.domain.outcomes.result import Result, Status
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.core.adapters import hub
from pipeline.workflows.common import checks


class Repo:
    """Le depot sur papier que `git` voit."""

    def __init__(self):
        self.branch = "main_agent"
        self.dirty = ""
        self.branch_exists = True
        self.origin_has_branch = True

    def run(self, cmd, *a, **kw):
        argv, out, code = list(cmd), "", 0
        if "symbolic-ref" in argv:
            out = self.branch + "\n"
        elif "--porcelain" in argv:
            out = self.dirty
        elif "ls-remote" in argv:
            code = 0 if self.origin_has_branch else 2
        elif "--verify" in argv:
            code = 0 if self.branch_exists else 1
        return subprocess.CompletedProcess(argv, code, out, "")


class Cfg:
    """Le minimum qu'une porte commune lit dans une config."""

    def __init__(self, workspace, branch="main_agent", allow_dirty=False):
        self.workspace = workspace
        self.integration_branch = branch
        self.allow_dirty = allow_dirty


@pytest.fixture
def cfg(tmp_path):
    return Cfg(Workspace(tmp_path))


@pytest.fixture
def repo(monkeypatch):
    here = Repo()
    monkeypatch.setattr(hub, "git",
                        lambda root, run=None: Git(root, run=here.run))
    return here


@pytest.fixture
def on_path(monkeypatch):
    monkeypatch.setattr(binaries, "shutil",
                        types.SimpleNamespace(which=lambda n: "/usr/bin/" + n))


@pytest.fixture
def hub_double(hub):
    """Le double de `gh` de conftest, nomme pour ne pas masquer le module."""
    return hub


def log():
    return logbook.null()


# --- les outils -------------------------------------------------------------


def test_a_binary_on_the_path_passes(on_path, cfg):
    assert checks.claude_on_path(cfg, log()).ok
    assert checks.gh_on_path(cfg, log()).ok


@pytest.mark.parametrize("gate, missing, said", [
    (checks.claude_on_path, "claude", "claude CLI not on PATH"),
    (checks.gh_on_path, "gh", "gh CLI not on PATH"),
])
def test_a_missing_binary_says_which_one(monkeypatch, cfg, gate, missing,
                                         said):
    monkeypatch.setattr(binaries, "shutil", types.SimpleNamespace(
        which=lambda n: None if n == missing else "/usr/bin/" + n))
    got = gate(cfg, log())
    assert got.status is Status.HALTED and got.reason == said


def test_an_unauthenticated_gh_says_the_gesture_to_make(cfg, hub_double):
    hub_double.authed = False
    got = checks.gh_authenticated(cfg, log())
    assert got.failed and "gh auth login" in got.reason


def test_an_authenticated_gh_passes(cfg, hub_double):
    assert checks.gh_authenticated(cfg, log()).ok


# --- la branche d'integration ----------------------------------------------


def test_a_branch_that_exists_and_is_checked_out_passes(repo, cfg):
    assert checks.integration_branch_exists(cfg, log()).ok
    assert checks.on_the_integration_branch(cfg, log()).ok
    assert checks.branch_is_on_origin(cfg, log()).ok


def test_an_absent_branch_says_how_to_create_it(repo, cfg):
    repo.branch_exists = False
    got = checks.integration_branch_exists(cfg, log())
    assert got.failed and "git branch main_agent origin/main" in got.reason


def test_being_on_another_branch_names_the_one_you_are_on(repo, cfg):
    repo.branch = "feat/autre-chose"
    got = checks.on_the_integration_branch(cfg, log())
    assert got.failed and "on branch feat/autre-chose" in got.reason


def test_a_branch_origin_never_saw_says_how_to_push_it(repo, cfg):
    repo.origin_has_branch = False
    got = checks.branch_is_on_origin(cfg, log())
    assert got.failed and "git push -u origin main_agent" in got.reason


# --- l'arbre de travail -----------------------------------------------------


def test_a_clean_tree_passes(repo, cfg):
    assert checks.working_tree_is_clean(cfg, log()).ok


def test_a_dirty_tree_is_listed_before_it_stops_the_run(repo, cfg):
    import io
    said = io.StringIO()
    repo.dirty = " M src/app/page.tsx\n?? .env.local\n"
    got = checks.working_tree_is_clean(
        cfg, logbook.open_logbook("test.checks", stream=said))
    assert got.failed and "ALLOW_DIRTY=1" in got.reason
    written = said.getvalue()
    assert "src/app/page.tsx" in written and ".env.local" in written


def test_allow_dirty_lets_it_through(repo, cfg):
    repo.dirty = " M src/app/page.tsx\n"
    assert checks.working_tree_is_clean(
        Cfg(cfg.workspace, allow_dirty=True), log()).ok


def test_a_config_without_the_setting_simply_wants_a_clean_tree(repo, tmp_path):
    """`allow_dirty` est lu par `getattr` : un workflow qui ne l'offre pas
    n'a pas a porter un champ pour cette porte."""
    class Bare:
        workspace = Workspace(tmp_path)

    repo.dirty = " M a.ts\n"
    assert checks.working_tree_is_clean(Bare(), log()).failed


# --- ce que `verify_all` fait de la liste -----------------------------------


def test_verify_all_stops_at_the_first_failure():
    """Les portes se supposent : demander les etiquettes n'a pas de sens
    tant qu'on ne sait pas si `gh` est authentifie."""
    seen = []

    def gate(name, answer):
        def verify(cfg, log):
            seen.append(name)
            return answer
        return checks.Check(name, verify)

    got = checks.verify_all((
        gate("un", Result.of(None)),
        gate("deux", Result.halt("ici")),
        gate("trois", Result.of(None)),
    ), None, log())
    assert seen == ["un", "deux"], "une porte a tourne apres un echec"
    assert got.failed and got.reason == "ici"


def test_verify_all_passes_when_every_gate_does():
    got = checks.verify_all((), None, log())
    assert got.ok
