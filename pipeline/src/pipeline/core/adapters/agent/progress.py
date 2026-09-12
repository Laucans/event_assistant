"""What a session is doing while it is doing it.

The SDK streams a message per assistant turn, per tool call and per tool
result. The loop used to drain that stream and keep only the final
`ResultMessage`, which is why `/business-analyst` could run eight minutes and
thirty-two seconds and emit exactly two lines: for those eight minutes the
loop was indistinguishable from hung.

The same stream, kept, answers both questions a human has:

- *what is it doing right now* — a heartbeat on the terminal, on a timer
  rather than on message arrival, so a stage stuck inside one long tool call
  still says so;
- *what did it actually do* — a full trace on disk next to the stage's
  `<step>-<skill>.log`, plus a one-line tool census when the stage ends.

The split matters: a wall of every tool call on the terminal would drown the
journal this exists to make readable. The terminal gets the heartbeat and the
census, the file gets everything, and `--verbose` moves the file's detail onto
the terminal too.

Messages are classified by class name rather than by importing the SDK. That
keeps this module standard-library only, lets it survive the SDK adding a
message type, and lets its tests run without the SDK installed.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pipeline.core.runtime.monitoring import metrics
from pipeline.core.runtime.monitoring.logbook import Logbook, null

# How much of a tool's input or a tool's output reaches the trace. Page text a
# stage scraped, a 4000-line file it read, a diff it generated: all of it flows
# through this stream, and none of it belongs in a journal meant to be read.
CLIP = 160

# The tool argument worth showing, per tool — the one that says *which* Read,
# *which* Bash. Anything not named here falls back to the first short string.
_IDENTIFYING = ("file_path", "command", "pattern", "path", "url", "query",
                "prompt", "description", "notebook_path", "skill")

# Messages that carry a subagent's progress rather than the main thread's.
_TASK_KINDS = ("TaskStartedMessage", "TaskProgressMessage",
               "TaskNotificationMessage", "TaskUpdatedMessage")


def _clip(text: object, limit: int = CLIP) -> str:
    """One line, bounded — a trace entry, never a transcript."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _identify(payload: object) -> str:
    """The one argument that says which call this was."""
    if not isinstance(payload, dict):
        return ""
    for key in _IDENTIFYING:
        if payload.get(key):
            return _clip(payload[key], 100)
    for value in payload.values():
        if isinstance(value, str) and value:
            return _clip(value, 100)
    return ""


def _result_text(content: object) -> str:
    """A tool result's content, whichever of the two shapes it arrived in."""
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict)]
        return _clip(" ".join(parts))
    return _clip(content)


