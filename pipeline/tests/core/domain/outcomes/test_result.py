"""Le pattern Result : ce que chaque statut vaut dehors, et la propagation.

Metier pur, teste comme tel — aucune session, aucun disque, aucun `gh`. Ce
fichier garde ce qui etait asserte sur la hierarchie d'exceptions avant
qu'elle disparaisse : les codes de sortie qu'un ordonnanceur lit, et le
niveau auquel chaque fin se dit.
"""

import pytest

from pipeline.core.domain.outcomes.exit_codes import (
    EXIT_HALT, EXIT_OK, EXIT_QUOTA, EXIT_STAGE_FAILED)
from pipeline.core.domain.outcomes.result import Result, Status
from pipeline.core.runtime.monitoring import logbook


# --- ce qu'un resultat porte -----------------------------------------------


def test_a_result_that_succeeded_carries_its_value():
    got = Result.of([1, 2])
    assert got.ok and not got.failed
    assert got.value == [1, 2] and got.exit_code == EXIT_OK


@pytest.mark.parametrize("make, status", [
    (Result.halt, Status.HALTED),
    (Result.unreadable, Status.UNREADABLE),
    (Result.fail, Status.FAILED),
    (Result.quota, Status.QUOTA),
])
def test_a_failure_carries_its_reason_and_no_value(make, status):
    """Une valeur lisible sur un echec est exactement ce qu'on veut empecher.

    `[]` lu comme « ce milestone est fini » est l'entree qui fait payer un
    `/planner` : un echec ne doit jamais pouvoir etre deballe par megarde.
    """
    got = make("la raison")
    assert got.failed and not got.ok
    assert got.value is None
    assert got.reason == "la raison" and str(got) == "la raison"


@pytest.mark.parametrize("make, code", [
    (Result.halt, EXIT_HALT),
    (Result.unreadable, EXIT_HALT),
    (Result.fail, EXIT_STAGE_FAILED),
    (Result.quota, EXIT_QUOTA),
])
def test_each_way_of_stopping_keeps_its_own_exit_code(make, code):
    """Un ordonnanceur exterieur lit ces codes, et ils sont dans `--help`.

    « reviens quand la fenetre se reouvre » et « quelque chose est casse »
    n'appellent pas la meme reponse.
    """
    assert make("x").exit_code == code


def test_each_way_of_stopping_carries_its_own_log_level():
    """Le CLI lit le niveau sur le statut, pas via un `if` par sorte.

    Un arret volontaire est un resultat correct : il ne se lit pas comme un
    avertissement. Une panne de stage n'est pas un arret. Et un quota n'est
    ni l'un ni l'autre — c'est « reviens plus tard ».
    """
    assert Result.halt("x").level == "info"
    assert Result.unreadable("x").level == "info"
    assert Result.fail("x").level == "error"
    assert Result.quota("x").level == "warn"


def test_every_level_is_one_the_journal_answers_to():
    """Un niveau invente ferait planter le CLI au moment de dire l'arret."""
    log = logbook.null()
    for status in Status:
        level = Result(status=status).level
        assert callable(getattr(log, level)), status


def test_each_way_of_stopping_has_its_own_word_in_the_journal():
    assert Result.halt("x").prefix == "STOP"
    assert Result.unreadable("x").prefix == "STOP"
    assert Result.fail("x").prefix == "FAILED"
    assert Result.quota("x").prefix == "QUOTA"


# --- la propagation --------------------------------------------------------


def test_recast_keeps_the_failure_and_drops_only_the_value_type():
    got = Result.quota("plus de fenetre").recast()
    assert got.status is Status.QUOTA and got.reason == "plus de fenetre"


def test_recasting_a_success_is_a_bug_and_says_so():
    """Propager un succes comme un echec serait un arret muet et invente."""
    with pytest.raises(ValueError):
        Result.of(3).recast()


def test_map_applies_to_a_value_and_steps_aside_for_a_failure():
    assert Result.of([1, 2, 3]).map(len).value == 3
    stayed = Result.unreadable("gh est muet").map(len)
    assert stayed.status is Status.UNREADABLE and stayed.value is None


def test_but_keeps_the_original_reason_behind_the_new_one():
    """Ce qui a casse en bas et ce que ca empechait en haut : les deux."""
    got = Result.fail("HTTP 500").but("cannot read the board")
    assert "cannot read the board" in got.reason and "HTTP 500" in got.reason
    assert got.status is Status.FAILED
