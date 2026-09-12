"""Les regles par route : ce qu'argparse ne sait pas exprimer."""

import argparse

import pytest

from pipeline.core.domain import stage_spec
from pipeline.launcher import routes, validation
from pipeline.launcher.cli import agentic_dev_loop as loop_cli
from pipeline.launcher.cli import pr_review as review_cli
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.workflows.agentic_dev_loop.stages import PIPELINE
from pipeline.workflows.pr_review.settings import ReviewConfig

LOOP = routes.find("loop")
REVIEW = routes.find("pr-review")
GUARD = routes.find("branch-guard")

TABLE = stage_spec.names(PIPELINE)


def config(route, **fields):
    """La config resolue que la validation examine, pour cette route."""
    if route is REVIEW:
        return ReviewConfig(**{"pr": "1", "base": "main_agent",
                               "level": "medium", **fields})
    return RunConfig(**fields)


def check(route, *, args=None, **fields) -> tuple[list[str], list[str]]:
    return validation.check(route, config(route, **fields),
                            args=argparse.Namespace(**(args or {})))


def errors(route, **fields) -> list[str]:
    return check(route, **fields)[0]


def warnings(route, **fields) -> list[str]:
    return check(route, **fields)[1]


def review(**fields) -> tuple[list[str], list[str]]:
    """La revue avec un `--level` valide par defaut."""
    return check(REVIEW, **fields)


def from_the_environment(route, argv=()):
    """La config qu'un vrai run batirait — flags ET environnement."""
    module = loop_cli if route is LOOP else review_cli
    return validation.check(route, module.config_to_check(
        module.parse_args(list(argv))))


# --- les refus -------------------------------------------------------------


def test_a_stage_that_is_not_in_the_table_is_refused():
    said = errors(LOOP, stages="analyst")
    assert len(said) == 1 and "'analyst'" in said[0]


def test_the_refusal_names_the_entries_of_the_real_table():
    said = errors(LOOP, stages="analyst")[0]
    for skill in TABLE.split():
        assert skill in said


def test_the_stages_of_the_table_pass():
    assert errors(LOOP, stages=TABLE) == []


@pytest.mark.parametrize("rounds", [0, -1])
def test_a_round_count_that_runs_nothing_is_refused(rounds):
    assert len(errors(LOOP, max_rounds=rounds)) == 1


@pytest.mark.parametrize("rounds", [None, 1, 3])
def test_a_usable_round_count_passes(rounds):
    assert errors(LOOP, max_rounds=rounds) == []


def test_an_unknown_effort_is_refused_before_the_round_starts():
    said = errors(LOOP, effort="turbo")
    assert len(said) == 1 and "turbo" in said[0]


@pytest.mark.parametrize("effort", stage_spec.EFFORTS)
def test_every_effort_of_the_domain_passes(effort):
    assert errors(LOOP, effort=effort) == []


def test_an_effort_left_empty_passes():
    assert errors(LOOP, effort=None) == [] and errors(LOOP, effort="") == []


@pytest.mark.parametrize("route", [LOOP, REVIEW])
def test_verbose_and_quiet_together_are_refused(route):
    said = errors(route, verbose=True, quiet=True)
    assert len(said) == 1 and "--verbose" in said[0]


@pytest.mark.parametrize("verbose, quiet", [(True, False), (False, True),
                                            (False, False)])
def test_one_verbosity_flag_at_a_time_passes(verbose, quiet):
    assert errors(LOOP, verbose=verbose, quiet=quiet) == []


def test_an_unknown_review_level_is_refused():
    said = review(level="turbo")[0]
    assert len(said) == 1 and "turbo" in said[0]


@pytest.mark.parametrize("level", validation.LEVELS)
def test_every_review_level_passes(level):
    assert review(level=level)[0] == []


@pytest.mark.parametrize("route", [LOOP, REVIEW])
def test_a_negative_heartbeat_is_refused(route):
    said = errors(route, heartbeat_s=-1.0)
    assert len(said) == 1 and "--heartbeat" in said[0]


