"""Shared test fixtures — a fake `claude_agent_sdk`, and a fake GitHub.

`sdk.run_query` imports the SDK lazily, inside the function, so a test can put
a stand-in in `sys.modules` and exercise the real message loop: the options it
builds, every message it feeds to `progress`, and which `ResultMessage` it
keeps. Nothing here talks to Claude, and nothing here costs anything.

The message shapes live in `sdk_shapes`, shared with `test_progress`, which
feeds the same classes straight to `Progress`. The issue store lives in
`fake_github`, and the `hub` fixture below plugs it in where the round, the
loop, the preconditions, the review and `--status` all look for `gh` — one
seam, because `workflows.common.utils.hub` is the one place any of them
builds a client.
"""

import pathlib
import sys
import types
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

ORACLE = pathlib.Path(__file__).parent / "oracle"

# Re-exported: the test modules import the shapes from here.
from sdk_shapes import (  # noqa: E402,F401
    AssistantMessage, ClaudeAgentOptions, ResultMessage, StreamEvent,
    SystemMessage, TaskStartedMessage, TextBlock, ThinkingBlock,
    ToolResultBlock, ToolUseBlock, UserMessage)
from fake_github import FakeGitHub  # noqa: E402,F401

from pipeline.domain import tasks as tasks_mod  # noqa: E402


class FakeSdk:
    """The stand-in module, plus what it recorded.

    `messages` is the script the fake `query()` yields, in order; set it with
    `answers()` or assign it directly. `options` and `prompts` hold what
    `run_query` asked for, and `raises` makes the stream blow up mid-way,
    which is the case that must still close the heartbeat down.
    """

    def __init__(self) -> None:
        self.messages: list = []
        self.prompts: list[str] = []
        self.options: list[ClaudeAgentOptions] = []
        self.raises: BaseException | None = None

    # -- what the test scripts ------------------------------------------
    def answers(self, *messages, **result_fields) -> ResultMessage:
        """Script `messages`, then one `ResultMessage` built from the kwargs."""
        result = ResultMessage(**result_fields)
        self.messages = [*messages, result]
        return result

    def says_nothing(self) -> None:
        """A session that ends without ever producing a result."""
        self.messages = [AssistantMessage([TextBlock("thinking it over")])]

    # -- what `run_query` calls -----------------------------------------
    def query(self, *, prompt: str, options=None, transport=None):
        self.prompts.append(prompt)
        self.options.append(options)
        fake = self

        async def stream():
            for message in list(fake.messages):
                yield message
            if fake.raises is not None:
                raise fake.raises

        return stream()

    def as_module(self) -> types.ModuleType:
        module = types.ModuleType("claude_agent_sdk")
        module.ClaudeAgentOptions = ClaudeAgentOptions
        module.ResultMessage = ResultMessage
        module.AssistantMessage = AssistantMessage
        module.UserMessage = UserMessage
        module.SystemMessage = SystemMessage
        module.query = self.query
        return module


@pytest.fixture
def fake_sdk(monkeypatch):
    """Put a fake `claude_agent_sdk` where `sdk.run_query` will import it.

    Both prior rebuilds of this package wrote a throwaway fake in a scratchpad,
    which left the one loop that drives every paid session — `async with
    progress / async for message` — with no committed test at all.
    """
    fake = FakeSdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake.as_module())
    return fake


@pytest.fixture
def hub(monkeypatch):
    """GitHub on paper, wired where every reader of the board will find it.

    Injected rather than monkeypatched call by call: `GitHub(run=...)` exists
    for exactly this, and going through the real adapter means these tests
    exercise the API paths it builds, not a mock of them.
    """
    from pipeline.adapters.shell import github
    from pipeline.workflows.common.utils import hub as adapters

    fake = FakeGitHub()
    monkeypatch.setattr(adapters, "github",
                        lambda root: github.GitHub(root, run=fake))
    return fake


def milestone(fake, *, ready=(), tasks=("Une task",), title="Le milestone",
              body="Le corps du milestone"):
    """Un milestone et ses tasks, la forme que la plupart des tests veulent.

    Rend `(numero du milestone, numeros des tasks)`. Les tasks sont chainees
    comme la migration les chaine — chacune bloquee par la precedente — parce
    que c'est la forme sur laquelle la boucle tournera vraiment.
    """
    number = fake.add(title, tasks_mod.MILESTONE, body=body)
    numbers = []
    previous = None
    for n, name in enumerate(tasks):
        labels = [tasks_mod.AGENT]
        if n in ready or name in ready:
            labels.append(tasks_mod.READY)
        issue = fake.add(name, *labels, body=f"le SPEC de {name}")
        fake.link(number, issue)
        if previous is not None:
            fake.block(issue, previous)
        numbers.append(issue)
        previous = issue
    return number, numbers
