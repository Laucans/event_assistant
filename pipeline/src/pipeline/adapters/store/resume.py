"""Ou en est la boucle, et comment elle reprend.

Deux magasins, et c'est deliberе :

- `.llocal/agent-loop/state`, un pointeur de deux lignes (`task=`, `flow_id=`)
  qui reste lisible au `cat` et effacable a la main ;
- `.llocal/agent-loop/flow_states.db`, ecrit par le `@persist` du moteur, qui
  porte l'etat complet du round et rend la reprise possible.

Le pointeur existe parce que `--status` doit repondre sans importer le moteur
(2,5 s d'import pour imprimer deux lignes), et parce qu'un etat de boucle que
personne ne peut lire est un etat que personne ne debogue.

La lecture des stages deja faits passe par le sqlite3 de la bibliotheque
standard, pour la meme raison. Le schema est donc connu de deux cotes : le
moteur l'ecrit, ce module le relit. C'est le prix a payer pour que le chemin
rapide reste rapide, et c'est le seul endroit ou ce couplage existe.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path

from pipeline.domain.outcomes.result import Result


def read_pointer(state: Path) -> tuple[str | None, str | None]:
    """`(task_key, flow_id)`, or `(None, None)` when there is no resume point."""
    if not state.exists():
        return None, None
    task = flow_id = None
    for line in state.read_text(encoding="utf-8").splitlines():
        if line.startswith("task="):
            task = line[5:]
        elif line.startswith("flow_id="):
            flow_id = line[8:]
    return task, flow_id


def write_pointer(task_key: str, flow_id: str, state: Path) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(f"task={task_key}\nflow_id={flow_id}\n", encoding="utf-8")


def clear(state: Path) -> None:
    """The task is closed: the resume point has nothing left to describe."""
    state.unlink(missing_ok=True)


def _unreadable(path: Path, exc: Exception) -> Result[list[str]]:
    """The one degraded read in this package that costs money if it is quiet.

    A row this function cannot decode is not "nothing has run yet": it is "I
    cannot tell", and the two answers are worth a `/code` stage apart. Say so,
    name the file, and name the two ways out.
    """
    return Result.unreadable(
        f"cannot read the resume state in {path}"
        f" ({type(exc).__name__}: {exc}) — which stages already ran is unknown,"
        f" and treating that as 'nothing ran' would re-pay for a stage that"
        f" already merged. Inspect or delete the file, or re-run with --restart"
        f" to replay this task from the top.")


def stages_done(flow_id: str, db: Path) -> Result[list[str]]:
    """The stages already finished, read from `@persist`'s store.

    The engine's schema is `flow_states(flow_uuid, method_name, timestamp,
    state_json)`: one row per persisted method, so the flow's last row carries
    the most recent state.

    Rend un `Result` illisible quand le magasin existe mais ne se lit pas. Un
    magasin absent, un flow inconnu et un id vide veulent tous dire la meme
    chose, inoffensive — rien n'a encore tourne — et rendent `[]`.
    """
    if not flow_id or not db.exists():
        return Result.of([])
    try:
        # `with sqlite3.connect(...)` manages the transaction, not the
        # connection: it left one open per call. Read-only, so there is no
        # transaction to manage — `closing` is what this needed all along.
        with contextlib.closing(
                sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
            row = conn.execute(
                "SELECT state_json FROM flow_states WHERE flow_uuid = ?"
                " ORDER BY id DESC LIMIT 1", (flow_id,)).fetchone()
    except sqlite3.Error as exc:
        return _unreadable(db, exc)
    if not row:
        return Result.of([])
    try:
        return Result.of(list(json.loads(row[0]).get("stages_done") or []))
    except (ValueError, AttributeError, TypeError) as exc:
        return _unreadable(db, exc)
