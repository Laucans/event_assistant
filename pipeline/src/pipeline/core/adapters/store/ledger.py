"""Le registre de couts : une ligne par stage, ce que le run a vraiment coute.

Le format est garde caractere pour caractere depuis le shell — meme entete,
memes colonnes, meme ordre. L'historique deja accumule reste lisible.

Ce module **ecrit et relit** le registre ; il ne le met pas en forme. Les
tables que rend `--costs` vivent dans `cli.reports` : un schema qu'on fait
evoluer et une colonne qu'on aligne ne se relisent pas pour les memes
raisons.

Bibliotheque standard uniquement : `--costs` ne doit payer l'import de rien
de lourd.
"""

from __future__ import annotations

import datetime
from pathlib import Path


# Columns added after the fact were added at the end of the line: older rows
# have 12, or 14, and stay readable as they are. `outcome` is the most recent
# one — without it, money burnt by a failing stage read as money that had
# bought something.
HEADER = ("when\trun\tround\ttask\tstage\tcost_usd\tturns"
          "\tduration_ms\tin\tout\tsession\tran_on"
          "\tcache_read\tcache_write\toutcome\n")

# The header is the single source of truth for where a column sits. Rows are
# read back by position — `r[STAGE]` rather than `r[4]` — and the names below
# are derived from HEADER itself, so extending it moves them with it instead
# of leaving a hand-maintained count to drift.
COLUMNS = HEADER.rstrip("\n").split("\t")
_AT = {name: index for index, name in enumerate(COLUMNS)}

WHEN = _AT["when"]
RUN = _AT["run"]
ROUND = _AT["round"]
TASK = _AT["task"]
STAGE = _AT["stage"]
COST = _AT["cost_usd"]
TURNS = _AT["turns"]
DURATION_MS = _AT["duration_ms"]
TOKENS_IN = _AT["in"]
TOKENS_OUT = _AT["out"]
SESSION = _AT["session"]
RAN_ON = _AT["ran_on"]
CACHE_READ = _AT["cache_read"]
CACHE_WRITE = _AT["cache_write"]
OUTCOME = _AT["outcome"]


def append(ledger: Path, *, run_id: str, round_no: int, task: str, stage: str,
           cost: float | None, turns: object, duration_ms: object,
           tokens_in: object, tokens_out: object, session: object,
           ran_on: str, cache_read: object = None,
           cache_write: object = None, outcome: str = "") -> None:
    """Append a row. Writes the header first if the file does not exist yet.

    `round_no` is the loop's round number; it lands in the column the header
    calls `round`, zero-padded, which is the on-disk name and is frozen.

    `outcome` is `"ok"`, or the reason the stage did not answer (`quota`,
    `failed`, `empty`). Left empty it means "not recorded", which is what
    every row written before the column existed means.
    """
    # Keyed by column name rather than written out as one positional line: the
    # row and the header cannot drift apart, and a reader never has to count
    # tabs to learn which value is which.
    row = {
        "when": datetime.datetime.now().isoformat(timespec="seconds"),
        "run": run_id,
        "round": f"{round_no:02d}",
        "task": " ".join(task.split()),
        "stage": stage,
        "cost_usd": f"{cost or 0.0:.6f}",
        "turns": turns,
        "duration_ms": duration_ms,
        "in": tokens_in,
        "out": tokens_out,
        "session": session,
        "ran_on": ran_on,
        "cache_read": "" if cache_read is None else cache_read,
        "cache_write": "" if cache_write is None else cache_write,
        "outcome": outcome,
    }
    fresh = not ledger.exists()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        if fresh:
            fh.write(HEADER)
        fh.write("\t".join(str(row[name]) for name in COLUMNS) + "\n")


def rows(ledger: Path) -> list[list[str]]:
    """Every data row of the register, split, header dropped."""
    if not ledger.exists() or ledger.stat().st_size == 0:
        return []
    return [l.split("\t")
            for l in ledger.read_text(encoding="utf-8").splitlines()[1:] if l]


# The PR review keeps a register of its own: different columns, different
# rows, and a review's cost is not mixed into a round's.
REVIEW_HEADER = ("when\tpr\tpass\tcost_usd\tturns\tduration_ms\tin\tout"
                 "\tsession\tran_on\n")

REVIEW_COLUMNS = REVIEW_HEADER.rstrip("\n").split("\t")
_REVIEW_AT = {name: index for index, name in enumerate(REVIEW_COLUMNS)}

REVIEW_PR = _REVIEW_AT["pr"]
REVIEW_COST = _REVIEW_AT["cost_usd"]


def append_review(ledger: Path, *, pr: str, label: str, cost: float | None,
                  turns: object, duration_ms: object, tokens_in: object,
                  tokens_out: object, session: object, ran_on: str) -> None:
    row = {
        "when": datetime.datetime.now().isoformat(timespec="seconds"),
        "pr": pr,
        "pass": label,
        "cost_usd": f"{cost or 0.0:.6f}",
        "turns": turns,
        "duration_ms": duration_ms,
        "in": tokens_in,
        "out": tokens_out,
        "session": session,
        "ran_on": ran_on,
    }
    fresh = not ledger.exists()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        if fresh:
            fh.write(REVIEW_HEADER)
        fh.write("\t".join(str(row[name]) for name in REVIEW_COLUMNS) + "\n")


def review_cost(ledger: Path, pr: str) -> str:
    """What the review of this PR cost, both passes together."""
    if not ledger.exists() or ledger.stat().st_size == 0:
        return ""
    total = 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines()[1:]:
        row = line.split("\t")
        if len(row) > REVIEW_COST and row[REVIEW_PR] == pr:
            total += float(row[REVIEW_COST] or 0)
    return f"{total:.4f}"
