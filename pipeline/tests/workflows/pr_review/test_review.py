"""The PR review: the prompt and the guards, as the shell held them.

`oracle/review-brief.txt` was produced by letting bash expand the heredoc of
`scripts/pr-review.sh` itself, with known values.

One passage has since been rewritten on purpose, in the source and in the
oracle in the same edit: the brief used to send the reviewer to
`docs/current/SPEC.md`, a file the move to issues deletes. A prompt that
names a missing file is paid for on every agent PR and orients nobody, so
the paragraph now names the issue the PR closes. Everything around it is
still the shell's text to the byte, which is what this file checks.
"""

import asyncio
import io
import json
import subprocess
import types

import pytest
from conftest import ORACLE, AssistantMessage, ToolUseBlock

from pipeline.adapters.shell import github
from pipeline.launcher.cli import pr_review as cli_review
from pipeline.domain.pr_review import notes as review_notes
from pipeline.domain.prompts.definitions.pr_review.brief import BRIEF_PROMPT
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.runtime.monitoring import logbook
from pipeline.adapters.shell import binaries
from pipeline.workflows.common.utils import hub as adapters
from pipeline.workflows.pr_review.internals import passes as passes_mod


def test_brief_prompt_still_matches_the_shell_to_the_byte():
    built = (BRIEF_PROMPT
             .replace("{num}", "42").replace("{title}", "Un titre de PR")
             .replace("{head}", "feat/x").replace("{base}", "main_agent")
             .replace("{findings}", "DES FINDINGS"))
    assert built == (ORACLE / "review-brief.txt").read_text(encoding="utf-8")


def test_every_placeholder_is_consumed():
    built = (BRIEF_PROMPT
             .replace("{num}", "1").replace("{title}", "t")
             .replace("{head}", "h").replace("{base}", "b")
             .replace("{findings}", "f"))
    assert "{" not in built.replace("{num}", "")


def test_the_marker_is_the_one_the_shell_posted():
    assert review_notes.MARKER == "<!-- agent-review -->"


def test_defaults_match_the_shell(monkeypatch):
    for var in ("PR_REVIEW_LEVEL", "PR_REVIEW_MODEL", "INTEGRATION_BRANCH"):
        monkeypatch.delenv(var, raising=False)
    args = cli_review.parse_args(["13"])
    assert args.level == "medium" and args.base == "main_agent"
    assert args.model == "" and not args.force and not args.no_inline


def test_env_overrides_are_read(monkeypatch):
    monkeypatch.setenv("PR_REVIEW_LEVEL", "high")
    monkeypatch.setenv("INTEGRATION_BRANCH", "autre")
    args = cli_review.parse_args(["13"])
    assert args.level == "high" and args.base == "autre"


def test_review_active_is_exported_at_import():
    import os
    assert os.environ["PR_REVIEW_ACTIVE"] == "1"


# --- les gardes, le verrou et le chemin de post ----------------------------
#
# Rien ici n'appelle `gh` ni `claude` : les deux sont remplaces. `_main` est
# ~110 lines of decisions — skip, lock, post — that had
# aucun test, alors que chacune protege deux passes payantes.


class FakeGh:
    """`gh`, on paper: what it answers, and what it was asked."""

    def __init__(self, **meta):
        self.meta = {"number": 12, "baseRefName": "main_agent",
                     "headRefName": "feat/x", "title": "Un titre de PR",
                     "url": "https://github.com/o/r/pull/12", "state": "OPEN",
                     "isDraft": False}
        self.meta.update(meta)
        self.meta_code = 0
        self.meta_stderr = ""
        self.comments = ""
        self.comments_code = 0
        self.comments_stderr = ""
        self.post_code = 0
        self.post_stderr = ""
        self.calls: list[tuple] = []

    def __call__(self, *args, check=True):
        self.calls.append(args)
        if args[:2] == ("pr", "view") and "comments" in args:
            return subprocess.CompletedProcess(
                args, self.comments_code, self.comments, self.comments_stderr)
        if args[:2] == ("pr", "view"):
            return subprocess.CompletedProcess(
                args, self.meta_code, json.dumps(self.meta), self.meta_stderr)
        if args[:2] == ("pr", "comment"):
            return subprocess.CompletedProcess(args, self.post_code, "",
                                               self.post_stderr)
        return subprocess.CompletedProcess(args, 0, "", "")

    @property
    def posted(self) -> bool:
        return any(a[:2] == ("pr", "comment") for a in self.calls)


