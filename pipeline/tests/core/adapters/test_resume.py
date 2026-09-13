"""The resume state: a readable pointer, stages read from CrewAI's store."""

import json
import sqlite3
from unittest import mock

import pytest

from pipeline.core.adapters.store import resume
from pipeline.launcher.cli import reports
from pipeline.core.domain.outcomes.result import Status
from pipeline.core.runtime.filesystem.workspace import Workspace


def test_pointer_round_trip(tmp_path):
    p = tmp_path / "state"
    resume.write_pointer("4|Un titre", "abc-123", p)
    assert resume.read_pointer(p) == ("4|Un titre", "abc-123")
    assert p.read_text(encoding="utf-8") == "task=4|Un titre\nflow_id=abc-123\n"


def test_no_file_is_no_resume_point(tmp_path):
    assert resume.read_pointer(tmp_path / "nope") == (None, None)


def test_clear_removes_the_pointer_and_is_idempotent(tmp_path):
    p = tmp_path / "state"
    resume.write_pointer("t", "f", p)
    resume.clear(p)
    resume.clear(p)
    assert not p.exists()


def make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE flow_states (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " flow_uuid TEXT NOT NULL, method_name TEXT NOT NULL,"
                 " timestamp DATETIME NOT NULL, state_json TEXT NOT NULL)")
    for uuid, method, payload in rows:
        conn.execute("INSERT INTO flow_states (flow_uuid, method_name, timestamp,"
                     " state_json) VALUES (?, ?, datetime('now'), ?)",
                     (uuid, method, json.dumps(payload)))
    conn.commit()
    conn.close()


def test_stages_done_reads_the_latest_snapshot(tmp_path):
    db = tmp_path / "flow.db"
    make_db(db, [("f1", "business_analyst", {"stages_done": ["business-analyst"]}),
                 ("f1", "code", {"stages_done": ["business-analyst", "code"]}),
                 ("f2", "code", {"stages_done": ["autre-flow"]})])
    assert resume.stages_done("f1", db).value == ["business-analyst", "code"]
    assert resume.stages_done("f2", db).value == ["autre-flow"]


def test_unknown_flow_or_missing_db_reads_as_nothing_done(tmp_path):
    db = tmp_path / "flow.db"
    make_db(db, [("f1", "code", {"stages_done": ["code"]})])
    assert resume.stages_done("inconnu", db).value == []
    assert resume.stages_done("f1", tmp_path / "absent.db").value == []
    assert resume.stages_done("", db).value == []


def corrupt_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE flow_states (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " flow_uuid TEXT, method_name TEXT, timestamp DATETIME,"
                 " state_json TEXT)")
    conn.execute("INSERT INTO flow_states VALUES (1,'f1','m','now','pas du json')")
    conn.commit()
    conn.close()


def test_a_corrupt_snapshot_is_loud_instead_of_reading_as_nothing_done(tmp_path):
    """D1: silently returning `[]` makes the loop re-pay a merged /code."""
    db = tmp_path / "flow.db"
    corrupt_db(db)
    got = resume.stages_done("f1", db)
    assert got.status is Status.UNREADABLE
    assert "flow.db" in got.reason
    assert "--restart" in got.reason


def test_an_unreadable_store_is_loud_too(tmp_path):
    """A file that is not a database: `sqlite3.Error`, not `[]`."""
    db = tmp_path / "flow.db"
    db.write_text("ce n'est pas une base sqlite", encoding="utf-8")
    assert resume.stages_done("f1", db).status is Status.UNREADABLE


def test_the_status_reports_the_degraded_read_without_crashing(tmp_path):
    """`--status` must stay a command that answers — while saying so."""
    ws = Workspace(tmp_path)
    ws.flow_db.parent.mkdir(parents=True, exist_ok=True)
    corrupt_db(ws.flow_db)
    resume.write_pointer("4|Une task", "f1", ws.state)
    text = reports.status_text(ws)
    assert "4|Une task" in text
    assert "unknown" in text and "cannot read the resume state" in text
    # Et la cle elle-meme est du markdown : `--status` le dit plutot que
    # d'aller demander a GitHub une issue qui n'existe pas.
    assert "predates the move to GitHub issues" in text


def test_the_connection_is_closed_after_a_read(tmp_path):
    """D4: `with sqlite3.connect(...)` manages the transaction, not the handle."""
    db = tmp_path / "flow.db"
    make_db(db, [("f1", "code", {"stages_done": ["code"]})])
    opened = []
    real = sqlite3.connect

    def spy(*a, **kw):
        conn = real(*a, **kw)
        opened.append(conn)
        return conn

    with mock.patch.object(sqlite3, "connect", spy):
        assert resume.stages_done("f1", db).value == ["code"]
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")
