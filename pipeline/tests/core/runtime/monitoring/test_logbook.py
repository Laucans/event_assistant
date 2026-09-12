"""The journal: a level, a date, a context — and one single system.

What these tests defend is what the `print()` closure they replace was
missing: a warning line that does not look like an ordinary line, a date that
survives a run crossing midnight, and an attribution when a detached review
writes into the same terminal.
"""

import io
import logging
import re

from pipeline.core.runtime.monitoring import logbook


def book(tmp_path, level=logbook.NORMAL, name="t"):
    stream = io.StringIO()
    log = logbook.open_logbook(name, file=tmp_path / "run.log", level=level,
                               stream=stream)
    return log, stream, tmp_path / "run.log"


def test_a_line_carries_a_date_a_level_and_its_context(tmp_path):
    log, stream, _ = book(tmp_path)
    log.bind("20260910-090000", "r1", "code")("ça tourne")
    line = stream.getvalue().strip()
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  INFO   "
                    r"\[20260910-090000 r1 code]  ça tourne$", line), line


def test_a_warning_does_not_read_like_an_ordinary_step(tmp_path):
    """The original defect: `print()` made the two identical."""
    log, stream, _ = book(tmp_path)
    log("ordinaire")
    log.warn("panneaux crewai non desactivables")
    info, warn = stream.getvalue().splitlines()
    assert "INFO" in info and "WARN" in warn


def test_context_is_bound_not_passed(tmp_path):
    log, stream, _ = book(tmp_path)
    round_log = log.bind("r1")
    round_log.bind("code")("dans le stage")
    round_log("hors du stage")
    lines = stream.getvalue().splitlines()
    assert "[r1 code]" in lines[0]
    assert "[r1]" in lines[1] and "code" not in lines[1]


def test_quiet_silences_the_terminal_but_never_the_file(tmp_path):
    """A silent cron must not make its own post-mortem useless."""
    log, stream, run_log = book(tmp_path, level=logbook.QUIET)
    log("une info")
    log.warn("un avertissement")
    assert "une info" not in stream.getvalue()
    assert "un avertissement" in stream.getvalue()
    assert "une info" in run_log.read_text(encoding="utf-8")


def test_verbose_puts_the_debug_detail_on_the_terminal(tmp_path):
    log, stream, _ = book(tmp_path, level=logbook.VERBOSE)
    log.debug("→ Read src/app/page.tsx")
    assert "Read src/app/page.tsx" in stream.getvalue()


def test_a_traceback_reaches_the_run_log(tmp_path):
    """A2: this is the whole point — the unexpected error must be written."""
    log, _, run_log = book(tmp_path)
    try:
        raise OSError(28, "No space left on device")
    except OSError:
        log.exception("CRASH — the run died on an unexpected error")
    written = run_log.read_text(encoding="utf-8")
    assert "CRASH" in written
    assert "Traceback (most recent call last):" in written
    assert "No space left on device" in written


def test_opening_twice_does_not_double_every_line(tmp_path):
    """`basicConfig` empilait un handler de plus a chaque appel."""
    for _ in range(3):
        log, stream, _ = book(tmp_path, name="twice")
    log("une fois")
    assert stream.getvalue().count("une fois") == 1


def test_the_null_logbook_writes_nowhere(capsys):
    log = logbook.null()
    log("rien")
    log.warn("rien non plus")
    assert capsys.readouterr().out == ""


def test_the_package_logger_does_not_propagate(tmp_path):
    """crewai configure le logger racine ; sans ca chaque ligne sortirait deux fois."""
    log, _, _ = book(tmp_path, name="propagation")
    assert logging.getLogger("propagation").propagate is False
