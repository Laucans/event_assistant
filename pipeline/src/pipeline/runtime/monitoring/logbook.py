"""One logging system for the package: levels, a date, and who is speaking.

An unattended loop is judged on the file it leaves behind. Three things were
missing from every line it wrote, and all three only hurt later, when the
terminal is gone:

- a **level**, so a warning does not read like an ordinary step;
- a **date**, because `%H:%M:%S` alone is ambiguous the moment a run crosses
  midnight or the log is read a week later;
- a **context**, because a detached `pr-review` writes to the same terminal
  and an unattributed line cannot be traced back to what produced it.

The context is bound, not passed: `log.bind("r1")` returns a logbook that
stamps every line with the round, and binding again adds the stage. Callers
keep writing `log("...")` — a `Logbook` is callable, and calling it means
INFO, which is what every existing call site meant.

Standard library only: this module sits under `--status` and `--costs`, which
answer without importing crewai or the SDK.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# The level a run is written at, by name — what `--verbose` and `--quiet` pick.
VERBOSE = logging.DEBUG
NORMAL = logging.INFO
QUIET = logging.WARNING

# `WARNING` is seven characters and would push every message right; the point
# of the column is to be scanned, not to be exhaustive.
_SHORT = {"WARNING": "WARN", "CRITICAL": "CRIT"}


class _Format(logging.Formatter):
    """`2026-09-10 09:00:01  INFO  [20260910-090000 r1 code]  message`."""

    default_time_format = "%Y-%m-%d %H:%M:%S"
    default_msec_format = ""

    def format(self, record: logging.LogRecord) -> str:
        level = _SHORT.get(record.levelname, record.levelname)
        ctx = getattr(record, "pipeline_ctx", "")
        stamp = f"[{ctx}]  " if ctx else ""
        line = f"{self.formatTime(record)}  {level:<5}  {stamp}{record.getMessage()}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class Logbook:
    """A logger plus the context its lines are stamped with.

    Callable so that the hundreds of existing `log("...")` call sites keep
    working unchanged; `*parts` are joined with a space, as the closure this
    replaces did.
    """

    def __init__(self, logger: logging.Logger, ctx: tuple[str, ...] = ()) -> None:
        self._logger = logger
        self._ctx = ctx

    def bind(self, *parts: object) -> "Logbook":
        """A logbook that stamps these extra context words on every line."""
        extra = tuple(str(p) for p in parts if p not in (None, ""))
        return Logbook(self._logger, self._ctx + extra)

    @property
    def context(self) -> str:
        return " ".join(self._ctx)

    def _emit(self, level: int, parts: tuple[object, ...],
              exc_info: bool = False) -> None:
        if not self._logger.isEnabledFor(level):
            return
        self._logger.log(level, " ".join(str(p) for p in parts),
                         extra={"pipeline_ctx": self.context},
                         exc_info=exc_info)

    def __call__(self, *parts: object) -> None:
        self._emit(logging.INFO, parts)

    def debug(self, *parts: object) -> None:
        self._emit(logging.DEBUG, parts)

    def info(self, *parts: object) -> None:
        self._emit(logging.INFO, parts)

    def warn(self, *parts: object) -> None:
        self._emit(logging.WARNING, parts)

    def error(self, *parts: object) -> None:
        self._emit(logging.ERROR, parts)

    def exception(self, *parts: object) -> None:
        """An error plus the traceback — the whole point of A2.

        Written through the same handlers as everything else, so the reason a
        run died lands in `run.log` instead of on a stderr nobody kept.
        """
        self._emit(logging.ERROR, parts, exc_info=True)


def open_logbook(name: str, *, file: Path | None = None, level: int = NORMAL,
                 stream=None) -> Logbook:
    """A logbook that prints and, when given a file, appends to it.

    Idempotent: calling it twice for the same name replaces the handlers
    rather than doubling every line, which is what a second call used to do
    through `logging.basicConfig`.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # A package logger that also propagated would print each line twice as
    # soon as anything configured the root logger — crewai does.
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout if stream is None else stream)
    console.setFormatter(_Format())
    logger.addHandler(console)

    if file is not None:
        file.parent.mkdir(parents=True, exist_ok=True)
        disk = logging.FileHandler(file, encoding="utf-8")
        # The file keeps everything: the terminal can be quiet for cron, and
        # the run log is still the artifact a post-mortem reads.
        disk.setLevel(logging.DEBUG)
        disk.setFormatter(_Format())
        logger.addHandler(disk)
        logger.setLevel(min(level, logging.DEBUG))
        console.setLevel(level)

    return Logbook(logger)


def null() -> Logbook:
    """A logbook that writes nowhere — for tests and for the silent paths."""
    logger = logging.getLogger("pipeline.null")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    logger.setLevel(logging.CRITICAL + 1)
    return Logbook(logger)
