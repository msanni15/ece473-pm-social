"""Synthetic contract tests; no network requests or research-data substitutions."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import bluesky_ingame as social


TIP = pd.Timestamp("2026-10-23T23:00:00Z")


def fixtures():
    games = pd.DataFrame([{"slug": "nba-nyk-bos-2026-10-23", "home": "bos", "away": "nyk",
                           "game_start_utc": TIP}])
    start, end = social.game_window(games.iloc[0])
    windows = []
    for side, team, query in [("home", "bos", "Celtics"), ("away", "nyk", "Knicks")]:
        for since in pd.date_range(start, end, freq="h", inclusive="left"):
            windows.append({"slug": games.iloc[0].slug, "side": side, "team": team, "query": query,
                            "since": since.isoformat(), "until": min(since + pd.Timedelta(hours=1), end).isoformat(),
                            "status": "ok", "posts": []})
    return games, windows


def post(uri="at://post/1", created="2026-10-23T23:00:59Z", indexed="2026-10-23T23:01:02Z", text="ankle injury"):
    return {"uri": uri, "author": {"did": "did:plc:test", "handle": "test.invalid"},
            "record": {"createdAt": created, "text": text}, "indexedAt": indexed}


def test_failed_and_truncated_windows_are_missing_not_zero():
    games, windows = fixtures()
    windows[2]["status"] = "failed"
    windows[3]["status"] = "truncated"
    posts = social.build_posts(windows, games)
    minutes = social.build_minutes(games, windows, posts)
    failed = (minutes.minute >= TIP) & (minutes.minute < TIP + pd.Timedelta(hours=2))
    assert minutes.loc[failed, ["posts_home", "injury_home", "abn_home"]].isna().all().all()
    assert minutes.loc[failed, "posts_away"].eq(0).all()
    assert not minutes.loc[failed, "bsky_ok"].any()
    assert minutes.loc[~failed, "posts_home"].eq(0).all()
    assert len(minutes) == 330


def test_sort_at_binning_not_indexed_at_or_query_window():
    games, windows = fixtures()
    windows[2]["posts"] = [post(), post("at://post/2", "2026-10-23T23:03:03Z", "2026-10-23T23:02:59Z", "Celtics")]
    posts = social.build_posts(windows, games)
    minutes = social.build_minutes(games, windows, posts).set_index("minute")
    assert minutes.loc[TIP, "posts_home"] == 1
    assert minutes.loc[TIP, "injury_home"] == 1
    assert minutes.loc[TIP + pd.Timedelta(minutes=1), "posts_home"] == 0
    assert minutes.loc[TIP + pd.Timedelta(minutes=2), "posts_home"] == 1
    assert str(posts.sort_at.dtype) == "datetime64[ns, UTC]"


def test_dedup_across_queries_and_windows_but_preserve_sides():
    games, windows = fixtures()
    windows[2]["posts"] = [post(), post()]
    duplicate = dict(windows[2], query="Boston Celtics")
    windows.append(duplicate)
    windows[8]["posts"] = [post()]
    posts = social.build_posts(windows, games)
    assert len(posts) == 2
    assert set(posts.side) == {"home", "away"}
    minutes = social.build_minutes(games, windows, posts)
    assert minutes.posts_home.sum() == 1
    assert minutes.posts_away.sum() == 1


def test_abnormal_attention_is_fixed_pre_tip_baseline():
    games, windows = fixtures()
    windows[0]["posts"] = [post("at://pre", "2026-10-23T21:00:02Z", "2026-10-23T21:00:03Z")]
    windows[2]["posts"] = [post()]
    posts = social.build_posts(windows, games)
    minutes = social.build_minutes(games, windows, posts).set_index("minute")
    assert minutes.loc[TIP, "abn_home"] == pytest.approx(np.log(2) - np.log(2) / 120)
    assert minutes.loc[TIP, "imbalance"] == pytest.approx(np.log(2))


def test_missing_pre_tip_baseline_does_not_silently_use_partial_mean():
    games, windows = fixtures()
    windows[0]["status"] = "failed"
    minutes = social.build_minutes(games, windows, social.build_posts(windows, games))
    assert minutes.abn_home.isna().all()
    assert minutes.loc[minutes.minute >= TIP, "posts_home"].eq(0).all()


def test_missing_windows_are_not_assumed_successful():
    games, windows = fixtures()
    windows = windows[1:]
    minutes = social.build_minutes(games, windows, social.build_posts(windows, games))
    assert minutes.iloc[:60].posts_home.isna().all()


def test_alias_requires_passing_review_and_limit_one():
    checks = pd.DataFrame([{"team": "cle", "query": "Cavs", "n_reviewed": 20,
                            "n_relevant": 13, "approved": True}])
    with pytest.raises(ValueError, match="relevance"):
        social.approved_queries("cle", checks)
    checks.loc[0, "n_relevant"] = 14
    assert social.approved_queries("cle", checks) == ["Cavaliers", "Cavs"]


def test_cache_identity_includes_query_and_failed_windows_retry(tmp_path, monkeypatch):
    games, _ = fixtures()
    calls = []

    def fetch(query, since, until):
        calls.append(query)
        return [], "ok"

    monkeypatch.setattr(social, "_collect_window", fetch)
    social.collect_game(games.iloc[0], raw_dir=tmp_path)
    assert len(calls) == 12
    social.collect_game(games.iloc[0], raw_dir=tmp_path)
    assert len(calls) == 12
    checks = pd.DataFrame([{"team": "bos", "query": "Boston Celtics", "n_reviewed": 20,
                            "n_relevant": 20, "approved": True}])
    social.collect_game(games.iloc[0], checks, raw_dir=tmp_path)
    assert len(calls) == 18


def test_timing_lag_sign_and_exact_minute_pairs():
    from pmsocial import timing
    rng = np.random.default_rng(473)
    n = 150
    changes = rng.normal(0, 0.01, n)
    attention = np.r_[np.zeros(3), changes[:-3]]
    minutes = pd.date_range(TIP, periods=n, freq="min")
    panel = pd.DataFrame({"slug": "test", "minute": minutes, "dlogit": changes,
                          "posts_total": 10 + attention, "imbalance": attention, "in_game": True})
    summary, _ = timing.cross_correlations(panel)
    g = summary[summary.feature == "posts_total"]
    assert g.loc[g.correlation.idxmax(), "lag"] == 3  # market precedes attention
    assert g.loc[g.lag == 3, "correlation"].iloc[0] == pytest.approx(1)
    # Dropping a minute must not compress time and change the lag definition.
    summary, _ = timing.cross_correlations(panel.drop(index=30))
    assert summary.loc[(summary.feature == "posts_total") & (summary.lag == 3), "correlation"].iloc[0] == pytest.approx(1)


def test_timing_event_perspective_and_missing_windows():
    from pmsocial import timing
    minutes = pd.date_range(TIP, periods=40, freq="min")
    panel = pd.DataFrame({"slug": "test", "minute": minutes, "p_home": np.arange(40) / 100 + 0.3,
                          "posts_home": 2.0, "posts_away": 3.0})
    centers = pd.DataFrame({"slug": ["test", "test"], "minute": [minutes[15], minutes[0]],
                            "side": ["away", "home"]})
    curve, _, used = timing.event_study(panel, centers)
    assert len(used) == 1  # edge event lacks a complete window
    assert curve.loc[curve.lag == 0, "price_change_pp"].iloc[0] == pytest.approx(-1)
    assert curve.posts.eq(3).all()


def test_timing_differences_do_not_cross_gaps_or_unobserved_prices():
    from pmsocial import timing
    minutes = pd.DatetimeIndex([TIP, TIP + pd.Timedelta(minutes=1), TIP + pd.Timedelta(minutes=3), TIP + pd.Timedelta(minutes=4)])
    market = pd.DataFrame({"slug": "test", "minute": minutes, "p_home": [0.5, 0.6, 0.7, 0.8],
                           "logit_p": [0., 0.4, 0.8, 1.2], "price_observed": [True, True, True, False],
                           "in_game": True})
    social_data = pd.DataFrame({"slug": "test", "minute": minutes,
                                "posts_home": 1., "posts_away": 2., "imbalance": 0.})
    panel = timing.minute_panel(market, social_data)
    assert panel.dp.notna().tolist() == [False, True, False, False]
