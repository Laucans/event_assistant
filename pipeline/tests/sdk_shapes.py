"""The message shapes the Claude SDK streams, mirrored for the tests.

Field names were checked against the installed `claude_agent_sdk`. `progress`
classifies messages by class *name*, never by importing the SDK, so these
stand-ins are what it sees in production too — which is the whole reason it
can stay standard-library-only and testable without the SDK installed.

One definition, imported by `conftest` (which builds the fake module around
them) and by `test_progress` (which feeds them to `Progress` directly).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str


@dataclass
class ThinkingBlock:
    thinking: str
    signature: str = ""


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


@dataclass
class AssistantMessage:
    content: list
    model: str = "opus"


@dataclass
class UserMessage:
    content: Any


@dataclass
class SystemMessage:
    subtype: str
    data: dict = field(default_factory=dict)


@dataclass
class TaskStartedMessage:
    description: str = "explore the schema"
    subtype: str = "task_started"
    task_id: str = "t1"


@dataclass
class StreamEvent:
    uuid: str = "u"
    session_id: str = "s"
    event: dict = field(default_factory=dict)


@dataclass
class ResultMessage:
    """What a session answers with — the one message `run_query` keeps."""

    subtype: str = "success"
    duration_ms: float = 433_000
    duration_api_ms: float = 400_000
    is_error: bool = False
    num_turns: int = 34
    session_id: str = "sess-1"
    stop_reason: str | None = None
    total_cost_usd: float | None = 0.9814
    usage: dict | None = field(default_factory=lambda: {
        "input_tokens": 11_000,
        "cache_read_input_tokens": 117_000,
        "cache_creation_input_tokens": 4_000,
        "output_tokens": 12_400,
    })
    result: str | None = "AGENT_LOOP_OK: done"
    errors: list = field(default_factory=list)
    api_error_status: int | None = None
    uuid: str = "u"
    terminal_reason: str | None = None


@dataclass
class ClaudeAgentOptions:
    """Only the fields `sdk.run_query` sets — a test asserts on these."""

    model: str = ""
    effort: str = ""
    permission_mode: str = ""
    setting_sources: list | None = None
    cwd: str = ""
