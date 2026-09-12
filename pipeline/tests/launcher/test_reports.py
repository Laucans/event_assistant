"""Les tables que `--costs` imprime, dont la premiere est celle du shell.

Le registre est ecrit avec `ledger.append` : c'est le constructeur de
fixtures le plus honnete, puisque c'est ce qui l'ecrit en production.
"""

import pytest
from conftest import ORACLE, milestone

from pipeline.adapters.store import ledger, resume
from pipeline.launcher.cli import reports
from pipeline.domain import tasks
from pipeline.runtime.filesystem.workspace import Workspace


def test_report_matches_the_shell_output():
    """The historical table stays character-for-character the shell's.

    Les metriques ajoutees depuis vivent dans une section separee par une
    ligne vide, precisement pour que cette comparaison reste possible.
    """
    core = reports.report(Workspace.here().ledger).split("\n\n")[0]
    assert core == (ORACLE / "costs-report.txt").read_text(
        encoding="utf-8").rstrip("\n")


def test_old_twelve_column_rows_still_read(tmp_path):
    """The cache columns were appended at end of line, not inserted."""
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + "\t".join(
        ["2026-01-01T00:00:00", "r", "01", "4|T", "code", "1.000000", "3",
         "10", "1", "2", "s", "opus/high"]) + "\n", encoding="utf-8")
    report = reports.report(f)
    assert "code" in report and "1.0000" in report
    assert "\n\n" not in report   # aucune section cache : ces lignes n'en ont pas


def test_the_cache_section_appears_once_there_is_data(tmp_path):
    f = tmp_path / "c.tsv"
    ledger.append(f, run_id="r", round_no=1, task="t", stage="code", cost=1.0,
                  turns=1, duration_ms=1, tokens_in=10000, tokens_out=500,
                  session="s", ran_on="opus/high", cache_read=90000,
                  cache_write=0)
    section = reports.report(f).split("\n\n")[1]
    assert "cache" in section
    assert "90%" in section


def test_a_missing_cost_is_booked_as_zero(tmp_path):
    f = tmp_path / "c.tsv"
    ledger.append(f, run_id="r", round_no=1, task="t", stage="s", cost=None,
                  turns=None, duration_ms=None, tokens_in=None, tokens_out=None,
                  session=None, ran_on="haiku/low")
    assert f.read_text(encoding="utf-8").splitlines()[1].split("\t")[5] == "0.000000"


def test_an_absent_ledger_says_so(tmp_path):
    assert "no cost ledger yet" in reports.report(tmp_path / "nope.tsv")


def test_the_outcome_column_separates_money_that_bought_something(tmp_path):
    """A8: a failed stage cost money, and used to read as a purchase."""
    f = tmp_path / "c.tsv"
    for stage, cost, outcome in [("code", 1.0, "ok"), ("code", 2.0, "quota"),
                                 ("create-test", 0.5, "ok")]:
        ledger.append(f, run_id="r1", round_no=1, task="4|Schema", stage=stage,
                      cost=cost, turns=1, duration_ms=1, tokens_in=1,
                      tokens_out=1, session="s", ran_on="opus/high",
                      outcome=outcome)
    out = reports.breakdown(f, by="task")
    assert "4|Schema" in out
    assert "3.5000" in out          # le total inclut ce qui a echoue
    assert "2.0000" in out          # ... et le nomme comme gaspille
    assert "predate the outcome column" not in out


def test_a_breakdown_answers_what_this_task_cost(tmp_path):
    f = tmp_path / "c.tsv"
    for task, cost in [("3|Supabase", 1.0), ("4|Schema", 2.0)]:
        ledger.append(f, run_id="r1", round_no=1, task=task, stage="code",
                      cost=cost, turns=1, duration_ms=1, tokens_in=1,
                      tokens_out=1, session="s", ran_on="opus/high", outcome="ok")
    only = reports.breakdown(f, by="task", task="schema")
    assert "4|Schema" in only and "3|Supabase" not in only


def test_a_breakdown_answers_what_today_cost(tmp_path):
    f = tmp_path / "c.tsv"
    ledger.append(f, run_id="r1", round_no=1, task="4|Schema", stage="code",
                  cost=1.0, turns=1, duration_ms=1, tokens_in=1, tokens_out=1,
                  session="s", ran_on="opus/high", outcome="ok")
    today = reports.breakdown(f, by="day").splitlines()[1].split()[0]
    assert len(today) == 10 and today[4] == "-"
    assert "no ledger row matches" in reports.breakdown(f, by="day",
                                                       since="2999-01-01")


