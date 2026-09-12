"""La boucle par laquelle passe chaque session payante.

`ClaudeSdkRunner.run` est ce qu'appellent `session.run` et les deux passes de
revue. Son corps — construire les options, ouvrir `progress`, nourrir chaque
message au vol, garder le dernier `ResultMessage`, puis le traduire en
`AgentResult` — n'avait aucun test commite : le faux SDK qu'il faut a vecu
deux fois dans un scratchpad et a ete jete deux fois. Il est dans
`conftest.py` maintenant.

La traduction est testee ici aussi : c'est elle qui fait que le reste du
paquet ne connait plus un seul nom de champ d'Anthropic.
"""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import (AssistantMessage, SystemMessage, TextBlock,
                      ToolResultBlock, ToolUseBlock, UserMessage)

from pipeline.adapters.agent import AgentResult, progress
from pipeline.adapters.agent.claude_sdk import ClaudeSdkRunner
from pipeline.adapters.store import envelope
from pipeline.runtime.filesystem.workspace import Workspace


def run(prompt="fais quelque chose", *, model="opus", effort="high",
        permission_mode="bypassPermissions", watch=None, workspace=None):
    runner = ClaudeSdkRunner(workspace or Workspace(Path("/un/depot")))
    return asyncio.run(runner.run(prompt, model=model, effort=effort,
                                  permission_mode=permission_mode,
                                  progress=watch))


def test_the_last_result_message_is_translated_and_comes_back(fake_sdk):
    """Ce qui sort n'est plus un type du SDK, mais il en porte tout."""
    sent = fake_sdk.answers(
        AssistantMessage([TextBlock("j'y vais")]),
        result="AGENT_LOOP_OK: fini")
    got = run()
    assert isinstance(got, AgentResult)
    assert got.text == "AGENT_LOOP_OK: fini"
    assert (got.cost_usd, got.turns, got.session_id) == (
        sent.total_cost_usd, sent.num_turns, sent.session_id)
    assert got.failure is None


def test_the_translation_strips_the_answer_and_never_yields_none_usage(fake_sdk):
    """Les deux formes que chaque appelant refaisait a la main."""
    fake_sdk.answers(result="  AGENT_LOOP_OK: fini  \n", usage=None)
    got = run()
    assert got.text == "AGENT_LOOP_OK: fini"
    assert got.usage == {}


def test_the_raw_fields_survive_the_translation_flat(fake_sdk):
    """L'enveloppe relit `raw` : elle doit y trouver ce que l'interface tait.

    Copie plate et non `asdict()` — la conversion profonde changerait le JSON
    que des tests oracle lisent au bit pres.
    """
    fake_sdk.answers(result="fini")
    raw = run().raw
    assert raw["terminal_reason"] is None and raw["uuid"] == "u"
    assert raw["result"] == "fini"


def test_a_session_that_never_answers_returns_none(fake_sdk):
    """`None` is what `session.run` turns into StageFailed — not a crash."""
    fake_sdk.says_nothing()
    assert run() is None


def test_every_message_reaches_the_progress_census(fake_sdk, tmp_path):
    fake_sdk.answers(
        AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a.ts"})]),
        UserMessage([ToolResultBlock("1", "du texte")]),
        AssistantMessage([ToolUseBlock("2", "Bash", {"command": "npm test"}),
                          ToolUseBlock("3", "Read", {"file_path": "b.ts"})]),
        UserMessage([ToolResultBlock("2", "erreur", is_error=True)]),
        SystemMessage("init"))
    watch = progress.Progress(trace=tmp_path / "t.log", heartbeat_s=0)
    run(watch=watch)
    assert watch.tool_calls == 3
    assert watch.tool_errors == 1
    assert watch.by_tool == {"Read": 2, "Bash": 1}
    assert watch.census() == "tools: Read×2 Bash×1 — 3 call(s), 1 error(s)"
    # ... and the trace on disk carries the same run, one line per event.
    written = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "npm test" in written and "tool-error" in written


def test_the_options_carry_the_model_the_effort_and_the_repo(fake_sdk, tmp_path):
    run(model="sonnet", effort="low", permission_mode="acceptEdits",
        workspace=Workspace(tmp_path))
    options = fake_sdk.options[-1]
    assert (options.model, options.effort) == ("sonnet", "low")
    assert options.permission_mode == "acceptEdits"
    # Explicit rather than implicit: this is what loads the repo's hooks,
    # agents, skills and permissions.
    assert options.setting_sources == ["user", "project", "local"]
    # La session travaille dans le workspace qu'on lui a donne, pas dans une
    # racine que l'adaptateur serait alle chercher tout seul.
    assert options.cwd == str(tmp_path)


def test_the_prompt_is_passed_through_untouched(fake_sdk):
    fake_sdk.answers()
    run("/code-review medium 12 --comment")
    assert fake_sdk.prompts == ["/code-review medium 12 --comment"]


def test_the_heartbeat_is_stopped_even_when_the_stream_raises(fake_sdk):
    """A session that dies must not leave a pulse task behind."""
    fake_sdk.answers(AssistantMessage([TextBlock("puis rien")]))
    fake_sdk.raises = RuntimeError("le transport a laché")
    watch = progress.Progress(heartbeat_s=10)
    with pytest.raises(RuntimeError, match="le transport"):
        run(watch=watch)
    assert watch._beat is None


def test_no_progress_means_a_census_nobody_reads(fake_sdk):
    """The default path must not need a logger, a trace or a timer."""
    fake_sdk.answers(AssistantMessage([ToolUseBlock("1", "Read", {"path": "a"})]))
    assert run() is not None


# --- what the callers do with that result -----------------------------------

def test_the_envelope_keeps_the_named_fields(fake_sdk, tmp_path):
    fake_sdk.answers(total_cost_usd=0.5, session_id="abc")
    out = tmp_path / "deep" / "01-code.json"
    envelope.write(out, run().raw, ("subtype", "total_cost_usd", "session_id"))
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "subtype": "success", "total_cost_usd": 0.5, "session_id": "abc"}


def test_the_envelope_writes_null_for_a_field_the_provider_lacks(tmp_path):
    """Une trace ne doit jamais etre ce qui arrete un run qui marche."""
    out = tmp_path / "01-code.json"
    envelope.write(out, {"subtype": "success"}, ("subtype", "inconnu"))
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "subtype": "success", "inconnu": None}


def test_the_shared_ledger_columns_are_read_off_the_result(fake_sdk):
    fake_sdk.answers(num_turns=7, duration_ms=1234, session_id="s9")
    assert run().ledger_fields(model="opus", effort="high") == {
        "cost": 0.9814, "turns": 7, "duration_ms": 1234,
        "tokens_in": 11_000, "tokens_out": 12_400,
        "session": "s9", "ran_on": "opus/high"}


def test_a_result_with_no_usage_still_fills_the_columns(fake_sdk):
    fake_sdk.answers(usage=None, total_cost_usd=None)
    fields = run().ledger_fields(model="haiku", effort="low")
    assert fields["tokens_in"] is None and fields["cost"] is None