class Progress:
    """The running census of one session, and where it gets reported."""

    def __init__(self, log: Logbook | None = None, *, trace: Path | None = None,
                 heartbeat_s: float = 60.0, verbose: bool = False,
                 clock=time.monotonic) -> None:
        self.log = log if log is not None else null()
        self.trace = trace
        self.heartbeat_s = heartbeat_s
        self.verbose = verbose
        self._clock = clock
        self.started = clock()

        self.turns = 0
        self.tool_calls = 0
        self.tool_errors = 0
        self.thinking = 0
        self.messages = 0
        self.subagents = 0
        self.last_tool: str | None = None
        self.by_tool: dict[str, int] = {}
        self._beat: asyncio.Task | None = None

    # -- the stream ------------------------------------------------------

    def feed(self, message: object) -> None:
        """Take one SDK message into the census, and into the trace."""
        self.messages += 1
        kind = type(message).__name__
        if kind == "AssistantMessage":
            self.turns += 1
            self._blocks(getattr(message, "content", None))
        elif kind == "UserMessage":
            # Tool results come back on the user side of the conversation.
            self._blocks(getattr(message, "content", None))
        elif kind == "SystemMessage":
            self._write("system", getattr(message, "subtype", "?"))
        elif kind in _TASK_KINDS:
            self._task(kind, message)
        elif kind == "ResultMessage":
            self._write("result", getattr(message, "subtype", "?"))
        # StreamEvent and anything unknown are counted, not traced: partial
        # token deltas would bury the trace under the text they build up to.

    def _blocks(self, content: object) -> None:
        if not isinstance(content, list):
            return
        for block in content:
            self._block(block)

    def _block(self, block: object) -> None:
        kind = type(block).__name__
        if kind in ("ToolUseBlock", "ServerToolUseBlock"):
            name = str(getattr(block, "name", "?"))
            self.tool_calls += 1
            self.last_tool = name
            self.by_tool[name] = self.by_tool.get(name, 0) + 1
            detail = _identify(getattr(block, "input", None))
            self._write("tool", f"{name} {detail}" if detail else name)
            if self.verbose:
                self.log.debug(f"→ {name} {detail}")
        elif kind in ("ToolResultBlock", "ServerToolResultBlock"):
            text = _result_text(getattr(block, "content", None))
            if getattr(block, "is_error", False):
                self.tool_errors += 1
                self._write("tool-error", text)
                # A failing tool is the thing a post-mortem looks for first,
                # so it is the one trace entry the terminal also gets.
                self.log.debug(f"tool error — {text}")
            else:
                self._write("tool-ok", text)
        elif kind == "ThinkingBlock":
            self.thinking += 1
            length = len(getattr(block, "thinking", "") or "")
            self._write("thinking", f"{length} chars")
        elif kind == "TextBlock":
            self._write("say", _clip(getattr(block, "text", "")))

    def _task(self, kind: str, message: object) -> None:
        if kind == "TaskStartedMessage":
            self.subagents += 1
        detail = _clip(getattr(message, "description", "")
                       or getattr(message, "summary", ""))
        status = getattr(message, "status", None) or getattr(
            message, "last_tool_name", None)
        self._write("subagent", f"{status} {detail}" if status else detail)

    # -- where it goes ---------------------------------------------------

    def _write(self, kind: str, detail: object) -> None:
        """Append one line to the per-stage trace.

        Opened and closed per line on purpose: the trace of a run that dies
        mid-stage is exactly the trace worth having, and a few hundred appends
        over several minutes cost nothing.
        """
        if self.trace is None:
            return
        try:
            self.trace.parent.mkdir(parents=True, exist_ok=True)
            with self.trace.open("a", encoding="utf-8") as fh:
                stamp = "+" + metrics.duration(self.elapsed_ms)
                fh.write(f"{stamp:>8}  {kind:<11} {_clip(detail)}\n")
        except OSError:
            # A trace that cannot be written must never be what ends a run
            # that is otherwise working.
            self.trace = None

    @property
    def elapsed_ms(self) -> float:
        return (self._clock() - self.started) * 1000

    def heartbeat(self) -> str:
        """`still running — 8m32s, 41 turns, 187 tool calls, last: Bash`."""
        parts = [f"still running — {metrics.duration(self.elapsed_ms)}",
                 f"{self.turns} turn(s)",
                 f"{self.tool_calls} tool call(s)"]
        if self.subagents:
            parts.append(f"{self.subagents} subagent(s)")
        if self.tool_errors:
            parts.append(f"{self.tool_errors} tool error(s)")
        if self.last_tool:
            parts.append(f"last: {self.last_tool}")
        return ", ".join(parts)

    def census(self, top: int = 6) -> str:
        """What the stage actually did, in one line, once it is over."""
        if not self.tool_calls:
            return f"tools: none — {self.turns} turn(s)"
        ranked = sorted(self.by_tool.items(), key=lambda kv: (-kv[1], kv[0]))
        shown = " ".join(f"{name}×{n}" for name, n in ranked[:top])
        if len(ranked) > top:
            shown += f" +{len(ranked) - top} more"
        tail = f"{self.tool_calls} call(s)"
        if self.tool_errors:
            tail += f", {self.tool_errors} error(s)"
        if self.subagents:
            tail += f", {self.subagents} subagent(s)"
        if self.thinking:
            # Compte a chaque `ThinkingBlock` depuis toujours, et jamais
            # remonte nulle part : c'est pourtant ce qui separe un stage qui
            # a reflechi d'un stage qui a seulement enchaine des outils.
            tail += f", {self.thinking} thinking"
        return f"tools: {shown} — {tail}"

    # -- the timer -------------------------------------------------------

    async def _pulse(self) -> None:
        """Le battement, jusqu'a ce que la session finisse ou qu'il echoue.

        Meme principe que `_write` pour la trace : ce qui observe un run ne
        doit jamais etre ce qui l'arrete. Un disque plein pendant un stage
        faisait mourir cette tache avec son exception, et `__aexit__` la
        relevait — un stage deja facture perdait son resultat, sa ligne de
        registre et son enveloppe, et le run sortait en CRASH.

        Le battement se tait alors plutot que de reessayer chaque minute sur
        une cause qui ne va pas se resoudre.
        """
        while True:
            await asyncio.sleep(self.heartbeat_s)
            try:
                self.log.info(self.heartbeat())
            except Exception:
                return

    async def __aenter__(self) -> "Progress":
        self.started = self._clock()
        if self.heartbeat_s > 0:
            self._beat = asyncio.create_task(self._pulse())
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._beat is not None:
            self._beat.cancel()
            try:
                await self._beat
            except asyncio.CancelledError:
                pass
            except Exception:
                # Ceinture et bretelles : `_pulse` avale deja ce qu'il peut,
                # mais `cancel()` ne fait rien sur une tache deja finie, et
                # `await` releverait alors ce qui l'a tuee — par-dessus le
                # resultat de la session, qui est ce qui compte ici.
                pass
            self._beat = None


def silent() -> Progress:
    """A census nobody reads — what `run_query` uses when given no progress."""
    return Progress(null(), trace=None, heartbeat_s=0)
