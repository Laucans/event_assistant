"""L'entree du raffinage : les flags, l'environnement, la regle de validation.

Rien ici ne fait tourner un round. Ce qui est verifie est ce qui se decide
avant : quels modeles, quel effort, et ce qu'une valeur illisible fait.
"""

import argparse
import io
import subprocess
import sys

import pytest

from pipeline.core.domain import stage_spec
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.launcher import routes, validation
from pipeline.launcher.cli import refinement as cli
from pipeline.workflows.refinement.settings import RefinementConfig

ROOT = Workspace.here().root
REFINEMENT = routes.find("refinement")

# Les six couples du tableau des modeles : la variable, le champ qu'elle
# regle, et le defaut qu'elle remplace.
KNOBS = (("REFINEMENT_GOAL_MODEL", "goal_model", "opus"),
         ("REFINEMENT_TECHNICAL_MODEL", "technical_model", "opus"),
         ("REFINEMENT_CRITERIA_MODEL", "criteria_model", "sonnet"),
         ("REFINEMENT_RULES_MODEL", "rules_model", "opus"),
         ("REFINEMENT_PLAN_MODEL", "plan_model", "opus"),
         ("REFINEMENT_ROUTER_MODEL", "router_model", "sonnet"))

EFFORTS = (("REFINEMENT_GOAL_EFFORT", "goal_effort", "high"),
           ("REFINEMENT_TECHNICAL_EFFORT", "technical_effort", "high"),
           ("REFINEMENT_CRITERIA_EFFORT", "criteria_effort", "high"),
           ("REFINEMENT_RULES_EFFORT", "rules_effort", "high"),
           ("REFINEMENT_PLAN_EFFORT", "plan_effort", "high"),
           ("REFINEMENT_ROUTER_EFFORT", "router_effort", "low"))

ALL_VARS = [v for v, _, _ in KNOBS + EFFORTS] + ["REFINEMENT_MODEL"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Aucun reglage de la machine ne decide de ce que ces tests lisent."""
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)


def config(*argv) -> RefinementConfig:
    return cli.build_config(cli.parse_args(list(argv)))


# --- les flags -------------------------------------------------------------


def test_the_issue_is_the_only_thing_a_round_cannot_guess():
    assert config("25").issue == 25
    with pytest.raises(SystemExit):
        cli.parse_args([])


def test_an_issue_that_is_not_a_number_is_refused_by_argparse():
    with pytest.raises(SystemExit):
        cli.parse_args(["vingt-cinq"])


def test_the_defaults_of_a_round_nobody_configured():
    cfg = config("25")
    assert cfg.context == "" and not cfg.force and not cfg.dry_run
    assert not cfg.verbose and not cfg.quiet and cfg.heartbeat_s == 60.0
    assert cfg.round_no == 0


def test_the_flags_reach_the_config():
    cfg = config("25", "--context", "revois les criteres", "--force",
                 "--dry-run", "--verbose", "--heartbeat", "5")
    assert cfg.context == "revois les criteres"
    assert cfg.force and cfg.dry_run and cfg.verbose
    assert cfg.heartbeat_s == 5.0


def test_quiet_is_a_flag_of_its_own():
    assert config("25", "--quiet").quiet


def test_the_issue_names_the_files_this_round_leaves_behind():
    assert config("25").handle == "25"


def test_the_round_is_what_the_artifacts_of_a_round_are_named_after():
    cfg = config("25")
    cfg.round_no = 3
    assert cfg.artifact_tag(1) == "r03"


def test_the_workspace_is_the_repository_this_command_was_run_in():
    cfg = config("25")
    assert cfg.workspace.root == ROOT
    assert cfg.workspace.refinement_ledger == ROOT / ".llocal/refinement/costs.tsv"


# --- l'environnement -------------------------------------------------------


@pytest.mark.parametrize("variable, field, default", KNOBS)
def test_each_stage_has_its_own_model_and_its_own_variable(monkeypatch,
                                                           variable, field,
                                                           default):
    assert getattr(config("25"), field) == default
    monkeypatch.setenv(variable, "haiku")
    assert getattr(config("25"), field) == "haiku"


@pytest.mark.parametrize("variable, field, default", EFFORTS)
def test_each_stage_has_its_own_effort_and_its_own_variable(monkeypatch,
                                                            variable, field,
                                                            default):
    # Jamais le defaut : le poser prouverait qu'on lit la variable meme quand
    # elle n'est pas lue du tout.
    other = "high" if default != "high" else "low"
    assert getattr(config("25"), field) == default
    monkeypatch.setenv(variable, other)
    assert getattr(config("25"), field) == other


def test_one_variable_forces_the_same_model_on_the_six_stages(monkeypatch):
    """Le bouton qu'on tourne pour essayer un round entier au rabais."""
    monkeypatch.setenv("REFINEMENT_MODEL", "haiku")
    cfg = config("25")
    assert [getattr(cfg, field) for _, field, _ in KNOBS] == ["haiku"] * 6


def test_forcing_one_model_leaves_each_effort_alone(monkeypatch):
    monkeypatch.setenv("REFINEMENT_MODEL", "haiku")
    cfg = config("25")
    assert [getattr(cfg, field) for _, field, _ in EFFORTS] == (
        ["high"] * 5 + ["low"])


def test_the_forced_model_beats_the_per_stage_ones(monkeypatch):
    monkeypatch.setenv("REFINEMENT_MODEL", "haiku")
    monkeypatch.setenv("REFINEMENT_GOAL_MODEL", "opus")
    assert config("25").goal_model == "haiku"


# --- la validation ---------------------------------------------------------


def check(argv=("25",)):
    return validation.check(REFINEMENT,
                            cli.config_to_check(cli.parse_args(list(argv))))


def test_a_round_nobody_misconfigured_says_nothing():
    assert check() == ([], [])


@pytest.mark.parametrize("variable, field, default", EFFORTS)
def test_an_unknown_effort_is_refused_before_the_round_starts(monkeypatch,
                                                              variable, field,
                                                              default):
    """Un effort inconnu part jusqu'au fournisseur, qui refuse — apres l'appel."""
    monkeypatch.setenv(variable, "turbo")
    errs, _ = check()
    assert len(errs) == 1
    assert variable in errs[0] and "turbo" in errs[0]


@pytest.mark.parametrize("effort", stage_spec.EFFORTS)
def test_every_effort_of_the_domain_passes(monkeypatch, effort):
    monkeypatch.setenv("REFINEMENT_PLAN_EFFORT", effort)
    assert check()[0] == []


def test_verbose_and_quiet_together_are_refused():
    errs, _ = check(("25", "--verbose", "--quiet"))
    assert len(errs) == 1 and "--verbose" in errs[0]


def test_a_negative_heartbeat_is_refused():
    errs, _ = check(("25", "--heartbeat", "-1"))
    assert len(errs) == 1 and "--heartbeat" in errs[0]


def test_the_route_carries_no_rule_of_another_workflow(monkeypatch):
    """`--stages` et `--level` n'existent pas ici : leurs regles non plus."""
    monkeypatch.setenv("STAGES", "analyst")
    monkeypatch.setenv("PR_REVIEW_LEVEL", "turbo")
    assert check() == ([], [])


def test_every_rule_the_route_names_is_one_the_table_implements():
    assert set(REFINEMENT.rules) <= validation.RULES


# --- le --help -------------------------------------------------------------


def test_the_help_documents_every_variable_the_round_reads(capsys):
    """Un reglage indecouvrable est un reglage que personne ne tourne."""
    with pytest.raises(SystemExit):
        cli.parse_args(["--help"])
    out = capsys.readouterr().out
    for variable in ALL_VARS:
        assert variable in out


def test_the_help_documents_the_exit_codes(capsys):
    """Un declencheur lance le raffinage detache : le code est le seul signal."""
    with pytest.raises(SystemExit):
        cli.parse_args(["--help"])
    out = capsys.readouterr().out
    for code in ("0", "1", "2", "3", "4", "130"):
        assert "\n  %s " % code in out or "\n  %-4s" % code in out


def test_the_help_names_the_labels_an_issue_must_carry(capsys):
    with pytest.raises(SystemExit):
        cli.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "pipeline:refinement" in out
    assert "pipeline:agent" in out and "pipeline:human" in out


# --- ce qui reste quand tout casse -----------------------------------------


def test_an_unexpected_error_is_logged_instead_of_escaping(monkeypatch):
    """Lance detache par un hook, une trace nue partirait nulle part."""
    said = io.StringIO()
    monkeypatch.setattr(cli, "make_logger",
                        lambda issue, workspace, level=logbook.NORMAL:
                        logbook.open_logbook("test.refinement", stream=said))

    async def boom(argv=None):
        raise RuntimeError("un interne du SDK")

    monkeypatch.setattr(cli, "_main", boom)
    assert cli.main(["25"]) == 4
    written = said.getvalue()
    assert "CRASH" in written
    assert "Traceback (most recent call last):" in written
    assert "un interne du SDK" in written


def test_an_interruption_keeps_its_own_code(monkeypatch):
    async def stopped(argv=None):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "_main", stopped)
    assert cli.main(["25"]) == 130