@pytest.fixture
def ws(tmp_path):
    """Le workspace de la revue : `.llocal/pr-review/` tombe dans tmp_path."""
    workspace = Workspace(tmp_path)
    workspace.review_dir.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def rev(ws, monkeypatch):
    """A `pr-review` that calls nothing: gh, the passes and the journal on paper."""
    fake = FakeGh()
    # Injecte plutot que monkeypatche : c'est ce que la classe `GitHub`
    # existe pour permettre. La couture est dans `common.utils.hub`, qui est
    # desormais le seul endroit du paquet qui construit un client.
    monkeypatch.setattr(adapters, "github",
                        lambda root: github.GitHub(root, run=fake))
    # Les portes communes regardent le PATH : sur la machine d'un test, ni
    # `claude` ni `gh` n'ont a y etre pour que la revue soit exercee.
    monkeypatch.setattr(binaries, "shutil",
                        types.SimpleNamespace(which=lambda n: "/usr/bin/" + n))
    monkeypatch.setattr(cli_review, "make_logger",
                        lambda pr, workspace, level=logbook.NORMAL:
                        logbook.null())
    monkeypatch.setattr(cli_review, "Workspace",
                        types.SimpleNamespace(here=lambda: ws))
    return fake


@pytest.fixture
def passes(monkeypatch):
    """The two paid passes, replaced by a scriptable recorder."""
    ran = []
    script = {"inline": ("DES FINDINGS", None), "brief": ("Le corps", None)}

    async def fake_run(prompt, label, model, effort, num, dry_run, log,
                       *, workspace, heartbeat_s=60.0, verbose=False,
                       runner=None):
        ran.append(label)
        return script[label]

    monkeypatch.setattr(passes_mod, "run_pass", fake_run)
    return types.SimpleNamespace(ran=ran, script=script)


def main(*argv):
    return asyncio.run(cli_review._main(list(argv)))


def test_a_pr_that_cannot_be_read_fails_with_its_last_stderr_line(rev, capsys):
    rev.meta_code = 1
    rev.meta_stderr = "quelque chose\nfatal: pull request not found\n"
    assert main("12") == 2
    assert "cannot read PR 12" in capsys.readouterr().err


@pytest.mark.parametrize("meta, reason", [
    ({"baseRefName": "main"}, "targets 'main'"),
    ({"isDraft": True}, "is a draft"),
    ({"headRefName": "test/le-lot"}, "test PR"),
])
def test_the_skip_rules_cost_nothing(rev, passes, meta, reason):
    rev.meta.update(meta)
    assert main("12") == 0
    assert passes.ran == [], "une passe payante a tourne sur une PR a sauter"


def test_a_pr_already_reviewed_is_not_reviewed_twice(rev, passes):
    rev.comments = "un commentaire\n%s\n## Notes de revue" % review_notes.MARKER
    assert main("12") == 0
    assert passes.ran == []


def test_an_unreadable_comment_list_never_reads_as_never_reviewed(
        rev, passes, capsys):
    """« l'API est en panne » et « pas encore revue » menent a l'oppose.

    Une lecture ratee rendait une chaine vide, ou le marqueur n'est
    evidemment pas : la PR passait pour jamais revue et deux passes payees
    repostaient un commentaire en double.
    """
    rev.comments_code = 1
    rev.comments_stderr = "gh: could not resolve to a PullRequest"
    assert main("12") == 2
    assert passes.ran == [], "une passe payante a tourne sans savoir"
    assert not rev.posted
    assert "cannot read the comments of PR #12" in capsys.readouterr().err


def test_a_forced_review_does_not_need_to_read_the_comments(rev, passes):
    """`--force` reposte volontairement : la question ne se pose plus."""
    rev.comments_code = 1
    assert main("12", "--force") == 0
    assert passes.ran == ["inline", "brief"]


def test_force_overrides_every_skip_rule(rev, passes):
    rev.meta.update({"baseRefName": "main", "isDraft": True,
                     "headRefName": "test/le-lot"})
    rev.comments = review_notes.MARKER
    assert main("12", "--force") == 0
    assert passes.ran == ["inline", "brief"]


def test_a_second_review_of_the_same_pr_does_not_start(rev, passes, ws):
    """Deux hooks partis sur la meme PR posteraient la revue deux fois."""
    (ws.review_dir / ".lock-12").mkdir()
    assert main("12") == 0
    assert passes.ran == [] and not rev.posted


