"""Le registre de couts : ce qui est ecrit, et relu.

Ce que `--costs` en imprime est teste a cote, dans `cli/test_reports.py` :
le schema et la mise en forme ne se cassent pas pour les memes raisons.
"""

from pipeline.adapters.store import ledger


def test_header_is_written_once_and_columns_are_stable(tmp_path):
    f = tmp_path / "costs.tsv"
    for i in range(2):
        ledger.append(f, run_id="r", round_no=1, task="4|T", stage="code",
                      cost=1.5, turns=3, duration_ms=10, tokens_in=1,
                      tokens_out=2, session="s", ran_on="opus/high")
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ledger.HEADER.rstrip("\n")
    assert len(lines) == 3
    cols = lines[1].split("\t")
    assert len(cols) == 15          # `outcome` a ete ajoute en fin de ligne
    assert cols[4] == "code" and cols[5] == "1.500000" and cols[11] == "opus/high"


def test_a_multiline_task_title_stays_on_one_row(tmp_path):
    f = tmp_path / "c.tsv"
    ledger.append(f, run_id="r", round_no=1, task="4|un titre\nsur deux lignes",
                  stage="s", cost=0.1, turns=1, duration_ms=1, tokens_in=1,
                  tokens_out=1, session="s", ran_on="x/y")
    assert len(f.read_text(encoding="utf-8").splitlines()) == 2


# --- le registre de la revue : d'autres colonnes, d'autres lignes ----------

def test_a_review_row_carries_the_pr_and_the_pass(tmp_path):
    f = tmp_path / "review.tsv"
    ledger.append_review(f, pr="12", label="inline", cost=0.1234, turns=8,
                         duration_ms=42_000, tokens_in=1000, tokens_out=200,
                         session="s1", ran_on="sonnet/medium")
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ledger.REVIEW_HEADER.rstrip("\n")
    row = lines[1].split("\t")
    assert row[1:4] == ["12", "inline", "0.123400"]
    assert row[9] == "sonnet/medium"


def test_the_review_header_is_written_once(tmp_path):
    f = tmp_path / "review.tsv"
    for label in ("inline", "brief"):
        ledger.append_review(f, pr="12", label=label, cost=0.1, turns=1,
                             duration_ms=1, tokens_in=1, tokens_out=1,
                             session="s", ran_on="sonnet/low")
    assert len(f.read_text(encoding="utf-8").splitlines()) == 3


def test_the_cost_of_a_review_sums_its_passes(tmp_path):
    f = tmp_path / "review.tsv"
    for pr, cost in [("12", 0.10), ("12", 0.05), ("13", 1.00)]:
        ledger.append_review(f, pr=pr, label="inline", cost=cost, turns=1,
                             duration_ms=1, tokens_in=1, tokens_out=1,
                             session="s", ran_on="sonnet/low")
    assert ledger.review_cost(f, "12") == "0.1500"
    assert ledger.review_cost(f, "13") == "1.0000"


def test_an_unknown_pr_costs_nothing_rather_than_crashing(tmp_path):
    f = tmp_path / "review.tsv"
    ledger.append_review(f, pr="12", label="inline", cost=0.1, turns=1,
                         duration_ms=1, tokens_in=1, tokens_out=1, session="s",
                         ran_on="sonnet/low")
    assert ledger.review_cost(f, "999") == "0.0000"


def test_an_absent_review_ledger_reads_as_an_empty_string(tmp_path):
    """The comment footer omits the cost rather than showing a false zero."""
    assert ledger.review_cost(tmp_path / "nope.tsv", "12") == ""


def test_a_missing_cost_on_a_review_row_is_booked_as_zero(tmp_path):
    f = tmp_path / "review.tsv"
    ledger.append_review(f, pr="12", label="brief", cost=None, turns=None,
                         duration_ms=None, tokens_in=None, tokens_out=None,
                         session=None, ran_on="sonnet/low")
    assert ledger.review_cost(f, "12") == "0.0000"
