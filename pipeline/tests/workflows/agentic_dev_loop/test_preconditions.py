"""What has to hold before a single stage is billed.

Every check here cost a run to write: a typo in the table costs nothing to
find before the first `claude`, and a whole stage to find after. None of it
was tested — and these tests run no git, no gh, no claude: the adapters are
replaced where they are built (`common.utils.hub`) and where they look on the
PATH (`adapters.shell.binaries`).

Les portes elles-memes vivent a deux endroits depuis qu'elles sont partagees :
les communes dans `common.utils.checks`, celles de la boucle ici. Ce fichier
exerce la liste composee — c'est elle qui tourne vraiment.
"""

import io
import re
import subprocess
import textwrap
import types

import pytest
from conftest import milestone

from pipeline.workflows.agentic_dev_loop.internals import tasks
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.core.adapters.shell import binaries
from pipeline.core.adapters.shell.git import Git
from pipeline.workflows.agentic_dev_loop.preconditions import LoopPreconditions
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.stages import PIPELINE
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.common.utils import hub as adapters


class Shell:
    """The paper repo that `git` and `gh` see."""

    def __init__(self):
        self.branch = "main_agent"
        self.dirty = ""
        self.branch_exists = True
        self.origin_has_branch = True
        self.calls: list[list[str]] = []

    def run(self, cmd, *a, **kw):
        argv = list(cmd)
        self.calls.append(argv)
        out, code = "", 0
        if "symbolic-ref" in argv:
            out = self.branch + "\n"
        elif "--porcelain" in argv:
            out = self.dirty
        elif "ls-remote" in argv:
            code = 0 if self.origin_has_branch else 2
        elif "--verify" in argv:
            code = 0 if self.branch_exists else 1
        elif "--short" in argv and "rev-parse" in argv:
            out = "4637718\n"
        return subprocess.CompletedProcess(argv, code, out, "")


@pytest.fixture
def repo(tmp_path, monkeypatch, hub):
    """A repo where everything is in place: preflight must pass without a word.

    `hub` is the fake GitHub: two of the gates below ask it for the labels
    and for the current milestone, and neither may reach the network.
    """
    ws = Workspace(tmp_path)
    for name in [s.skill for s in PIPELINE] + ["tech-analyst"]:
        (ws.skills / name).mkdir(parents=True)
        (ws.skills / name / "SKILL.md").write_text("# %s\n" % name,
                                                   encoding="utf-8")
    milestone(hub, ready=(0,), tasks=("Une task",))
    ws.ci_workflow.parent.mkdir(parents=True, exist_ok=True)
    ws.ci_workflow.write_text(textwrap.dedent("""\
        on:
          pull_request:
            branches: [main, main_agent]
        """), encoding="utf-8")

    shell = Shell()
    shell.hub = hub
    shell.workspace = ws
    # Les deux coutures, posees la ou les adaptateurs sont construits plutot
    # que dans le module qui les interroge : `hub` est le seul endroit du
    # paquet qui fabrique un `Git`, et `binaries` le seul qui regarde le PATH.
    monkeypatch.setattr(adapters, "git",
                        lambda root, run=None: Git(root, run=shell.run))
    monkeypatch.setattr(binaries, "shutil",
                        types.SimpleNamespace(which=lambda n: "/usr/bin/" + n))
    return shell


@pytest.fixture
def said():
    out = io.StringIO()
    return out, logbook.open_logbook("test.preflight", stream=out)


def cfg(repo, **kw):
    return RunConfig(run_id="20260910-090000", max_rounds=1,
                     workspace=repo.workspace, **kw)


def verify(repo, log=None, **kw):
    """Le preflight, tel que la sequence du contrat l'appelle."""
    return LoopPreconditions(cfg(repo, **kw), log or logbook.null()).verify()


def test_a_repository_in_order_passes_and_says_where_it_starts(repo, said):
    out, log = said
    assert verify(repo, log).ok
    written = out.getvalue()
    assert "run 20260910-090000 — branch main_agent @ 4637718, 1 round(s)" in written
    assert "business-analyst(opus/high)" in written
    assert "permission mode: bypassPermissions" in written


def test_a_missing_claude_stops_before_anything_else(repo, monkeypatch):
    monkeypatch.setattr(binaries, "shutil",
                        types.SimpleNamespace(which=lambda name: None))
    got = verify(repo)
    assert got.failed and re.search("claude CLI not on PATH", got.reason)


def test_a_missing_gh_is_named_as_such(repo, monkeypatch):
    monkeypatch.setattr(binaries, "shutil", types.SimpleNamespace(
        which=lambda name: None if name == "gh" else "/usr/bin/claude"))
    got = verify(repo)
    assert got.failed and re.search("gh CLI not on PATH", got.reason)


def test_an_unauthenticated_gh_says_how_to_fix_it(repo):
    repo.hub.authed = False
    got = verify(repo)
    assert got.failed and re.search("gh auth login", got.reason)