@pytest.mark.parametrize("heartbeat", [0, 0.0, 60.0, None])
def test_a_heartbeat_of_zero_or_more_passes(heartbeat):
    assert errors(LOOP, heartbeat_s=heartbeat) == []


# --- les avertissements ----------------------------------------------------


def test_a_stage_list_without_code_warns_rather_than_refuses():
    said = check(LOOP, stages="business-analyst")
    assert said[0] == []
    assert len(said[1]) == 1 and "code" in said[1][0]


def test_a_stage_list_with_code_says_nothing():
    assert warnings(LOOP, stages="code create-test") == []


def test_no_stage_filter_at_all_says_nothing():
    assert warnings(LOOP, stages=None) == []


def test_migrate_names_the_flags_it_ignores():
    said = warnings(LOOP, args={"command": "migrate", "rounds": 2,
                                "stages": "code", "restart": True})
    assert len(said) == 1
    for flag in ("--rounds", "--stages", "--restart"):
        assert flag in said[0]
    assert "--model" not in said[0]


def test_migrate_on_its_own_says_nothing():
    assert warnings(LOOP, args={"command": "migrate",
                                "dry_run": True}) == []


def test_the_flags_migrate_ignores_say_nothing_without_migrate():
    assert warnings(LOOP, args={"command": None, "rounds": 2},
                    stages="code") == []


# --- la portee des regles --------------------------------------------------


def test_the_review_does_not_carry_the_loops_rules():
    assert review() == ([], [])


def test_a_hook_route_validates_nothing():
    assert validation.check(GUARD, argparse.Namespace()) == ([], [])


def test_check_reads_nothing_but_its_two_arguments(monkeypatch):
    """Ni environnement, ni disque : seuls ses deux arguments comptent."""
    monkeypatch.setenv("STAGES", "analyst")
    monkeypatch.setenv("MAX_ROUNDS", "0")
    monkeypatch.setenv("EFFORT", "turbo")
    assert validation.check(LOOP, argparse.Namespace()) == ([], [])


# --- l'environnement, valide au meme titre qu'un flag ----------------------


@pytest.mark.parametrize("variable, value, said", [
    ("STAGES", "analyst", "'analyst'"),
    ("MAX_ROUNDS", "0", "would run no task"),
    ("EFFORT", "turbo", "'turbo'"),
])
def test_a_bad_value_from_the_environment_is_refused_too(monkeypatch, variable,
                                                         value, said):
    monkeypatch.setenv(variable, value)
    errs, _ = from_the_environment(LOOP)
    assert len(errs) == 1 and said in errs[0]


@pytest.mark.parametrize("variable", ["STAGES", "MAX_ROUNDS", "EFFORT"])
def test_the_refusal_names_the_variable_as_well_as_the_flag(monkeypatch,
                                                            variable):
    monkeypatch.setenv(variable, {"STAGES": "analyst", "MAX_ROUNDS": "0",
                                  "EFFORT": "turbo"}[variable])
    assert variable in from_the_environment(LOOP)[0][0]


def test_a_flag_beats_the_environment_it_overrides(monkeypatch):
    monkeypatch.setenv("MAX_ROUNDS", "0")
    assert from_the_environment(LOOP, ["--rounds", "1"])[0] == []


@pytest.mark.parametrize("variable, value", [
    ("PR_REVIEW_LEVEL", "turbo"),
    ("PR_REVIEW_INLINE_EFFORT", "turbo"),
    ("PR_REVIEW_BRIEF_EFFORT", "turbo"),
])
def test_the_reviews_environment_is_refused_too(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    errs, _ = from_the_environment(REVIEW, ["12"])
    assert len(errs) == 1 and variable in errs[0]


def test_a_fast_path_builds_no_config_and_validates_nothing(monkeypatch):
    """`--costs` ne lit aucune des valeurs validees : il n'en batit pas."""
    monkeypatch.setenv("STAGES", "analyst")
    assert loop_cli.config_to_check(loop_cli.parse_args(["--costs"])) is None
    assert from_the_environment(LOOP, ["--costs"]) == ([], [])
