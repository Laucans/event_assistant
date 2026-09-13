"""Le compteur de rounds, et ce qu'un round donne ecrit. Metier pur.

Le compteur vit dans les commentaires de l'issue : le lire trop bas fait
repartir le raffinage au round 1, qui reecrit le corps par-dessus tout ce que
les rounds precedents ont paye.
"""

import pytest

from pipeline.workflows.refinement.internals import rounds

ROUND_ONE = ("business-goal", "technical", "acceptance-criteria")
ROUND_TWO = ("business-rules", "technical-plan")
ALL_FIVE = ROUND_ONE + ROUND_TWO

FULL = {key: "du texte" for key in ALL_FIVE}


# --- le compteur -----------------------------------------------------------


def test_an_issue_nobody_has_refined_is_at_round_zero():
    assert rounds.counter([]) == 0
    assert rounds.counter(None) == 0


def test_one_round_already_commented_is_counted():
    assert rounds.counter(["refinement round: 1"]) == 1


def test_the_highest_round_wins_whatever_the_order_of_the_comments():
    """Les commentaires reviennent dans l'ordre de GitHub, pas dans le notre."""
    assert rounds.counter(["refinement round: 3", "refinement round: 1",
                           "refinement round: 2"]) == 3


def test_a_marker_among_other_comments_is_still_seen():
    assert rounds.counter(["une remarque de Laurent",
                           "refinement round: 2",
                           "encore une remarque"]) == 2


def test_a_marker_on_its_own_line_inside_a_longer_comment_counts():
    assert rounds.counter(["voila ce que j'en pense\nrefinement round: 4\n"]) == 4


def test_the_marker_is_read_whatever_its_case_and_its_indentation():
    assert rounds.counter(["  Refinement Round:  7  "]) == 7


def test_the_words_of_the_marker_in_a_sentence_do_not_count_as_a_round():
    """Sinon parler du raffinage dans un commentaire sauterait un round."""
    assert rounds.counter(["on en est au refinement round: 2 je crois"]) == 0


def test_a_marker_without_a_number_counts_nothing():
    assert rounds.counter(["refinement round:", "refinement round: deux"]) == 0


def test_the_comment_a_round_posts_says_the_round_and_nothing_else():
    assert rounds.comment(3) == "refinement round: 3"


def test_the_comment_a_round_posts_is_one_the_next_round_can_read():
    """Les deux moities du compteur : ce qu'on ecrit, et ce qu'on relit."""
    assert rounds.counter([rounds.comment(5)]) == 5


# --- ce qu'un round ecrit --------------------------------------------------


def test_round_one_writes_the_three_sections_of_round_one():
    assert rounds.planned(1, {}, False) == ROUND_ONE
    assert rounds.planned(1, FULL, True) == ROUND_ONE


def test_round_two_writes_its_two_sections_when_round_one_is_complete():
    assert rounds.planned(2, FULL, False) == ROUND_TWO


def test_round_two_catches_up_the_sections_round_one_never_wrote():
    """Un stage tombe au round 1 laisserait sa section vide pour toujours."""
    partial = {"business-goal": "du texte"}
    assert rounds.planned(2, partial, False) == (
        "technical", "acceptance-criteria") + ROUND_TWO


@pytest.mark.parametrize("round_no", [3, 4, 9])
def test_a_late_round_without_context_rewrites_the_five_sections(round_no):
    assert rounds.planned(round_no, FULL, False) == ALL_FIVE


@pytest.mark.parametrize("round_no", [3, 4, 9])
def test_a_late_round_with_a_context_writes_nothing_until_the_router_says(
        round_no):
    assert rounds.planned(round_no, FULL, True) == ()


def test_the_router_only_runs_from_round_three_and_only_with_a_context():
    """Chaque section qu'il nomme coute une session : il ne decide pas seul."""
    assert rounds.routed(3, True) is True
    assert rounds.routed(3, False) is False
    assert rounds.routed(2, True) is False
    assert rounds.routed(1, True) is False


# --- ce que le routeur a nomme ---------------------------------------------


def test_the_keys_the_router_wrote_are_read_back():
    assert rounds.wanted_from("business-goal\ntechnical-plan") == (
        "business-goal", "technical-plan")


def test_the_headings_name_their_section_as_well_as_the_keys():
    assert rounds.wanted_from("Business Goal\nTechnical Implementation Plan") == (
        "business-goal", "technical-plan")


def test_the_sections_come_back_in_the_canonical_order_not_the_routers():
    """Le corps se reecrit dans l'ordre du corps, pas dans celui de la reponse.

    Les cinq a l'envers : deux suffiraient a tomber juste par hasard.
    """
    assert rounds.wanted_from("\n".join(reversed(ALL_FIVE))) == ALL_FIVE
    assert rounds.wanted_from("technical-plan\nbusiness-goal") == (
        "business-goal", "technical-plan")


def test_a_section_named_twice_is_wanted_once():
    assert rounds.wanted_from("technical\nTechnical") == ("technical",)


def test_technical_alone_does_not_drag_the_implementation_plan_with_it():
    """Deux cles se ressemblent, et la confusion coute une session opus."""
    assert rounds.wanted_from("technical") == ("technical",)
    assert rounds.wanted_from("technical-plan") == ("technical-plan",)
    assert rounds.wanted_from("Technical Implementation Plan") == (
        "technical-plan",)


def test_a_router_that_named_both_gets_both():
    assert rounds.wanted_from("technical\ntechnical-plan") == (
        "technical", "technical-plan")
    assert rounds.wanted_from(
        "Technical\nTechnical Implementation Plan") == (
        "technical", "technical-plan")


def test_a_reply_with_bullets_around_the_keys_is_still_read():
    assert rounds.wanted_from("- business-rules\n- acceptance-criteria") == (
        "acceptance-criteria", "business-rules")


@pytest.mark.parametrize("answer", ["", None, "je ne sais pas",
                                    "aucune section", "technicalities"])
def test_a_reply_naming_no_section_is_empty_rather_than_everything(answer):
    """Vide, c'est le gate du routeur qui echoue ; tout, c'est cinq sessions."""
    assert rounds.wanted_from(answer) == ()


def test_the_short_form_of_the_plan_is_not_read_as_the_technical_section():
    """« technical plan » nommait `technical` : la mauvaise section rouvrait."""
    assert rounds.wanted_from("technical plan") == ("technical-plan",)
    assert rounds.wanted_from("implementation plan") == ("technical-plan",)
