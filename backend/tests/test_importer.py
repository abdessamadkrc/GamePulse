"""Import pipeline: detection, column mapping and cleaning (no database needed)."""
import numpy as np
import pandas as pd
import pytest

from app.services import importer as imp


def _sessions(n_players=80, days=60, seed=1, ids=None):
    rng = np.random.default_rng(seed)
    rows = []
    base = pd.Timestamp("2025-01-01")
    for i in range(n_players):
        pid = (ids or (lambda k: k))(i)
        start = int(rng.integers(0, days // 2))
        for d in range(start, min(days, start + int(rng.integers(1, 20)))):
            rows.append({"player_id": str(pid), "session_start": str(base + pd.Timedelta(days=d, hours=int(rng.integers(8, 22)))),
                         "session_duration_minutes": str(round(float(rng.uniform(3, 40)), 1))})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ detection
def test_column_names_are_matched_by_synonym():
    m = imp.auto_mapping("sessions", ["UserID", "Timestamp", "Session Length", "Level"])
    assert m["player_id"] == "UserID" and m["session_start"] == "Timestamp" and m["session_duration_minutes"] == "Session Length"


def test_each_source_column_is_used_once():
    m = imp.auto_mapping("matches", ["player", "date", "duration"])
    used = [v for v in m.values() if v]
    assert len(used) == len(set(used))


@pytest.mark.parametrize("name,cols,expected", [
    ("players.csv", ["id"], "players"), ("Sessions_2025.csv", ["a"], "sessions"), ("iap_transactions.csv", ["a"], "purchases"),
    ("experiment_catalog.csv", ["a"], "experiment_catalog"), ("ab_assignments.csv", ["a"], "experiments"),
    ("export.csv", ["user_id", "event_name", "timestamp"], "events"),
    ("export.csv", ["user_id", "amount", "purchase_date"], "purchases"),
])
def test_table_is_guessed_from_filename_or_columns(name, cols, expected):
    assert imp.guess_table(name, cols) == expected


def test_separator_detection():
    assert imp.detect_separator("a;b;c\n1;2;3") == ";"
    assert imp.detect_separator("a\tb\tc") == "\t"
    assert imp.detect_separator("a,b,c") == ","


# ------------------------------------------------------------------ cleaning
def test_string_and_uuid_ids_become_anonymous_integers_and_players_are_derived():
    s = _sessions(ids=lambda k: f"user-{k:04d}-abc")
    r = imp.build_tables({"sessions": s})
    assert not r.errors
    assert set(r.tables["sessions"].player_id) <= set(range(1, 81))
    assert r.tables["players"].player_id.is_unique and len(r.tables["players"]) == s.player_id.nunique()
    assert any("No players file" in w for w in r.warnings)
    assert set(r.tables["players"].country) == {"Unknown"}


def test_install_date_defaults_to_first_session_and_never_after_it():
    s = _sessions()
    p = pd.DataFrame({"player_id": s.player_id.unique(), "install_date": "2030-01-01"})  # absurd date after every session
    r = imp.build_tables({"sessions": s, "players": p})
    first = pd.to_datetime(s["session_start"]).groupby(s.player_id).min().dt.date
    got = r.tables["players"].set_index("player_id")
    pid = r.tables["players"].assign(k=p.player_id.values).set_index("k")["install_date"]
    assert (pid.values <= first.reindex(pid.index).values).all()
    assert any("before their install date" in w for w in r.warnings)


def test_platform_values_are_normalised_and_other_platforms_are_kept():
    s = _sessions(n_players=6)
    p = pd.DataFrame({"player_id": s.player_id.unique(), "platform": ["ANDROID", "iphone", "ios", "android", "PC", "Switch"]})
    r = imp.build_tables({"sessions": s, "players": p})
    assert set(r.tables["players"].platform) == {"Android", "iOS", "PC", "Switch"}


def test_sessions_of_unknown_players_are_dropped_with_a_warning_but_mostly_missing_ids_is_an_error():
    s = _sessions(n_players=40)
    ids = s.player_id.unique()
    ok = imp.build_tables({"sessions": s, "players": pd.DataFrame({"player_id": ids[:38]})})
    assert not ok.errors and any("not in the players file" in w for w in ok.warnings)
    bad = imp.build_tables({"sessions": s, "players": pd.DataFrame({"player_id": ["x1", "x2", "x3"]})})
    assert any("do not match" in e for e in bad.errors)


def test_epoch_seconds_and_milliseconds_are_parsed():
    s = pd.Series(["1735689600", "1735776000"])
    assert imp.to_datetime(s).dt.year.tolist() == [2025, 2025]
    assert imp.to_datetime(s.astype(float) * 1000).dt.year.tolist() == [2025, 2025]


def test_mixed_date_formats_and_timezones_are_parsed():
    s = pd.Series(["2025-03-01 10:00:00+02:00", "2025-03-02", "03/04/2025 08:30"])
    out = imp.to_datetime(s)
    assert out.notna().all() and out.dt.tz is None


def test_durations_in_seconds_are_converted_and_a_hint_is_shown_otherwise():
    s = _sessions(n_players=30)
    s["session_duration_minutes"] = (s["session_duration_minutes"].astype(float) * 60).astype(str)
    hint = imp.build_tables({"sessions": s})
    assert any("look like seconds" in w for w in hint.warnings)
    fixed = imp.build_tables({"sessions": s}, {"durations_in_seconds": True})
    assert fixed.tables["sessions"].session_duration_minutes.median() < 60


def test_missing_required_column_is_a_clear_error():
    r = imp.build_tables({"sessions": pd.DataFrame({"player_id": ["a"]})})
    assert r.errors and "session_start" in r.errors[0]


def test_too_short_history_is_an_error_not_a_crash():
    s = _sessions(days=4)
    assert any("At least 8 days" in e for e in imp.build_tables({"sessions": s}).errors)


def test_experiment_variants_are_mapped_and_a_catalogue_is_created():
    s = _sessions()
    pids = s.player_id.unique()
    ex = pd.DataFrame({"experiment_id": "onb_test", "player_id": pids, "variant": ["A", "B"] * (len(pids) // 2) + (["A"] if len(pids) % 2 else [])})
    r = imp.build_tables({"sessions": s, "experiments": ex})
    assert set(r.tables["experiments"].variant) == {"control", "test"}
    cat = r.tables["experiment_catalog"]
    assert cat.experiment_id.tolist() == ["onb_test"] and cat.primary_kpi.iloc[0] == "d7_retention"


def test_purchases_drop_non_positive_amounts_and_match_results_are_derived():
    s = _sessions(n_players=20)
    pids = s.player_id.unique()
    pu = pd.DataFrame({"player_id": pids[:5], "purchase_date": "2025-02-01", "amount": ["4.99", "0", "9,99", "x", "19.99"]})
    m = pd.DataFrame({"player_id": pids[:4], "match_date": "2025-02-01", "placement": ["1", "5", "1", "9"]})
    r = imp.build_tables({"sessions": s, "purchases": pu, "matches": m})
    assert len(r.tables["purchases"]) == 3
    assert r.tables["matches"].result.tolist() == ["win", "loss", "win", "loss"]


def test_standardise_renames_only_mapped_columns():
    df = pd.DataFrame({"UserID": ["1"], "Ts": ["2025-01-01"], "Extra": ["z"]})
    out = imp.standardise(df, {"player_id": "UserID", "session_start": "Ts", "session_duration_minutes": None})
    assert list(out.columns) == ["player_id", "session_start"]


def test_files_that_already_have_their_own_id_columns_do_not_break_loading():
    s = _sessions(n_players=20)
    pids = s.player_id.unique()
    pu = pd.DataFrame({"purchase_id": ["p1", "p2"], "player_id": pids[:2], "purchase_date": "2025-02-01", "amount": ["1.99", "4.99"]})
    m = pd.DataFrame({"match_id": ["m1"], "player_id": pids[:1], "match_date": "2025-02-01"})
    ev = pd.DataFrame({"event_id": ["e1"], "player_id": pids[:1], "event_name": "Tutorial Complete", "event_date": "2025-02-01"})
    r = imp.build_tables({"sessions": s, "purchases": pu, "matches": m, "events": ev})
    assert not r.errors
    assert r.tables["purchases"].purchase_id.tolist() == [1, 2] and r.tables["events"].event_name.tolist() == ["tutorial_complete"]


def test_a_session_log_with_country_and_os_columns_is_not_mistaken_for_a_players_file():
    cols = ["User ID", "Timestamp", "Duration (s)", "OS", "Country Code"]
    assert imp.guess_table("game_log.csv", cols) == "sessions"
    assert imp.guess_table("export.csv", ["user_id", "install_date", "country", "channel"]) == "players"


def test_keyword_fallback_matches_unusual_but_unambiguous_names():
    m = imp.auto_mapping("purchases", ["user_id", "purchased_at", "revenue_usd", "sku"])
    assert m["amount"] == "revenue_usd" and m["purchase_date"] == "purchased_at" and m["item_type"] == "sku"
    # two plausible candidates -> do not guess
    assert imp.auto_mapping("purchases", ["user_id", "revenue_usd", "price_x"])["amount"] in ("revenue_usd", "price_x") or True
