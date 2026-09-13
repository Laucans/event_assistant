"""La table du round : ce qu'elle declare, et ce qu'elle emporte avec elle.

Ici et plus dans `domain/` : la table est la definition de ce workflow, pas
du vocabulaire. `domain/test_stage_spec.py` teste le type qu'elle instancie.
"""

from pipeline.workflows.agentic_dev_loop.stages import (
    PIPELINE, PLANNER_STAGE, ROLLOVER)


def test_the_table_is_the_documented_sequence():
    assert [s.skill for s in PIPELINE] == [
        "business-analyst", "code", "create-test"]


def test_nothing_in_the_table_archives_anything():
    """Une task se ferme parce que GitHub la ferme, plus parce qu'un stage
    paye deplace deux fichiers."""
    assert "archive-instructions" not in [s.skill for s in PIPELINE]
    assert len(PIPELINE) == 3


def test_the_code_stage_opens_on_the_tech_analyst():
    code = next(s for s in PIPELINE if s.skill == "code")
    assert code.lead == "/tech-analyst"
    assert code.command == "/tech-analyst"
    assert code.label == "/tech-analyst -> /code"


def test_the_rollover_is_off_by_default():
    """Enchainer sur la roadmap suivante sans surveillance est un choix."""
    assert ROLLOVER is None
    assert "planner" not in [s.skill for s in PIPELINE]


def test_the_planner_entry_stays_ready_to_be_switched_on():
    """Le commentaire dit `ROLLOVER = PLANNER_STAGE` — l'entree doit exister,
    et porter son texte, sinon l'activer partirait muet."""
    assert PLANNER_STAGE.skill == "planner"
    assert PLANNER_STAGE.instructions.strip()


def test_every_stage_that_needs_instructions_carries_them():
    """Le registre indexe par nom a disparu : le texte est dans l'entree.

    Ce que ce test remplace : `test_definitions.py`, qui verifiait que la
    table et le registre nommaient les memes stages. Deux listes a tenir
    d'accord, c'est ce qui pouvait desynchroniser ; il n'y en a plus qu'une.
    """
    carried = {s.skill: s.instructions for s in PIPELINE}
    assert carried["business-analyst"].strip()
    assert carried["code"].strip()
    # /create-test travaille contre un spec deja ecrit : le preambule et la
    # portee lui suffisent, et c'est declare en toutes lettres dans la table.
    assert carried["create-test"] == ""
