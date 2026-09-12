"""What a run costs, and where it spends it.

An unattended loop spends money for tens of minutes with nobody watching.
These measurements exist to answer three questions asked after the fact, which
cannot be reconstructed if they were never written down: where the time went,
where the money went, and whether the cache is working.

Standard library only — this module sits on the fast path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def duration(ms: float | None) -> str:
    """`7m13s`, `42s`, `1h04m` — read at a glance, not to the millisecond.

    `None` is the only unknown. Zero is a measurement: a stage that answered
    in under a second read as "?" — an unknown duration — which is exactly
    what a stage that never reported one reads as.
    """
    if ms is None:
        return "?"
    s = int(ms // 1000)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def tokens(n: float | None) -> str:
    """`934`, `128k`, `1.2M` — and `?` when there is no counter at all.

    Same distinction as `duration`: a missing counter is not a count of zero.
    """
    if n is None:
        return "?"
    if not n:
        return "0"
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{round(n / 1000)}k"
    return f"{n / 1_000_000:.1f}M"


def input_tokens(usage: dict | None) -> int:
    """Every token billed as input: cache reads, fresh input, cache writes.

    The three counters are separate lines in the SDK's usage because they are
    priced differently, but the answer to "how big was the input" is their
    sum — and the ratio between them is the cache metric below.
    """
    usage = usage or {}
    return ((usage.get("cache_read_input_tokens") or 0)
            + (usage.get("input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0))


def cache_ratio(usage: dict | None) -> float | None:
    """The share of the input served by the cache, or None when unknown.

    A cache read costs a fraction of the full price: a ratio that collapses is
    the first thing to look at when the bill goes up without the work
    changing.
    """
    total = input_tokens(usage)
    if not total:
        return None
    return (usage.get("cache_read_input_tokens") or 0) / total


def stage_line(skill: str, cost: float | None, duration_ms: float | None,
               turns: object, usage: dict | None) -> str:
    """The end-of-stage line: cost, time, turns, input/output, cache."""
    parts = [f"/{skill} done — ${cost or 0.0:.4f}", duration(duration_ms)]
    if turns:
        parts.append(f"{turns} turns")
    usage = usage or {}
    total_in = input_tokens(usage)
    if total_in:
        ratio = cache_ratio(usage)
        entry = f"{tokens(total_in)} in"
        if ratio is not None:
            entry += f" ({round(ratio * 100)}% cache)"
        parts.append(entry)
    out = usage.get("output_tokens")
    if out:
        parts.append(f"{tokens(out)} out")
    return " · ".join(parts)


@dataclass
class Tally:
    """A run's running total: what the loop has spent since it started.

    Two clocks, and they are not the same measurement. `duration_ms` is the
    sum of what the sessions themselves reported; `started` is when this tally
    was opened, so `elapsed_ms` is the wall time a human would read off a
    watch. The gap between them is everything that is not a session — flow
    kickoff, persistence writes, git calls, preflight — and a summary that
    reported only the first left that gap unexplained.
    """

    stages: int = 0
    cost: float = 0.0
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    by_stage: dict[str, float] = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)

    def add(self, skill: str, cost: float | None, duration_ms: float | None,
            usage: dict | None) -> None:
        usage = usage or {}
        self.stages += 1
        self.cost += cost or 0.0
        self.duration_ms += duration_ms or 0
        self.tokens_in += input_tokens(usage)
        self.tokens_out += usage.get("output_tokens") or 0
        self.cache_read += usage.get("cache_read_input_tokens") or 0
        self.by_stage[skill] = self.by_stage.get(skill, 0.0) + (cost or 0.0)

    def merge(self, other: "Tally") -> None:
        """Pour a round's running total into the run's."""
        self.stages += other.stages
        self.cost += other.cost
        self.duration_ms += other.duration_ms
        self.tokens_in += other.tokens_in
        self.tokens_out += other.tokens_out
        self.cache_read += other.cache_read
        for skill, cost in other.by_stage.items():
            self.by_stage[skill] = self.by_stage.get(skill, 0.0) + cost

    @property
    def elapsed_ms(self) -> float:
        """Real time since this tally was opened, not time spent in sessions."""
        return (time.monotonic() - self.started) * 1000

    @property
    def cache_pct(self) -> int | None:
        if not self.tokens_in:
            return None
        return round(self.cache_read / self.tokens_in * 100)

    def running(self) -> str:
        """The running total, printed after each stage: watch the bill rise."""
        return (f"running total — ${self.cost:.4f} over {self.stages} stage(s),"
                f" {duration(self.duration_ms)} (wall {duration(self.elapsed_ms)})")

    def summary(self, label: str) -> str:
        parts = [f"{label} — ${self.cost:.4f}",
                 f"{duration(self.duration_ms)} (wall {duration(self.elapsed_ms)})",
                 f"{self.stages} stage(s)"]
        if self.tokens_in:
            entry = f"{tokens(self.tokens_in)} in"
            if self.cache_pct is not None:
                entry += f" ({self.cache_pct}% cache)"
            parts.append(entry)
        if self.tokens_out:
            parts.append(f"{tokens(self.tokens_out)} out")
        if self.by_stage:
            skill, cost = max(self.by_stage.items(), key=lambda kv: kv[1])
            parts.append(f"priciest: /{skill} ${cost:.4f}")
        return " · ".join(parts)
