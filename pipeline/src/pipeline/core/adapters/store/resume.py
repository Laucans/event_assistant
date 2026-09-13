"""Ou en est la boucle, et comment elle reprend.

Deux magasins, et c'est deliberе :

- `.llocal/agent-loop/state`, un pointeur de deux lignes (`task=`, `flow_id=`)
  qui reste lisible au `cat` et effacable a la main ;
- `.llocal/agent-loop/flow_states.db`, qui porte l'etat complet du round et
  rend la reprise possible.

Le pointeur existe parce qu'un etat de boucle que personne ne peut lire est
un etat que personne ne debogue : deux lignes, lisibles au `cat`, effacables
a la main.

Le schema du second etait celui du `@persist` d'un moteur de graphe : il
l'ecrivait, ce module le relisait en sqlite3 standard parce que `--status` ne
pouvait pas payer 1,6 s d'import pour imprimer deux lignes. Un schema connu
de deux cotes dont un seul etait a nous. Les deux bouts sont ici desormais —
`save` ecrit, `load` et `stages_done` relisent — et les colonnes sont restees
les memes, donc un magasin ecrit par l'ancien moteur se relit sans rien
migrer.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline.core.domain.outcomes.result import Result


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


# Le schema, tel que le `@persist` du moteur l'ecrivait. Garde a l'identique :
# une boucle interrompue avant ce changement doit pouvoir etre reprise apres.
_SCHEMA = """CREATE TABLE IF NOT EXISTS flow_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_uuid TEXT NOT NULL,
    method_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    state_json TEXT NOT NULL
)"""


def save(flow_id: str, step: str, state: dict, db: Path) -> None:
    """L'etat du round apres une etape, ajoute au magasin.

    Une ligne par etape plutot qu'une mise a jour : `stages_done` lit la
    derniere ligne du flow, et garder les precedentes rend une reprise ratee
    lisible apres coup. Le magasin est efface avec la task, pas au fil de
    l'eau.
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(_SCHEMA)
            conn.execute(
                "INSERT INTO flow_states"
                " (flow_uuid, method_name, timestamp, state_json)"
                " VALUES (?, ?, ?, ?)",
                (flow_id, step, datetime.now(timezone.utc).isoformat(),
                 json.dumps(state)))


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


def load(flow_id: str, db: Path) -> Result[dict]:
    """L'etat le plus recent de ce flow, ou `{}`.

    Une ligne par etape, donc la derniere ligne du flow porte l'etat le plus
    recent. Rend un `Result` illisible quand le magasin existe mais ne se lit
    pas : un magasin absent, un flow inconnu et un id vide veulent tous dire
    la meme chose, inoffensive — rien n'a encore tourne — et rendent `{}`.
    """
    if not flow_id or not db.exists():
        return Result.of({})
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
        return Result.of({})
    try:
        return Result.of(dict(json.loads(row[0])))
    except (ValueError, AttributeError, TypeError) as exc:
        return _unreadable(db, exc)


def stages_done(flow_id: str, db: Path) -> Result[list[str]]:
    """Les stages deja finis pour ce flow, relus dans le magasin.

    Ce que `--status` imprime, et ce que la boucle lit pour ne pas repayer un
    stage. Un magasin illisible n'est pas « rien n'a tourne » : les deux
    reponses valent une session de `/code` d'ecart, et `load` le dit.
    """
    return load(flow_id, db).map(
        lambda state: list(state.get("stages_done") or []))
