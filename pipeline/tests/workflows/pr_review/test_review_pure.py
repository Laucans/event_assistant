"""Ce que la revue decide sans appeler personne.

Ce que valait une passe muette n'est plus ici : les deux passes sont des
etapes ordinaires, et c'est `execution.session.failure_of` qui traduit une
session qui n'a rien rendu. La moitie de ce fichier a suivi, juste en
dessous, parce que ce qu'elle garde reste vrai — un quota se relance, une
panne se debugge, et l'identifiant de session est ce qui rouvre la bonne.
"""

import pytest

from pipeline.core.domain.outcomes.result import Status
from pipeline.core.execution.session import failure_of

# --- ce qu'une session qui n'a rien rendu vaut -----------------------------


def failed(reason, *, skill="inline", subtype="s", where="env, session sess-7"):
    return failure_of(reason, skill, subtype, where)


def test_a_pass_that_answered_says_nothing():
    assert failed(None) is None


def test_an_unknown_reason_says_nothing_rather_than_guessing():
    assert failed("surprise") is None


def test_a_quota_is_a_warning_and_the_two_others_are_errors():
    """La passe n'a pas casse, elle a ete coupee : relancer plus tard suffit.

    Les confondre ferait chercher un bug la ou il n'y a qu'une fenetre
    d'abonnement epuisee — et l'ecart voyage jusqu'au code de sortie.
    """
    assert failed("quota").status is Status.QUOTA
    assert failed("quota").level == "warn"
    assert failed("failed").status is Status.FAILED
    assert failed("failed").level == "error"
    assert failed("empty").status is Status.FAILED
    assert failed("empty").level == "error"


@pytest.mark.parametrize("reason", ["quota", "failed", "empty"])
def test_every_failure_names_the_pass_and_its_session(reason):
    """L'identifiant de session est ce qui rouvre exactement la passe morte."""
    said = failed(reason, skill="brief").reason
    assert "brief" in said and "sess-7" in said


def test_only_a_real_failure_names_the_subtype():
    """Il dit *comment* le fournisseur a echoue ; ailleurs il n'explique rien."""
    assert "error_max_turns" in failed("failed", subtype="error_max_turns").reason
    assert "error_max_turns" not in failed("quota", subtype="error_max_turns").reason


def test_every_level_a_failure_names_is_one_the_journal_has():
    from pipeline.core.runtime.monitoring import logbook
    log = logbook.null()
    for reason in ("quota", "failed", "empty"):
        assert callable(getattr(log, failed(reason).level))
