"""The progress stream: what used to make a stage indistinguishable from hung.

`/business-analyst` ran for 8m32s and produced two lines of journal. The SDK
was emitting a message per turn, per tool call and per tool result the whole
time; `run_query` threw all of them away but the last.

These tests import no SDK: `progress` classifies messages by class *name*,
precisely so it stays standard-library-only and testable without it. The
shapes come from `sdk_shapes`, shared with `conftest`.
"""

import asyncio
import logging

import pytest

from sdk_shapes import (
    AssistantMessage, StreamEvent, SystemMessage, TaskStartedMessage,
    TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, UserMessage)

from pipeline.core.runtime.monitoring import logbook
from pipeline.core.adapters.agent import progress


def test_tool_calls_are_counted_and_named(tmp_path):
    p = progress.Progress(logbook.null(), trace=tmp_path / "t.log", heartbeat_s=0)
    p.feed(AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a.ts"})]))
    p.feed(AssistantMessage([ToolUseBlock("2", "Read", {"file_path": "b.ts"}),
                             ToolUseBlock("3", "Bash", {"command": "npm test"})]))
    assert p.turns == 2
    assert p.tool_calls == 3
    assert p.by_tool == {"Read": 2, "Bash": 1}
    assert p.last_tool == "Bash"


def test_a_failing_tool_is_counted_separately(tmp_path):
    p = progress.Progress(logbook.null(), trace=tmp_path / "t.log", heartbeat_s=0)
    p.feed(UserMessage([ToolResultBlock("1", "no matches", is_error=True)]))
    p.feed(UserMessage([ToolResultBlock("2", "ok")]))
    assert p.tool_errors == 1
    assert "tool-error" in (tmp_path / "t.log").read_text(encoding="utf-8")


def test_the_census_ranks_the_tools_the_stage_actually_used():
    p = progress.Progress(logbook.null(), heartbeat_s=0)
    for _ in range(6):
        p.feed(AssistantMessage([ToolUseBlock("x", "Bash", {"command": "ls"})]))
    for _ in range(2):
        p.feed(AssistantMessage([ToolUseBlock("x", "Read", {"file_path": "a"})]))
    assert p.census() == "tools: Bash×6 Read×2 — 8 call(s)"


def test_a_census_with_no_tool_call_says_so():
    p = progress.Progress(logbook.null(), heartbeat_s=0)
    p.feed(AssistantMessage([TextBlock("juste une reponse")]))
    assert p.census() == "tools: none — 1 turn(s)"


def test_the_heartbeat_names_elapsed_turns_and_the_last_tool():
    ticks = [0.0]      # le premier appel ouvre le compteur, les suivants avancent
    p = progress.Progress(logbook.null(), heartbeat_s=0,
                          clock=lambda: ticks.pop(0) if ticks else 512.0)
    p.feed(AssistantMessage([ToolUseBlock("1", "Bash", {"command": "ls"})]))
    assert p.heartbeat() == ("still running — 8m32s, 1 turn(s), "
                             "1 tool call(s), last: Bash")


def test_page_text_is_clipped_before_it_reaches_the_trace(tmp_path):
    """A 40kB tool result would drown the journal it exists to make legible."""
    trace = tmp_path / "t.log"
    p = progress.Progress(logbook.null(), trace=trace, heartbeat_s=0)
    p.feed(UserMessage([ToolResultBlock("1", "x" * 40_000)]))
    line = trace.read_text(encoding="utf-8").splitlines()[0]
    assert len(line) < 200
    assert line.endswith("…")


def test_an_unknown_message_type_is_counted_and_never_raises():
    """The SDK will add message types; none of them may bring a run down."""
    p = progress.Progress(logbook.null(), heartbeat_s=0)
    p.feed(StreamEvent())
    p.feed(object())
    assert p.messages == 2 and p.tool_calls == 0


def test_subagents_and_thinking_are_visible(tmp_path):
    trace = tmp_path / "t.log"
    p = progress.Progress(logbook.null(), trace=trace, heartbeat_s=0)
    p.feed(TaskStartedMessage())
    p.feed(AssistantMessage([ThinkingBlock("hmm" * 100)]))
    p.feed(SystemMessage("init"))
    written = trace.read_text(encoding="utf-8")
    assert p.subagents == 1 and p.thinking == 1
    assert "explore the schema" in written and "300 chars" in written


def test_an_unwritable_trace_never_ends_the_run(tmp_path):
    """The journal must never be what brings down a run that works."""
    p = progress.Progress(logbook.null(), trace=tmp_path / "nope" / "t.log",
                          heartbeat_s=0)
    (tmp_path / "nope").write_text("un fichier, pas un repertoire", encoding="utf-8")
    p.feed(AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a"})]))
    assert p.trace is None
    assert p.tool_calls == 1


def test_the_heartbeat_fires_on_a_timer_not_on_message_arrival(tmp_path):
    """A stage stuck inside one single tool call must still report in."""
    seen = []

    async def go():
        p = progress.Progress(logbook.null(), heartbeat_s=0.01)
        p.log = type("L", (), {"info": lambda _s, *a: seen.append(a),
                               "debug": lambda _s, *a: None})()
        async with p:
            await asyncio.sleep(0.05)   # aucun message ne passe

    asyncio.run(go())
    assert seen, "aucun battement pendant une attente silencieuse"


def test_the_heartbeat_task_is_cancelled_on_exit():
    async def go():
        p = progress.Progress(logbook.null(), heartbeat_s=10)
        async with p:
            task = p._beat
        return task

    task = asyncio.run(go())
    assert task is not None and task.cancelled()


def test_silent_progress_writes_nothing(capsys):
    p = progress.silent()
    p.feed(AssistantMessage([ToolUseBlock("1", "Read", {"file_path": "a"})]))
    assert p.trace is None and p.heartbeat_s == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("payload, expected", [
    ({"file_path": "src/app/page.tsx"}, "src/app/page.tsx"),
    ({"command": "npm run test"}, "npm run test"),
    ({"pattern": "createClient"}, "createClient"),
    ({"autre": "valeur"}, "valeur"),
    ({}, ""),
    (None, ""),
])
def test_the_identifying_argument_is_the_one_shown(payload, expected):
    assert progress._identify(payload) == expected


def test_a_heartbeat_that_cannot_write_does_not_lose_the_session(monkeypatch):
    """Le disque se remplit pendant un stage : le stage est quand meme fini.

    `_pulse` levait, la tache mourait avec l'exception, et `__aexit__` la
    relevait — un stage deja facture perdait son resultat, sa ligne de
    registre et son enveloppe, et sortait en CRASH. Meme principe que la
    trace : ce qui observe un run ne doit jamais etre ce qui l'arrete.
    """
    class Deaf(logbook.Logbook):
        def info(self, *parts):
            raise OSError("no space left on device")

    async def one_session():
        watch = progress.Progress(Deaf(logging.getLogger("test.deaf")),
                                  heartbeat_s=0.01)
        async with watch:
            await asyncio.sleep(0.05)
        return "le stage a repondu"

    assert asyncio.run(one_session()) == "le stage a repondu"
