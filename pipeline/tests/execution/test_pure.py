"""Ce que l'execution decide sans rien toucher.

Ces fonctions vivaient dans le corps de `session.run` : les exercer demandait
une session, un workspace et un registre. Sorties, elles se testent en leur
passant des chaines — et c'est la moitie des chemins d'erreur du paquet.
"""

from pathlib import Path

import pytest

from pipeline.domain.outcomes.exit_codes import EXIT_QUOTA, EXIT_STAGE_FAILED
from pipeline.domain.outcomes.result import Status
from pipeline.execution.session import Artifacts, failure_of


# --- les trois fichiers d'un stage -----------------------------------------


def test_the_three_artifacts_hang_off_the_round_and_the_skill():
    files = Artifacts.of(Path("/logs"), 7, "code")
    assert files.log == Path("/logs/07-code.log")
    assert files.envelope == Path("/logs/07-code.json")
    assert files.trace == Path("/logs/07-code.trace.log")


def test_the_round_number_is_zero_padded_like_the_ledger_column():
    """Le registre ecrit la meme valeur dans sa colonne `round`."""
    assert Artifacts.of(Path("/l"), 3, "s").log.name.startswith("03-")
    assert Artifacts.of(Path("/l"), 12, "s").log.name.startswith("12-")


def test_two_stages_of_one_round_do_not_share_a_file():
    one = Artifacts.of(Path("/l"), 1, "code")
    two = Artifacts.of(Path("/l"), 1, "create-test")
    assert {one.log, one.envelope, one.trace}.isdisjoint(
        {two.log, two.envelope, two.trace})


# --- la panne que vaut une raison ------------------------------------------


def test_a_stage_that_answered_is_no_failure():
    assert failure_of(None, "code", "success", "where") is None


@pytest.mark.parametrize("reason, status, code", [
    ("quota", Status.QUOTA, EXIT_QUOTA),
    ("failed", Status.FAILED, EXIT_STAGE_FAILED),
    ("empty", Status.FAILED, EXIT_STAGE_FAILED),
])
def test_each_reason_carries_its_own_status_and_exit_code(reason, status, code):
    """Un ordonnanceur exterieur lit ces codes : ils ne se confondent pas.

    « reviens quand la fenetre se reouvre » et « quelque chose est casse »
    n'appellent pas la meme reponse.
    """
    failure = failure_of(reason, "code", "error_max_turns", "env.json, s-1")
    assert failure.status is status
    assert failure.exit_code == code


@pytest.mark.parametrize("reason", ["quota", "failed", "empty"])
def test_every_failure_names_where_to_look(reason):
    """L'identifiant de session est la seule cle qui rouvre la session morte."""
    failure = failure_of(reason, "code", "error_x", "07-code.json, session s-1")
    assert "07-code.json" in str(failure) and "s-1" in str(failure)


def test_the_subtype_is_named_only_where_it_explains_something():
    """Il dit *comment* le fournisseur a echoue ; il n'a de sens que la."""
    assert "error_max_turns" in str(
        failure_of("failed", "code", "error_max_turns", "w"))
    assert "error_max_turns" not in str(
        failure_of("empty", "code", "error_max_turns", "w"))


def test_an_unknown_reason_is_not_silently_a_failure():
    """Rendre une panne pour une raison inconnue arreterait un run sain."""
    assert failure_of("something-new", "code", "s", "w") is None
