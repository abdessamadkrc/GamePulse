"""Unit tests that need no database: pure statistics, decomposition maths and simulator invariants."""
import numpy as np
import pandas as pd
import pytest

from app.services.experiments import _mde_pp, _recommend, _test_kpi
from app.services.investigation import decompose, followup_test_design
from seed.simulate import DAYS, simulate


# ------------------------------------------------------------------ decomposition
def _frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 4000
    df = pd.DataFrame({
        "period": rng.choice(["previous", "current"], n),
        "country": rng.choice(["A", "B", "C"], n),
        "platform": rng.choice(["x", "y"], n),
    })
    base = 0.3 - 0.1 * ((df.period == "current") & (df.country == "A"))
    df["d7"] = (rng.random(n) < base).astype(float)
    return df


def test_contributions_sum_to_overall_change():
    df = _frame()
    dec = decompose(df, ["country", "platform"], "d7")
    overall = df[df.period == "current"].d7.mean() - df[df.period == "previous"].d7.mean()
    assert dec.contribution.sum() == pytest.approx(overall, abs=1e-12)


def test_rate_plus_mix_equals_contribution_when_both_periods_exist():
    dec = decompose(_frame(1), ["country"], "d7")
    assert (dec.rate_effect + dec.mix_effect).to_numpy() == pytest.approx(dec.contribution.to_numpy(), abs=1e-12)


def test_growing_low_quality_segment_is_a_drag_even_with_stable_rate():
    """A segment whose own retention does not change but whose share grows must show a NEGATIVE
    contribution when its retention is below the overall average (pure mix effect)."""
    rows = []
    for period, n_good, n_bad in (("previous", 900, 100), ("current", 600, 400)):
        rows += [{"period": period, "seg": "good", "d7": 1.0 if i < 0.4 * n_good else 0.0} for i in range(n_good)]
        rows += [{"period": period, "seg": "bad", "d7": 1.0 if i < 0.1 * n_bad else 0.0} for i in range(n_bad)]
    dec = decompose(pd.DataFrame(rows), ["seg"], "d7").set_index("seg")
    assert dec.loc["bad", "rate_effect"] == pytest.approx(0, abs=1e-9)
    assert dec.loc["bad", "mix_effect"] < 0
    assert dec.loc["bad", "contribution"] < 0


# ------------------------------------------------------------------ A/B statistics
def _ab(n=20000, p0=0.30, lift=0.05, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    v = np.where(np.arange(n) % 2 == 0, "control", "test")
    p = np.where(v == "test", p0 + lift, p0)
    return pd.DataFrame({"variant": v, "d7": (rng.random(n) < p).astype(float),
                         "sessions_7d": rng.poisson(5, n).astype(float)})


def test_significant_lift_is_detected_and_recommended():
    df = _ab(lift=0.05)
    k = _test_kpi(df, "d7_retention")
    k["significant_adj"] = True
    assert k["p_value"] < 0.001 and k["abs_diff"] > 0
    rec = _recommend(k, [], srm_ok=True, exp_name="x")
    assert rec["decision"] == "ship"


def test_null_effect_is_inconclusive_not_a_win():
    k = _test_kpi(_ab(lift=0.0, seed=11), "d7_retention")
    k["significant_adj"] = False
    rec = _recommend(k, [], srm_ok=True, exp_name="x")
    assert rec["decision"] == "inconclusive"


def test_srm_failure_blocks_a_decision():
    k = _test_kpi(_ab(lift=0.05), "d7_retention")
    assert _recommend(k, [], srm_ok=False, exp_name="x")["decision"] == "investigate"


def test_guardrail_regression_blocks_rollout():
    k = _test_kpi(_ab(lift=0.05), "d7_retention")
    guard = {"label": "Revenue", "significant_adj": True, "abs_diff": -1.0, "higher_is_better": True}
    assert _recommend(k, [guard], srm_ok=True, exp_name="x")["decision"] == "hold"


def test_mde_shrinks_with_sample_size():
    assert _mde_pp(0.3, 20000, 20000) < _mde_pp(0.3, 2000, 2000)


def test_test_design_scales_inversely_with_effect():
    d = followup_test_design(seg_cur_n=1400, window=28, baseline=0.10)
    big, small = d["options"][1], d["options"][0]
    assert big["n_per_arm"] < small["n_per_arm"]


# ------------------------------------------------------------------ simulator
@pytest.fixture(scope="module")
def sim():
    return simulate(3000, seed=5)


def test_simulator_is_deterministic():
    a, b = simulate(500, seed=9), simulate(500, seed=9)
    assert a["sessions"].equals(b["sessions"]) and a["purchases"].equals(b["purchases"])


def test_referential_integrity(sim):
    pids = set(sim["players"].player_id)
    for t in ("sessions", "matches", "purchases", "events", "experiments"):
        assert set(sim[t].player_id) <= pids, t


def test_every_player_has_an_install_day_session(sim):
    s = sim["sessions"].merge(sim["players"][["player_id", "install_date"]], on="player_id")
    day0 = s[s.session_start.dt.date == s.install_date]
    assert day0.player_id.nunique() == len(sim["players"])


def test_nothing_happens_after_the_data_window(sim):
    end = pd.Timestamp(sim["meta"].set_index("key").loc["max_date", "value"]) + pd.Timedelta(days=1)
    assert sim["sessions"].session_start.max() < end and sim["events"].event_date.max() < end


def test_experiment_assignment_is_single_arm_per_player(sim):
    e = sim["experiments"]
    assert not e.duplicated(["experiment_id", "player_id"]).any()
    assert set(e.variant) == {"control", "test"}


def test_data_is_labelled_synthetic(sim):
    assert "SYNTHETIC" in sim["meta"].set_index("key").loc["data_label", "value"]
    assert DAYS == 120


# ------------------------------------------------------------------ cohort explorer
def test_explorer_contributions_sum_exactly_to_overall_change():
    from app.services.explorer import contributions
    agg = pd.DataFrame({
        "grp": ["a", "b", "c"],
        "n_prev": [500, 300, 200], "ret_prev": [150, 90, 40],
        "n_cur": [400, 300, 500], "ret_cur": [120, 100, 80],
    })
    out = contributions(agg)
    overall = agg.ret_cur.sum() / agg.n_cur.sum() - agg.ret_prev.sum() / agg.n_prev.sum()
    assert out.contribution.sum() == pytest.approx(overall, abs=1e-12)
    # group c grew a lot and retains below average -> it must be the biggest drag
    assert out.set_index("grp").contribution.idxmin() == "c"


def test_explorer_significance_needs_enough_players_and_detects_real_change():
    from app.services.explorer import _significance
    assert _significance(20, 5, 500, 100) == (None, None, None)
    lo, hi, p = _significance(2000, 600, 2000, 450)   # 30% -> 22.5%
    assert hi < 0 and p < 0.001
    lo, hi, p = _significance(2000, 600, 2000, 606)   # essentially unchanged
    assert lo < 0 < hi and p > 0.05


def test_explorer_drop_stats_finds_steepest_day_after_day_one():
    from app.services.explorer import _drop_stats
    pts = [{"day": 0, "rate": 1.0}, {"day": 1, "rate": 0.5}, {"day": 2, "rate": 0.45},
           {"day": 3, "rate": 0.30}, {"day": 4, "rate": 0.28}]
    s = _drop_stats(pts)
    assert s["day1_loss"] == pytest.approx(0.5)
    assert s["steepest_day"] == 3
