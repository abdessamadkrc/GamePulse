"""Experiment Hub: planner maths and the monitor's novelty check (no database needed)."""
import pytest

from app.services.experiment_hub import _fade, plan
from app.services.investigation import followup_test_design
from app.services.power import mde_pp, sample_size_control


def test_bigger_lift_needs_fewer_players():
    assert sample_size_control(0.3, 5) < sample_size_control(0.3, 2) < sample_size_control(0.3, 1)


def test_more_power_or_stricter_alpha_needs_more_players():
    base = sample_size_control(0.3, 3)
    assert sample_size_control(0.3, 3, power=0.9) > base
    assert sample_size_control(0.3, 3, alpha=0.01) > base


def test_mde_and_sample_size_are_inverses():
    n = sample_size_control(0.25, 4)
    assert mde_pp(0.25, n, n) == pytest.approx(4, abs=0.1)


def test_investigation_and_planner_quote_the_same_sample_size():
    n_inv = followup_test_design(seg_cur_n=1400, window=28, baseline=0.10)["options"][1]["n_per_arm"]
    n_plan = plan("d7", 0.10, 5, 0.8, 0.05, daily=50, arms=2, test_share=0.5)["result"]["n_control"]
    assert n_inv == n_plan


def test_plan_duration_and_readout_day():
    r = plan("d7", 0.30, 3, 0.8, 0.05, daily=200, arms=2, test_share=0.5)["result"]
    assert r["enrol_days"] == pytest.approx(r["total"] / 200, abs=1)
    assert r["readout_day"] == r["enrol_days"] + 7          # D7 must mature for the last enrolee


def test_multi_arm_splits_alpha_and_needs_more_players():
    two = plan("conversion_14d", 0.05, 1, 0.8, 0.05, daily=400, arms=2, test_share=0.5)
    three = plan("conversion_14d", 0.05, 1, 0.8, 0.05, daily=400, arms=3, test_share=0.5)
    assert three["inputs"]["alpha_per_comparison"] == pytest.approx(0.025)
    assert three["result"]["total"] > two["result"]["total"]


def test_long_test_gets_a_warning_and_measurement_plan_forbids_peeking():
    r = plan("d7", 0.30, 1, 0.8, 0.05, daily=50, arms=2, test_share=0.5)
    assert r["warnings"], "a multi-month test should warn the planner"
    assert any("peeking" in s.lower() for s in r["measurement_plan"]["stop_rules"])
    assert len(r["measurement_plan"]["guardrails"]) >= 2


def _lift_rows(rel_by_day):
    rows = []
    for day, rel in rel_by_day.items():
        nc = nt = 5000
        rc = int(nc * 0.4 / (1 + day * 0.1))
        rt = int(rc * (1 + rel))
        rows.append({"day": day, "n_control": nc, "ret_control": rc, "n_test": nt, "ret_test": rt})
    return rows


def test_novelty_check_flags_a_fading_relative_lift():
    fading = _lift_rows({d: (0.20 if d <= 3 else 0.02) for d in range(1, 15)})
    assert _fade(fading)["flag"] is True


def test_novelty_check_ignores_normal_decay_of_absolute_lift():
    steady_relative = _lift_rows({d: 0.15 for d in range(1, 15)})   # absolute gap shrinks, relative is constant
    assert _fade(steady_relative)["flag"] is False
