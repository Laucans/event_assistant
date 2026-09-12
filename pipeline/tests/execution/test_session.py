"""What decides a stage answered — the runner's subtlest logic.

`claude -p` exits 0 even on a quota message: it is the envelope that decides,
not the return code. And the quota phrase must only be read inside an already
failed run (review of 2026-09-09, finding #1).
"""

import asyncio
import io
import json

import pytest
from conftest import AssistantMessage, ToolUseBlock

from pipeline.adapters.store import resume
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.runtime.monitoring import logbook
from pipeline.execution import session
from pipeline.domain.stages.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.domain.outcomes.result import Status
from pipeline.adapters.agent import failure_reason

QUOTA_TEXT = "You've hit your session limit. Try again later."


@pytest.mark.parametrize("text", [
    "AGENT_LOOP_OK: ajout du rate limit handling sur le scraper",
    "AGENT_LOOP_OK: documente la usage limit de l'API Mistral",
    "AGENT_LOOP_OK: le test couvre le cas 'too many requests'",
])
def test_a_successful_stage_talking_about_limits_is_not_a_quota(text):
    """The bug that would have re-paid a merged /code."""
    assert failure_reason(is_error=False, subtype="success", text=text,
                          api_error_status=None) is None


def test_a_failed_run_carrying_the_quota_phrase_is_a_quota():
    assert failure_reason(is_error=True, subtype="error_during_execution",
                          text=QUOTA_TEXT, api_error_status=None) == "quota"


def test_a_429_stands_on_its_own():
    """A structured signal: it needs no phrase to be recognised."""
    assert failure_reason(is_error=False, subtype="success", text="ok",
                          api_error_status=429) == "quota"


def test_a_plain_failure_is_reported_as_such():
    assert failure_reason(is_error=True, subtype="error_max_turns", text="oups",
                          api_error_status=None) == "failed"
    assert failure_reason(is_error=False, subtype="error_during_execution",
                          text="oups", api_error_status=None) == "failed"


def test_an_empty_answer_is_not_a_success():
    assert failure_reason(is_error=False, subtype="success", text="",
                          api_error_status=None) == "empty"


def test_a_good_run_passes():
    assert failure_reason(is_error=False, subtype="success",
                          text="AGENT_LOOP_OK: fait", api_error_status=None) is None


# --- un stage entier, du prompt a la ligne de registre ---------------------

@pytest.fixture
def stage_env(tmp_path):
    """Le workspace du stage : son registre et ses artefacts y tombent."""
    return Workspace(tmp_path)


def run_stage(ws, cfg=None, *, skill="code", log=None):
    cfg = cfg or RunConfig(run_id="20260910-090000", heartbeat_s=0,
                           workspace=ws)
    stage = StageSpec(skill, "opus", "high", lead="/tech-analyst")
    return asyncio.run(session.run(stage, cfg, round_no=1, task="4|Schema",
                                   log_dir=ws.root,
                                   log=log or logbook.null()))


def test_a_stage_that_answers_leaves_every_artifact_behind(stage_env, fake_sdk):
    fake_sdk.answers(
        AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a.ts"})]),
        result="AGENT_LOOP_OK: fait")
    result = run_stage(stage_env).value

    assert result.text == "AGENT_LOOP_OK: fait"
    assert result.ok_line == "AGENT_LOOP_OK: fait" and not result.stopped
    assert result.cost == 0.9814 and result.turns == 34

    assert (stage_env.root / "01-code.log").read_text(encoding="utf-8") == (
        "AGENT_LOOP_OK: fait\n")
    envelope = json.loads(
        (stage_env.root / "01-code.json").read_text(encoding="utf-8"))
    assert envelope["session_id"] == "sess-1" and envelope["subtype"] == "success"
    assert "Read a.ts" in (stage_env.root / "01-code.trace.log").read_text(
        encoding="utf-8")

    row = stage_env.ledger.read_text(
        encoding="utf-8").splitlines()[1].split("\t")
    assert row[1] == "20260910-090000" and row[3] == "4|Schema"
    assert row[4] == "code" and row[5] == "0.981400"
    assert row[11] == "opus/high" and row[14] == "ok"


