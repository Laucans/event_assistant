"""Ce que le raffinage etablit avant de payer quoi que ce soit.

Les quatre refus du precontrole, le round qu'il deduit, et le verrou. Rien
n'appelle `gh` : le double de `conftest` tient le depot sur papier.
"""

import io

import pytest

from pipeline.core.domain.outcomes.result import Status
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.workflows.common import labels
from pipeline.workflows.refinement.internals import refine
from pipeline.workflows.refinement.settings import RefinementConfig

BODY = ("## Business Goal\n\nLe but.\n\n"
        "## Technical\n\nLa technique.\n\n"
        "## Acceptance Criteria\n\n- un critere\n")


@pytest.fixture
def ws(tmp_path):
    """Le workspace du raffinage : `.llocal/refinement/` tombe dans tmp_path."""
    return Workspace(tmp_path)


@pytest.fixture
def said():
    return io.StringIO()


def config(ws, issue, **kw):
    return RefinementConfig(issue=issue, workspace=ws, **kw)


def run(cfg, said=None):
    """Le precontrole, et l'etat qu'il a rempli."""
    log = (logbook.open_logbook("test.refine", stream=said)
           if said is not None else logbook.null())
    state = refine.RefinementState()
    return refine.precheck(cfg, log, state), state


def task(hub, *extra, body=BODY, title="Une task"):
    return hub.add(title, labels.AGENT, labels.REFINEMENT, *extra, body=body)


# --- les quatre refus, avant toute depense ---------------------------------


def test_an_issue_gh_cannot_read_stops_instead_of_refining_nothing(hub, ws):
    got, state = run(config(ws, 404))
    assert got.failed and state.round_no == 0


def test_a_closed_issue_is_not_refined(hub, ws):
    number = task(hub)
    hub.close(number)
    got, _ = run(config(ws, number))
    assert got.status is Status.HALTED
    assert f"#{number} is closed" in got.reason


def test_an_issue_that_is_not_a_task_is_refused_and_says_which_label_to_add(
        hub, ws):
    """Un milestone raffine perdrait sa liste de sous-issues pour cinq sections."""
    number = hub.add("Le milestone", labels.MILESTONE, labels.REFINEMENT)
    got, _ = run(config(ws, number))
    assert got.status is Status.HALTED
    assert labels.AGENT in got.reason and labels.HUMAN in got.reason


def test_force_does_not_make_a_milestone_a_task(hub, ws):
    """`--force` leve l'etiquette manquante, jamais la nature de l'issue."""
    number = hub.add("Le milestone", labels.MILESTONE, labels.REFINEMENT)
    got, _ = run(config(ws, number, force=True))
    assert got.status is Status.HALTED
    assert labels.AGENT in got.reason


def test_an_issue_without_the_refinement_label_is_refused(hub, ws):
    number = hub.add("Une task", labels.AGENT, body=BODY)
    got, _ = run(config(ws, number))
    assert got.status is Status.HALTED
    assert labels.REFINEMENT in got.reason and "--force" in got.reason


def test_force_refines_an_issue_that_does_not_carry_the_label(hub, ws):
    number = hub.add("Une task", labels.AGENT, body=BODY)
    got, state = run(config(ws, number, force=True))
    assert got.ok and state.round_no == 1


def test_a_human_task_is_refined_like_an_agent_one(hub, ws):
    number = hub.add("Une action humaine", labels.HUMAN, labels.REFINEMENT)
    got, _ = run(config(ws, number))
    assert got.ok


# --- le compteur de rounds -------------------------------------------------


def test_an_issue_nobody_has_refined_starts_at_round_one(hub, ws):
    number = task(hub)
    _, state = run(config(ws, number))
    assert state.round_no == 1


def test_the_round_is_the_one_after_the_last_comment(hub, ws):
    number = task(hub)
    hub.comment(number, "refinement round: 1")
    hub.comment(number, "refinement round: 2")
    _, state = run(config(ws, number))
    assert state.round_no == 3


def test_a_comment_list_gh_could_not_read_never_reads_as_round_one(hub, ws):
    """« l'API est en panne » et « jamais raffinee » menent a l'oppose.

    Une lecture ratee lue comme « aucun commentaire » ferait repartir le
    compteur a 1, et le corps deja raffine serait reecrit par-dessus.
    """
    number = task(hub)
    hub.comment(number, "refinement round: 2")
    hub.fails_on = "comments"
    got, state = run(config(ws, number))
    assert got.failed, "une lecture ratee est passee pour un round 1"
    assert state.round_no == 0
    assert "comments" in got.reason


def test_the_round_travels_on_the_config_so_the_artifacts_carry_it(hub, ws):
    number = task(hub)
    hub.comment(number, "refinement round: 4")
    cfg = config(ws, number)
    run(cfg)
    assert cfg.round_no == 5 and cfg.artifact_tag(1) == "r05"


# --- ce que le precontrole pose dans l'etat --------------------------------


def test_the_body_already_written_is_read_as_sections(hub, ws):
    number = task(hub)
    _, state = run(config(ws, number))
    assert state.found == {"business-goal": "Le but.",
                           "technical": "La technique.",
                           "acceptance-criteria": "- un critere"}


def test_round_one_plans_the_three_sections_of_round_one(hub, ws):
    number = task(hub, body="je voudrais un bouton bleu")
    _, state = run(config(ws, number))
    assert state.wanted == ["business-goal", "technical",
                            "acceptance-criteria"]


