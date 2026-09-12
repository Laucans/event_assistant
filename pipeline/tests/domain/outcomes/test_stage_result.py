"""Le contrat verbal d'un stage : les deux marqueurs de fin de reponse.

Metier pur, teste comme tel — on passe trois lignes de texte, on lit ce qui
sort. Aucune session, aucun disque, aucun fournisseur.
"""

from pipeline.domain.outcomes.stage_result import StageResult, read_markers


def test_the_markers_are_read_off_their_own_line():
    ok, stop = read_markers(
        "du bla\nAGENT_LOOP_OK: la task 4 est fermee\nencore du bla")
    assert ok == "AGENT_LOOP_OK: la task 4 est fermee" and stop is None
    ok, stop = read_markers("AGENT_LOOP_STOP: c'est ambigu")
    assert stop == "AGENT_LOOP_STOP: c'est ambigu" and ok is None


def test_the_first_marker_of_each_kind_wins():
    ok, stop = read_markers(
        "AGENT_LOOP_OK: le premier\nAGENT_LOOP_OK: le second\n"
        "AGENT_LOOP_STOP: puis un stop\nAGENT_LOOP_STOP: et un autre")
    assert ok == "AGENT_LOOP_OK: le premier"
    assert stop == "AGENT_LOOP_STOP: puis un stop"


def test_a_marker_mentioned_mid_sentence_is_not_a_marker():
    """The shell grepped the whole line: it must start with the word."""
    assert read_markers("j'aurais pu ecrire AGENT_LOOP_STOP: mais non") == (
        None, None)


def test_a_marker_keeps_its_trailing_whitespace_out():
    ok, _ = read_markers("AGENT_LOOP_OK: fait   \n")
    assert ok == "AGENT_LOOP_OK: fait"


def test_a_stop_line_is_what_makes_a_result_stopped():
    """`stopped` est ce que le flow lit pour halter — pas le texte."""
    assert not StageResult("ok", 0.0, "s", "AGENT_LOOP_OK: fait", None).stopped
    assert StageResult("", 0.0, "s", None, "AGENT_LOOP_STOP: ambigu").stopped