def test_the_lock_is_released_when_the_review_ends(rev, passes, ws):
    assert main("12") == 0
    assert not (ws.review_dir / ".lock-12").exists()


def test_a_review_that_posts_writes_the_comment_it_posted(rev, passes, ws):
    assert main("12") == 0
    assert passes.ran == ["inline", "brief"]
    body = (ws.review_dir / "12-comment.md").read_text(encoding="utf-8")
    assert body.startswith(review_notes.MARKER)
    assert "Le corps" in body
    assert "Revue automatique" in body
    assert "findings `sonnet`/niveau `medium`" in body
    assert rev.posted


def test_the_inline_pass_can_be_turned_off(rev, passes, ws):
    assert main("12", "--no-inline") == 0
    assert passes.ran == ["brief"]
    # Accentue : ce texte est publie sur une PR pour un lecteur francophone,
    # et il voisinait un pied de page qui, lui, disait « a pu être mergé ».
    assert "passe ligne à ligne désactivée" in (
        ws.review_dir / "12-comment.md").read_text(encoding="utf-8")


def test_a_dry_run_posts_nothing(rev, passes):
    assert main("12", "--dry-run") == 0
    assert not rev.posted


def test_a_failed_post_names_the_error_instead_of_a_list_repr(rev, passes,
                                                              ws, monkeypatch):
    """D7 : `splitlines()[-1:]` imprimait `['fatal: …']`, ou `[]` tout court."""
    said = io.StringIO()
    monkeypatch.setattr(cli_review, "make_logger",
                        lambda pr, workspace, level=logbook.NORMAL:
                        logbook.open_logbook("test.review", stream=said))
    rev.post_code = 1
    rev.post_stderr = "un prelude\nfatal: could not read Username\n"
    assert main("12") == 2
    written = said.getvalue()
    assert "fatal: could not read Username" in written
    assert "['fatal" not in written and "[]" not in written
    # Deux passes payees : le texte reste sur disque, et on dit ou.
    assert "12-comment.md" in written
    assert (ws.review_dir / "12-comment.md").exists()


def test_a_failed_post_with_no_stderr_still_says_something(rev, passes,
                                                           monkeypatch):
    said = io.StringIO()
    monkeypatch.setattr(cli_review, "make_logger",
                        lambda pr, workspace, level=logbook.NORMAL:
                        logbook.open_logbook("test.review2", stream=said))
    rev.post_code = 1
    assert main("12") == 2
    assert "(no output on stderr)" in said.getvalue()


def test_a_brief_pass_that_failed_is_a_failure_not_a_quota(rev, passes):
    passes.script["brief"] = (None, "failed")
    assert main("12") == 2
    assert not rev.posted


def test_a_brief_pass_out_of_quota_says_come_back_later(rev, passes):
    """`1` for both left a caller unable to tell the two follow-ups apart."""
    passes.script["brief"] = (None, "quota")
    assert main("12") == 3
    assert not rev.posted


def test_an_inline_pass_out_of_quota_does_not_start_the_second(rev, passes):
    passes.script["inline"] = (None, "quota")
    assert main("12") == 3
    assert passes.ran == ["inline"]


def test_an_inline_pass_that_merely_failed_lets_the_notes_be_written(rev, passes,
                                                                     tmp_path):
    passes.script["inline"] = (None, "failed")
    assert main("12") == 0
    assert passes.ran == ["inline", "brief"]
    assert rev.posted


def test_an_unexpected_error_is_logged_instead_of_escaping(monkeypatch, tmp_path):
    """The review runs detached from a hook: an uncaught traceback goes nowhere."""
    said = io.StringIO()
    monkeypatch.setattr(cli_review, "make_logger",
                        lambda pr, workspace, level=logbook.NORMAL:
                        logbook.open_logbook("test.review3", stream=said))

    async def boom(argv=None):
        raise RuntimeError("un interne du SDK")

    monkeypatch.setattr(cli_review, "_main", boom)
    assert cli_review.main(["12"]) == 4
    written = said.getvalue()
    assert "CRASH" in written
    assert "Traceback (most recent call last):" in written
    assert "un interne du SDK" in written


def test_an_interruption_keeps_its_own_code(monkeypatch):
    async def stopped(argv=None):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_review, "_main", stopped)
    assert cli_review.main(["12"]) == 130