def test_round_two_plans_what_round_one_left_out_and_its_own_two(hub, ws):
    number = task(hub)
    hub.comment(number, "refinement round: 1")
    _, state = run(config(ws, number))
    assert state.wanted == ["business-rules", "technical-plan"]


def test_a_late_round_with_a_context_leaves_the_plan_to_the_router(hub, ws):
    number = task(hub)
    for n in (1, 2):
        hub.comment(number, f"refinement round: {n}")
    _, state = run(config(ws, number, context="revois les criteres"))
    assert state.wanted == []


def test_the_issue_is_kept_in_the_state_for_the_steps_that_follow(hub, ws):
    number = task(hub)
    _, state = run(config(ws, number))
    assert state.issue.number == number and state.issue.has(labels.REFINEMENT)


def test_the_journal_names_the_round_and_the_sections_it_will_write(hub, ws,
                                                                    said):
    number = task(hub, body="je voudrais un bouton bleu")
    run(config(ws, number), said)
    assert f"refining #{number} — round 1" in said.getvalue()
    assert "business-goal technical acceptance-criteria" in said.getvalue()


def test_the_journal_says_when_the_router_is_the_one_deciding(hub, ws, said):
    number = task(hub)
    for n in (1, 2):
        hub.comment(number, f"refinement round: {n}")
    run(config(ws, number, context="revois les criteres"), said)
    assert "round 3 (router decides)" in said.getvalue()


def test_the_artifact_folder_of_the_issue_exists_before_a_stage_writes_in_it(
        hub, ws):
    number = task(hub)
    assert not (ws.refinement_dir / str(number)).exists()
    run(config(ws, number))
    assert (ws.refinement_dir / str(number)).is_dir()


def test_a_refusal_writes_nothing_at_all_on_github(hub, ws):
    """Un refus est justement le cas ou rien ne doit bouger sur l'issue."""
    number = hub.add("Une task", labels.AGENT, body=BODY)
    run(config(ws, number))
    assert hub.wrote() == []


# --- le verrou -------------------------------------------------------------


def test_two_refinements_of_the_same_issue_do_not_run_at_once(ws):
    """Deux rounds partis ensemble reecriraient le corps l'un par-dessus l'autre."""
    cfg = config(ws, 25)
    state = refine.RefinementState()
    with refine.one_at_a_time(cfg, state) as mine:
        assert mine is True
        with refine.one_at_a_time(cfg, state) as second:
            assert second is False


def test_another_issue_is_not_held_by_the_lock_of_this_one(ws):
    state = refine.RefinementState()
    with refine.one_at_a_time(config(ws, 25), state):
        with refine.one_at_a_time(config(ws, 26), state) as other:
            assert other is True


def test_the_lock_is_released_when_the_round_ends(ws):
    cfg = config(ws, 25)
    state = refine.RefinementState()
    with refine.one_at_a_time(cfg, state):
        pass
    assert not (ws.refinement_dir / ".lock-25").exists()


def test_what_a_held_lock_says_names_the_issue(ws):
    said = refine.already_running(config(ws, 25), refine.RefinementState())
    assert "#25" in said and "already running" in said


# --- la phrase de fin ------------------------------------------------------


def test_a_round_that_wrote_says_which_issue_and_which_round(ws):
    state = refine.RefinementState()
    state.round_no = 2
    assert refine.summary(config(ws, 25), state) == "refined #25 — round 2"


def test_a_dry_run_never_claims_to_have_written_anything(ws):
    state = refine.RefinementState()
    state.round_no = 2
    assert refine.summary(config(ws, 25, dry_run=True), state) == (
        "dry run — nothing written")


# --- ce qu'un appelant detache voit passer ---------------------------------


@pytest.fixture
def warned():
    """Le canal direct : ce que `warn` aurait imprime sur stderr."""
    return []


def test_an_issue_gh_could_not_read_is_said_on_the_direct_channel(hub, ws,
                                                                  warned):
    """Detache d'un declencheur, le fichier de log n'est ouvert par personne."""
    got, _ = run(config(ws, 404, warn=warned.append))
    assert got.failed and "404" in got.reason
    assert warned and "#404" in warned[0]


def test_comments_gh_could_not_read_are_said_on_the_direct_channel(hub, ws,
                                                                   warned):
    number = task(hub)
    hub.fails_on = "comments"
    got, _ = run(config(ws, number, warn=warned.append))
    assert got.failed and "comments" in got.reason
    assert warned and "comments" in warned[0] and f"#{number}" in warned[0]


def test_a_refusal_stays_off_the_direct_channel(hub, ws, warned):
    """Un refus vient d'une decision : le code de sortie et le journal le disent."""
    number = task(hub)
    hub.close(number)
    got, _ = run(config(ws, number, warn=warned.append))
    assert got.status is Status.HALTED
    assert warned == []


def test_an_issue_without_the_label_stays_off_the_direct_channel(hub, ws,
                                                                 warned):
    number = hub.add("Une task", labels.AGENT, body=BODY)
    got, _ = run(config(ws, number, warn=warned.append))
    assert got.status is Status.HALTED
    assert warned == []


def test_a_round_that_read_everything_warns_about_nothing(hub, ws, warned):
    number = task(hub)
    got, _ = run(config(ws, number, warn=warned.append))
    assert got.ok and warned == []
