"""The measurements: legible formats, and a tally that does not lie."""

import pytest

from pipeline.runtime.monitoring import metrics


@pytest.mark.parametrize("ms, expected", [
    (None, "?"), (0, "0s"), (900, "0s"), (42_000, "42s"),
    (59_999, "59s"), (60_000, "1m00s"), (433_000, "7m13s"),
    (3_600_000, "1h00m"), (5_040_000, "1h24m"),
])
def test_durations_read_at_a_glance(ms, expected):
    assert metrics.duration(ms) == expected


@pytest.mark.parametrize("n, expected", [
    (None, "?"), (0, "0"), (934, "934"), (1000, "1k"),
    (117_000, "117k"), (999_499, "999k"), (1_240_000, "1.2M"),
])
def test_token_counts_stay_short(n, expected):
    assert metrics.tokens(n) == expected


def test_cache_ratio_counts_every_input_token():
    usage = {"input_tokens": 10_000, "cache_read_input_tokens": 90_000,
             "cache_creation_input_tokens": 0}
    assert metrics.cache_ratio(usage) == pytest.approx(0.9)


def test_cache_ratio_is_unknown_rather_than_zero_when_there_is_no_usage():
    assert metrics.cache_ratio(None) is None
    assert metrics.cache_ratio({}) is None
    assert metrics.cache_ratio({"input_tokens": 0}) is None


def test_a_stage_line_carries_the_four_numbers_that_matter():
    line = metrics.stage_line(
        "code", 0.9814, 433_000, 34,
        {"input_tokens": 11_000, "cache_read_input_tokens": 117_000,
         "cache_creation_input_tokens": 4_000, "output_tokens": 12_400})
    assert line == ("/code done — $0.9814 · 7m13s · 34 turns · "
                    "132k in (89% cache) · 12k out")


def test_a_stage_line_survives_a_result_with_no_usage():
    assert metrics.stage_line("x", None, None, None, None) == "/x done — $0.0000 · ?"


def test_the_tally_adds_up_and_names_the_most_expensive_stage():
    t = metrics.Tally()
    t.add("code", 1.0, 60_000, {"input_tokens": 1000, "output_tokens": 100,
                                "cache_read_input_tokens": 9000})
    t.add("create-test", 0.25, 30_000, {"input_tokens": 500, "output_tokens": 50})
    assert t.stages == 2
    assert t.cost == pytest.approx(1.25)
    assert t.tokens_in == 10_500 and t.tokens_out == 150
    assert t.cache_pct == 86
    summary = t.summary("loop")
    assert summary.startswith("loop — $1.2500 · 1m30s (wall 0s) · 2 stage(s)")
    assert "priciest: /code $1.0000" in summary


def test_merging_a_round_into_the_run_keeps_every_number():
    run, rnd = metrics.Tally(), metrics.Tally()
    run.add("code", 1.0, 1000, {"input_tokens": 10, "output_tokens": 1})
    rnd.add("code", 2.0, 2000, {"input_tokens": 20, "output_tokens": 2})
    rnd.add("create-test", 0.5, 500, None)
    run.merge(rnd)
    assert run.stages == 3
    assert run.cost == pytest.approx(3.5)
    assert run.duration_ms == 3500
    assert run.by_stage == {"code": pytest.approx(3.0), "create-test": 0.5}


def test_an_empty_tally_says_nothing_misleading():
    t = metrics.Tally()
    assert t.cache_pct is None
    assert t.summary("loop") == "loop — $0.0000 · 0s (wall 0s) · 0 stage(s)"


def test_the_running_total_is_short_enough_to_read_between_stages():
    t = metrics.Tally()
    t.add("code", 0.98, 433_000, None)
    assert t.running() == "running total — $0.9800 over 1 stage(s), 7m13s (wall 0s)"


def test_zero_and_unknown_are_not_the_same_measurement():
    """D5: `if not ms` reported a sub-second stage as unknown."""
    assert metrics.duration(0) == "0s"       # il a tourne, tres vite
    assert metrics.duration(None) == "?"     # on ne sait pas
    assert metrics.tokens(0) == "0"          # aucun token
    assert metrics.tokens(None) == "?"       # aucun compteur
