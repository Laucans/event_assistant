"""Ce que la revue decide sans appeler personne.

Ces deux-la vivaient dans le corps de `run` et de `run_pass` : les exercer
demandait une PR, un faux `gh` et deux passes. Sorties, elles prennent un
dictionnaire ou trois chaines.
"""

import pytest

from pipeline.workflows.pr_review.internals.passes import (
    PASS_FAILURES, pass_failure)
from pipeline.workflows.pr_review.internals.pr import Pr

META = {"number": 12, "baseRefName": "main_agent", "headRefName": "feat/x",
        "title": "Un titre de PR", "url": "https://github.com/o/r/pull/12",
        "state": "OPEN", "isDraft": False}


# --- les metadonnees d'une PR ----------------------------------------------


def test_a_pr_reads_the_five_fields_the_review_needs():
    pr = Pr.of(META)
    assert (pr.num, pr.base, pr.head) == ("12", "main_agent", "feat/x")
    assert (pr.title, pr.url) == ("Un titre de PR", META["url"])


def test_the_number_is_a_string_because_every_reader_wants_one():
    """Il nomme des fichiers et part dans des commandes `gh`, jamais en int."""
    assert Pr.of({**META, "number": 7}).num == "7"


# --- ce qu'une passe qui n'a rien rendu vaut -------------------------------


def test_a_pass_that_answered_says_nothing():
    assert pass_failure(None, label="inline", subtype="success",
                        session="s") is None


def test_an_unknown_reason_says_nothing_rather_than_guessing():
    assert pass_failure("surprise", label="inline", subtype="s",
                        session="s") is None


def test_a_quota_is_a_warning_and_the_two_others_are_errors():
    """La passe n'a pas casse, elle a ete coupee : relancer plus tard suffit.

    Les confondre ferait chercher un bug la ou il n'y a qu'une fenetre
    d'abonnement epuisee.
    """
    assert pass_failure("quota", label="inline", subtype="s",
                        session="s")[0] == "warn"
    assert pass_failure("failed", label="inline", subtype="s",
                        session="s")[0] == "error"
    assert pass_failure("empty", label="inline", subtype="s",
                        session="s")[0] == "error"


@pytest.mark.parametrize("reason", sorted(PASS_FAILURES))
def test_every_failure_names_the_pass_and_its_session(reason):
    """L'identifiant de session est ce qui rouvre exactement la passe morte."""
    _, said = pass_failure(reason, label="brief", subtype="error_x",
                           session="sess-7")
    assert "brief" in said and "sess-7" in said


def test_only_a_real_failure_names_the_subtype():
    """Il dit *comment* le fournisseur a echoue ; ailleurs il n'explique rien."""
    assert "error_max_turns" in pass_failure(
        "failed", label="b", subtype="error_max_turns", session="s")[1]
    assert "error_max_turns" not in pass_failure(
        "quota", label="b", subtype="error_max_turns", session="s")[1]


def test_every_level_the_table_names_is_one_the_journal_has():
    from pipeline.runtime.monitoring import logbook
    log = logbook.null()
    for level, _ in PASS_FAILURES.values():
        assert callable(getattr(log, level))