def test_the_prompt_names_the_lead_command(stage_env, fake_sdk):
    fake_sdk.answers()
    run_stage(stage_env)
    assert fake_sdk.prompts[0].startswith("/tech-analyst")


def test_a_dry_run_writes_the_prompt_and_calls_nobody(stage_env, fake_sdk):
    fake_sdk.answers()
    cfg = RunConfig(dry_run=True, run_id="r", workspace=stage_env)
    dry = run_stage(stage_env, cfg)
    assert dry.ok and dry.value is None, "un dry-run reussit sans rien rendre"
    assert "/tech-analyst" in (stage_env.root / "01-code.log").read_text(
        encoding="utf-8")
    assert fake_sdk.prompts == []
    assert not stage_env.ledger.exists()


@pytest.mark.parametrize("fields, expected", [
    ({"api_error_status": 429}, Status.QUOTA),
    ({"is_error": True, "subtype": "error_during_execution",
      "result": "You've hit your session limit."}, Status.QUOTA),
    ({"is_error": True, "subtype": "error_max_turns"}, Status.FAILED),
    ({"result": ""}, Status.FAILED),
])
def test_a_stage_that_did_not_answer_fails_and_still_books_the_money(
        stage_env, fake_sdk, fields, expected):
    """L'argent brule par un stage en echec est compte, et nomme comme tel."""
    fake_sdk.answers(**fields)
    assert run_stage(stage_env).status is expected
    row = stage_env.ledger.read_text(
        encoding="utf-8").splitlines()[1].split("\t")
    assert row[5] == "0.981400"
    assert row[14] in ("quota", "failed", "empty")


def test_a_session_that_never_answered_is_a_failure_not_a_success(stage_env,
                                                                  fake_sdk):
    fake_sdk.says_nothing()
    got = run_stage(stage_env)
    assert got.status is Status.FAILED and "returned no result" in got.reason


def test_the_tool_census_is_written_before_the_failure_is_returned(stage_env,
                                                                   fake_sdk):
    """A stage that died after forty tool calls is the one we want traced."""
    said = io.StringIO()
    log = logbook.open_logbook("test.session.census", stream=said)
    fake_sdk.answers(
        AssistantMessage([ToolUseBlock("1", "Bash", {"command": "npm test"})]),
        is_error=True, subtype="error_during_execution")
    assert run_stage(stage_env, log=log).failed
    assert "tools: Bash×1 — 1 call(s)" in said.getvalue()


def test_a_stop_marker_travels_back_as_a_result(stage_env, fake_sdk):
    """Le marqueur remonte dans la valeur : c'est `StageRunner` qui en fait
    un arret, pas `session`."""
    fake_sdk.answers(result="AGENT_LOOP_STOP: le spec est ambigu")
    got = run_stage(stage_env)
    assert got.ok
    assert got.value.stopped and got.value.stop_line.endswith("ambigu")


def test_two_workspaces_in_one_process_write_to_their_own_root(tmp_path,
                                                               fake_sdk):
    """Deux racines, deux registres, deux points de reprise — un seul process.

    Ce que la disparition du global achete : tant que la racine etait lue
    dans un module, deux runs d'un meme process ecrivaient dans le meme
    registre et se marchaient sur le point de reprise.
    """
    un, deux = Workspace(tmp_path / "un"), Workspace(tmp_path / "deux")
    un.root.mkdir()
    deux.root.mkdir()

    fake_sdk.answers(result="AGENT_LOOP_OK: fait")
    run_stage(un, RunConfig(run_id="r-un", heartbeat_s=0, workspace=un))
    fake_sdk.answers(result="AGENT_LOOP_OK: fait")
    run_stage(deux, RunConfig(run_id="r-deux", heartbeat_s=0, workspace=deux))
    resume.write_pointer("41", "flow-un", un.state)
    resume.write_pointer("42", "flow-deux", deux.state)

    def only_row(ws):
        rows = ws.ledger.read_text(encoding="utf-8").splitlines()[1:]
        assert len(rows) == 1, rows
        return rows[0].split("\t")[1]

    assert (only_row(un), only_row(deux)) == ("r-un", "r-deux")
    assert resume.read_pointer(un.state) == ("41", "flow-un")
    assert resume.read_pointer(deux.state) == ("42", "flow-deux")