def test_no_open_milestone_issue_means_nothing_to_work_from(repo):
    """La porte que `docs/current/CURRENT_MILESTONE.md` tenait avant elle."""
    for issue in repo.hub.issues.values():
        issue["state"] = "closed"
    got = verify(repo)
    assert got.failed and re.search("nothing to work from", got.reason)


@pytest.mark.parametrize("missing", tasks.LABELS)
def test_a_label_the_model_needs_is_caught_before_paying(repo, missing):
    """Une etiquette absente ne leve nulle part : elle rend une liste vide.

    Et une liste vide de tasks se lit « ce milestone est fini », qui est
    l'entree qui fait payer un `/planner`. Un typo se trouve ici, pour rien.
    """
    repo.hub.repo_labels.remove(missing)
    got = verify(repo)
    assert got.failed and re.search("missing the label", got.reason)
    assert missing in verify(repo).reason


def test_a_github_that_will_not_answer_stops_before_the_first_stage(repo):
    """Une API muette au milieu d'un round coute un stage deja facture."""
    repo.hub.fails_on = "issues"
    got = verify(repo)
    assert got.failed and re.search("what is left to do is unknown", got.reason)


def test_the_milestone_gate_does_not_care_that_no_task_is_ready(repo):
    """Le preflight verifie l'atteignabilite, pas la jouabilite.

    Une task non prete est un arret du round, avec son propre message : le
    dupliquer ici ferait dire deux choses differentes au meme etat.
    """
    for issue in repo.hub.issues.values():
        issue["labels"] = [l for l in issue["labels"]
                           if l["name"] != tasks.READY]
    assert verify(repo).ok


def test_a_pipeline_skill_without_a_skill_file_is_caught_before_paying(repo):
    (repo.workspace.skills / "create-test" / "SKILL.md").unlink()
    got = verify(repo)
    assert got.failed and re.search("PIPELINE names /create-test", got.reason)


def test_a_missing_lead_command_is_caught_too(repo):
    """`lead` n'est le nom d'aucune entree : la boucle sur PIPELINE l'ignore."""
    (repo.workspace.skills / "tech-analyst" / "SKILL.md").unlink()
    got = verify(repo)
    assert got.failed and re.search("opens on /tech-analyst", got.reason)


def test_a_filtered_out_lead_is_not_required(repo):
    """--stages create-test does not run /code: its lead is beside the point."""
    (repo.workspace.skills / "tech-analyst" / "SKILL.md").unlink()
    assert verify(repo, stages="create-test").ok


def test_a_configured_rollover_skill_is_checked_as_well(repo, monkeypatch):
    got = verify(repo, rollover=StageSpec("planner", "opus", "high"))
    assert got.failed and "PIPELINE names /planner" in got.reason


def test_an_absent_integration_branch_says_how_to_create_it(repo):
    repo.branch_exists = False
    got = verify(repo)
    assert got.failed and re.search("git branch main_agent origin/main", got.reason)


def test_being_on_another_branch_stops_the_run(repo):
    repo.branch = "feat/autre-chose"
    got = verify(repo)
    assert got.failed and re.search("on branch feat/autre-chose", got.reason)


def test_a_branch_origin_never_saw_stops_the_run(repo):
    repo.origin_has_branch = False
    got = verify(repo)
    assert got.failed and re.search("origin has no main_agent", got.reason)


def test_a_ci_that_does_not_trigger_on_the_branch_stops_the_run(repo):
    """With no `ci` check, the `gh pr checks` the skills await never resolves."""
    repo.workspace.ci_workflow.write_text(
        "on:\n  pull_request:\n    branches: [main]\n", encoding="utf-8")
    got = verify(repo)
    assert got.failed and re.search("does not trigger on main_agent", got.reason)


def test_a_missing_ci_workflow_stops_the_run(repo):
    repo.workspace.ci_workflow.unlink()
    got = verify(repo)
    assert got.failed and re.search("does not trigger on main_agent", got.reason)


def test_a_dirty_tree_is_listed_before_it_stops_the_run(repo, said):
    out, log = said
    repo.dirty = " M src/app/page.tsx\n?? .env.local\n"
    got = verify(repo, log)
    assert got.failed and re.search("ALLOW_DIRTY=1", got.reason)
    written = out.getvalue()
    assert "src/app/page.tsx" in written and ".env.local" in written
    assert "WARN" in written


def test_allow_dirty_lets_it_through(repo):
    repo.dirty = " M src/app/page.tsx\n"
    assert verify(repo, allow_dirty=True).ok


def test_the_stages_left_out_are_announced_rather_than_vanishing(repo, said):
    out, log = said
    assert verify(repo, log, stages="code").ok
    written = out.getvalue()
    assert "filtered out by --stages" in written
    assert "business-analyst" in written and "create-test" in written


def test_the_git_calls_all_name_the_repository(repo):
    """`git -C <root>`: preflight does not depend on the current directory."""
    assert verify(repo).ok
    for argv in repo.calls:
        if argv[0] == "git":
            assert argv[1:3] == ["-C", str(repo.workspace.root)]