def test_the_crash_log_is_named_after_the_issue_not_after_a_flag_value():
    """`--context x 25` nommait le log `x.log` : la seule trace d'un crash."""
    assert cli._issue_arg(["25"]) == "25"
    assert cli._issue_arg(["--context", "revois tout", "25"]) == "25"
    assert cli._issue_arg(["25", "--force"]) == "25"
    assert cli._issue_arg([]) == "unknown"


def test_the_api_key_is_dropped_at_import():
    """`claude -p` facture ce sous quoi il est authentifie : jamais une cle."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import os; from pipeline.launcher.cli import refinement;"
         " print(os.environ.get('ANTHROPIC_API_KEY'),"
         " os.environ.get('ANTHROPIC_AUTH_TOKEN'))"],
        capture_output=True, text=True, cwd=str(ROOT),
        env={"PATH": "/usr/bin:/bin",
             "ANTHROPIC_API_KEY": "sk-ne-doit-pas-survivre",
             "ANTHROPIC_AUTH_TOKEN": "tok-non-plus",
             "PYTHONPATH": str(ROOT / "pipeline" / "src")})
    assert r.stdout.strip() == "None None", r.stderr


def test_the_log_of_a_round_is_named_after_its_issue(tmp_path):
    log = cli.make_logger("25", Workspace(tmp_path))
    log("une ligne")
    assert (Workspace(tmp_path).refinement_dir / "25.log").exists()


@pytest.mark.parametrize("variable, field, default", EFFORTS)
def test_an_effort_set_but_left_empty_falls_back_to_the_default(monkeypatch,
                                                                variable,
                                                                field,
                                                                default):
    """Vide vaut absente : `StageSpec` levait, apres le preflight et le verrou."""
    monkeypatch.setenv(variable, "")
    assert getattr(config("25"), field) == default