def test_the_crash_log_is_named_after_the_pr(monkeypatch, tmp_path):
    assert cli_review._pr_arg(["--force", "13"]) == "13"
    assert cli_review._pr_arg(["--force"]) == "unknown"


def test_the_help_documents_every_env_var_the_review_reads(capsys):
    with pytest.raises(SystemExit):
        cli_review.parse_args(["--help"])
    out = capsys.readouterr().out
    for var in ("INTEGRATION_BRANCH", "PR_REVIEW_LEVEL", "PR_REVIEW_MODEL",
                "PR_REVIEW_INLINE_MODEL", "PR_REVIEW_INLINE_EFFORT",
                "PR_REVIEW_BRIEF_MODEL", "PR_REVIEW_BRIEF_EFFORT",
                "PR_REVIEW_ACTIVE"):
        assert var in out


# --- une passe, du SDK jusqu'au registre -----------------------------------

def one_pass(ws, label="inline", dry_run=False):
    return asyncio.run(passes_mod.run_pass("/code-review medium 12 --comment", label,
                                   "sonnet", "medium", "12", dry_run,
                                   logbook.null(), workspace=ws,
                                   heartbeat_s=0))


def test_a_pass_that_answers_books_its_cost_and_keeps_its_envelope(rev, ws,
                                                                   fake_sdk):
    fake_sdk.answers(
        AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a.ts"})]),
        result="DES FINDINGS", total_cost_usd=0.1234)
    assert one_pass(ws) == ("DES FINDINGS", None)

    envelope = json.loads(
        (ws.review_dir / "12-inline.json").read_text(encoding="utf-8"))
    assert envelope["result"] == "DES FINDINGS" and envelope["is_error"] is False
    row = ws.review_ledger.read_text(encoding="utf-8").splitlines()[1]
    assert row.split("\t")[1:4] == ["12", "inline", "0.123400"]
    assert "Read a.ts" in (ws.review_dir / "12-inline.trace.log").read_text(
        encoding="utf-8")


@pytest.mark.parametrize("fields, reason", [
    ({"api_error_status": 429}, "quota"),
    ({"is_error": True, "subtype": "error_during_execution"}, "failed"),
    ({"result": ""}, "empty"),
])
def test_a_pass_that_did_not_answer_says_which_kind_of_nothing(rev, ws,
                                                               fake_sdk,
                                                               fields, reason):
    fake_sdk.answers(**fields)
    assert one_pass(ws) == (None, reason)


def test_a_session_that_never_answered_is_its_own_reason(rev, ws, fake_sdk):
    fake_sdk.says_nothing()
    assert one_pass(ws) == (None, "no-result")


def test_a_dry_run_pass_prints_the_prompt_and_calls_nothing(rev, ws, fake_sdk,
                                                            capsys):
    assert one_pass(ws, dry_run=True) == (None, "dry-run")
    assert "/code-review medium 12 --comment" in capsys.readouterr().out
    assert fake_sdk.prompts == []


# --- ou tourne `gh`, et sur quelle PR ---------------------------------------

def test_every_gh_call_names_this_repository(monkeypatch, tmp_path):
    """`pr-review.sh:54` faisait `cd "$(git rev-parse --show-toplevel)"`.

    Sans ca, lancer `scripts/pr-review 12` depuis un autre checkout resout
    la PR #12 de *cet autre* depot : deux passes payantes sur le mauvais
    diff, et le commentaire poste sur une PR etrangere.
    """
    seen = []

    def record(argv, **kwargs):
        seen.append((argv[0], kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(github.subprocess, "run", record)
    github.gh("pr", "view", "12", root=tmp_path)
    # Et par le constructeur, qui est la facon dont la revue et le round le
    # construisent : la racine est celle du workspace, pas un global.
    github.GitHub(tmp_path).pr("12", "number")
    assert seen == [("gh", str(tmp_path)), ("gh", str(tmp_path))]


def test_the_crash_log_is_named_after_the_pr_not_after_a_flag_value():
    """`--level high 12` nommait le log `high.log`.

    Le hook lance la revue detachee : ce fichier mal nomme est la seule
    trace qu'un crash laisse.
    """
    assert cli_review._pr_arg(["--level", "high", "12"]) == "12"
    assert cli_review._pr_arg(["12", "--level", "high"]) == "12"
    assert cli_review._pr_arg(["--force", "13"]) == "13"