def test_rows_written_before_the_outcome_column_are_never_called_successes(tmp_path):
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + "\t".join(
        ["2026-01-01T00:00:00", "r", "01", "4|T", "code", "1.000000", "3",
         "10", "1", "2", "s", "opus/high"]) + "\n", encoding="utf-8")
    out = reports.breakdown(f, by="task")
    assert "1 row(s) predate the outcome column" in out


def test_an_unknown_grouping_says_what_is_available(tmp_path):
    f = tmp_path / "c.tsv"
    ledger.append(f, run_id="r", round_no=1, task="t", stage="code", cost=1.0,
                  turns=1, duration_ms=1, tokens_in=1, tokens_out=1,
                  session="s", ran_on="o/h", outcome="ok")
    assert "unknown grouping" in reports.breakdown(f, by="couleur")


TRUNCATED = "2026-01-01T00:00:00\tr\t01\t4|T\tcode\t1.000000\n"
FULL = "\t".join(["2026-01-02T00:00:00", "r", "01", "4|T", "code", "2.000000",
                  "3", "10", "1", "2", "s", "opus/high", "", "", "ok"]) + "\n"


def test_a_truncated_row_is_named_instead_of_dropped(tmp_path):
    """D8 : un registre tronque sous-declarait la depense, sans un mot."""
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + TRUNCATED + FULL, encoding="utf-8")
    out = reports.report(f)
    assert out.split("\n\n")[0].splitlines()[-1].startswith("ALL")
    assert "1 row(s) ignored" in out
    assert "under-reports" in out


def test_a_clean_ledger_says_nothing_about_ignored_rows(tmp_path):
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + FULL, encoding="utf-8")
    assert "ignored" not in reports.report(f)
    assert "ignored" not in reports.breakdown(f, by="task")


def test_the_breakdown_names_the_rows_it_could_not_read(tmp_path):
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + TRUNCATED + FULL, encoding="utf-8")
    out = reports.breakdown(f, by="task")
    assert "2.0000" in out
    assert "1 row(s) ignored" in out


def test_the_historical_table_keeps_its_first_block(tmp_path):
    """The oracle comparison reads the first block: nothing may slip into it."""
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + TRUNCATED + FULL, encoding="utf-8")
    head = reports.report(f).split("\n\n")[0].splitlines()
    assert head[0].startswith("stage")
    assert len(head) == 3          # en-tete, une ligne de stage, ALL


def test_a_wholly_truncated_ledger_is_named_not_called_empty(tmp_path):
    """`--costs` le disait deja ; `--costs-by` disait « rien depense ».

    Un registre coupe en plein milieu d'une ecriture n'est pas un registre
    vide : dire a l'operateur que rien n'a ete depense est le pire des deux
    mensonges possibles.
    """
    f = tmp_path / "c.tsv"
    f.write_text(ledger.HEADER + TRUNCATED + TRUNCATED, encoding="utf-8")
    out = reports.breakdown(f, by="task")
    assert "no cost ledger yet" not in out
    assert "2 row(s) ignored" in out


# --- ce que `--status` dit de la task en cours ------------------------------
#
# Le pointeur ne porte plus qu'un numero : tout ce qu'un humain veut lire —
# le titre, l'etat, les etiquettes — est sur GitHub. C'est la seule lecture
# d'issue du paquet qui ne doit jamais lever : `--status` repond, toujours.

@pytest.fixture
def pointer(tmp_path):
    """Un workspace a nous : le pointeur de reprise y vit, et nulle part ailleurs."""
    return Workspace(tmp_path)


def test_no_pointer_says_a_run_would_start_from_the_top(pointer):
    assert "no resume point" in reports.status_text(pointer)


def test_the_status_names_the_issue_it_would_resume(pointer, hub):
    number, numbers = milestone(hub, ready=(0,), tasks=("Schema",))
    hub.issues[numbers[0]]["labels"].append({"name": tasks.SPEC_WRITTEN})
    resume.write_pointer(str(numbers[0]), "f1", pointer.state)
    said = reports.status_text(pointer)
    assert f"issue #{numbers[0]}: Schema [open]" in said
    assert tasks.SPEC_WRITTEN in said


def test_a_github_that_will_not_answer_is_a_line_not_a_crash(pointer, hub):
    """`--status` ne depense rien : ne pas savoir n'a pas a l'arreter."""
    milestone(hub, ready=(0,), tasks=("Schema",))
    hub.fails_on = "issues"
    resume.write_pointer("2", "f1", pointer.state)
    said = reports.status_text(pointer)
    assert "issue #2: unreadable" in said
    assert "task=2" in said


def test_a_pointer_left_over_from_the_markdown_era_is_named_as_such(pointer,
                                                                    hub):
    resume.write_pointer("4|Schema, seed & first DB-backed page", "f1",
                         pointer.state)
    said = reports.status_text(pointer)
    assert "predates the move to GitHub issues" in said
    assert "--restart" in said
