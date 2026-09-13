"""Les cinq sections : ce que le corps d'une issue rend, et ce qu'il redevient.

Metier pur, donc rien n'est branche ici. Ce que ce fichier protege est un
aller-retour : le corps qu'un round ecrit est celui que le round suivant
relit, et une section perdue entre les deux est une session payee pour rien.
"""

import pytest

from pipeline.workflows.refinement.internals import sections

FULL = {
    "business-goal": "Le but.",
    "technical": "La technique.",
    "acceptance-criteria": "- un critere\n- un autre",
    "business-rules": "1. une regle",
    "technical-plan": "1. une etape",
}


def test_the_five_sections_are_in_the_canonical_order():
    assert sections.KEYS == ("business-goal", "technical",
                             "acceptance-criteria", "business-rules",
                             "technical-plan")


def test_each_round_introduces_the_sections_the_plan_says():
    assert sections.keys_of_round(1) == ("business-goal", "technical",
                                         "acceptance-criteria")
    assert sections.keys_of_round(2) == ("business-rules", "technical-plan")
    assert sections.keys_of_round(3) == ()


def test_a_key_that_exists_names_its_heading_and_an_unknown_one_says_nothing():
    assert sections.by_key("technical-plan").heading == (
        "Technical Implementation Plan")
    assert sections.by_key("router") is None


def test_a_body_written_by_a_round_is_read_back_whole():
    """L'aller-retour : ce qui n'y survit pas est une section perdue."""
    assert sections.parse(sections.render(FULL)) == FULL


@pytest.mark.parametrize("key", list(FULL))
def test_every_section_alone_survives_the_round_trip(key):
    only = {key: FULL[key]}
    assert sections.parse(sections.render(only)) == only


def test_the_body_is_rendered_in_the_canonical_order_whatever_the_dict_order():
    """Un corps dont l'ordre bouge d'un round a l'autre se relit mal."""
    backwards = dict(reversed(list(FULL.items())))
    assert sections.render(backwards) == sections.render(FULL)
    body = sections.render(backwards)
    assert [line for line in body.splitlines() if line.startswith("## ")] == [
        "## Business Goal", "## Technical", "## Acceptance Criteria",
        "## Business Rules", "## Technical Implementation Plan"]


def test_the_body_carries_nothing_but_the_sections():
    body = sections.render({"business-goal": "Le but."})
    assert body == "## Business Goal\n\nLe but.\n"


def test_a_section_the_round_has_nothing_for_is_left_out():
    assert sections.render({"business-goal": "Le but.", "technical": ""}) == (
        "## Business Goal\n\nLe but.\n")
    assert sections.render({"business-goal": "   \n  "}) == ""
    assert sections.render({}) == ""


def test_an_empty_body_reads_as_no_section_rather_than_raising():
    assert sections.parse("") == {}
    assert sections.parse(None) == {}


def test_what_a_human_wrote_before_the_first_heading_is_not_a_section():
    body = "Je voudrais un bouton bleu.\n\n## Technical\n\nUn bouton.\n"
    assert sections.parse(body) == {"technical": "Un bouton."}


def test_a_heading_nobody_declared_is_ignored_but_still_closes_the_one_above():
    """Sinon le contenu d'une section etrangere entrerait dans la precedente."""
    body = ("## Business Goal\n\nLe but.\n\n"
            "## Notes de Laurent\n\nrien a voir\n\n"
            "## Technical\n\nLa technique.\n")
    assert sections.parse(body) == {"business-goal": "Le but.",
                                    "technical": "La technique."}


def test_a_heading_is_matched_whatever_its_case_and_its_trailing_spaces():
    body = "##   business goal   \n\nLe but.\n"
    assert sections.parse(body) == {"business-goal": "Le but."}


def test_a_deeper_heading_inside_a_section_is_not_a_boundary():
    """Un `###` du texte d'une section couperait la section en deux."""
    body = "## Technical\n\n### Le detail\n\nLa technique.\n"
    assert sections.parse(body) == {
        "technical": "### Le detail\n\nLa technique."}


def test_a_section_left_empty_in_the_body_is_not_read_as_written():
    """Sinon `missing` la croirait faite et le rattrapage ne la rejouerait pas."""
    body = "## Business Goal\n\n\n## Technical\n\nLa technique.\n"
    assert sections.parse(body) == {"technical": "La technique."}


def test_what_round_one_still_owes_is_what_the_body_does_not_carry():
    assert sections.missing(FULL) == ()
    assert sections.missing({}) == ("business-goal", "technical",
                                    "acceptance-criteria")
    assert sections.missing({"technical": "La technique.",
                             "business-goal": "  "}) == (
        "business-goal", "acceptance-criteria")


def test_a_section_of_round_two_is_never_something_round_one_owes():
    assert sections.missing({"business-rules": "1. une regle"}) == (
        "business-goal", "technical", "acceptance-criteria")
