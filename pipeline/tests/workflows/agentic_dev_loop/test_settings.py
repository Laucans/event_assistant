"""`RunConfig` : les filtres et les surcharges, appliques a la table.

Separe de `test_stages.py` comme les deux modules le sont : la
table est un design, la config est un etat de run lu dans l'environnement.
"""

import pytest

from pipeline.workflows.agentic_dev_loop.stages import PIPELINE
from pipeline.workflows.agentic_dev_loop.settings import (
    ConfigError, RunConfig)


def test_stage_filter_selects_a_subset():
    cfg = RunConfig(stages="code create-test")
    assert [s.skill for s in PIPELINE if cfg.enabled(s)] == [
        "code", "create-test"]


def test_no_filter_enables_everything():
    cfg = RunConfig(stages="")
    assert all(cfg.enabled(s) for s in PIPELINE)


def test_model_override_applies_to_every_stage_and_keeps_the_lead():
    cfg = RunConfig(model="sonnet")
    resolved = [cfg.resolve(s) for s in PIPELINE]
    assert {r.model for r in resolved} == {"sonnet"}
    assert [r.effort for r in resolved] == [s.effort for s in PIPELINE]
    assert resolved[1].lead == "/tech-analyst"


def test_effort_override_alone_leaves_the_models_alone():
    cfg = RunConfig(effort="low")
    resolved = [cfg.resolve(s) for s in PIPELINE]
    assert {r.effort for r in resolved} == {"low"}
    assert [r.model for r in resolved] == [s.model for s in PIPELINE]


def test_without_override_resolve_is_identity():
    cfg = RunConfig()
    assert all(cfg.resolve(s) is s for s in PIPELINE)


def test_summary_reads_like_the_shell_line():
    assert RunConfig().summary() == (
        "business-analyst(opus/high) -> code(opus/high) -> "
        "create-test(sonnet/high)")


def test_the_filtered_out_stages_can_be_named(monkeypatch):
    """A5: a silent skip is the classic "why did nothing happen" trap."""
    monkeypatch.delenv("STAGES", raising=False)
    assert RunConfig(stages="code").filtered_out() == [
        "business-analyst", "create-test"]
    assert RunConfig(stages="").filtered_out() == []


# --- ce que l'environnement peut contenir de travers ----------------------

def test_an_empty_numeric_variable_falls_back_to_its_default(monkeypatch):
    """`${MAX_ROUNDS:-3}` du shell traitait le vide comme absent."""
    monkeypatch.setenv("MAX_ROUNDS", "")
    monkeypatch.setenv("HEARTBEAT_SECONDS", "")
    cfg = RunConfig()
    assert cfg.max_rounds == 3 and cfg.heartbeat_s == 60.0


def test_a_nonsense_numeric_variable_says_which_one_it_is(monkeypatch):
    """Un `int()` nu sortait en trace, sans nommer la variable fautive.

    La seule chose que ce paquet leve encore, et pour une raison qui tient a
    ce cas precis : une config qui ne se construit pas n'a pas d'objet a qui
    rendre un `Result`.
    """
    monkeypatch.setenv("MAX_ROUNDS", "beaucoup")
    with pytest.raises(ConfigError, match="MAX_ROUNDS"):
        RunConfig()
    assert "beaucoup" in str(pytest.raises(ConfigError, RunConfig).value)
