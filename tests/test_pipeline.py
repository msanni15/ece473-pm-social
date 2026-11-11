"""Logic tests on SYNTHETIC fixtures. These never touch or substitute research data."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import bluesky, gdelt, integrate, models, polymarket  # noqa: E402

UTC = "UTC"
T0 = pd.Timestamp("2026-10-20 00:00", tz=UTC)


def _game(gs="2026-10-20 06:00"):
    return pd.Series({"slug": "nba-aaa-bbb-2026-10-20", "condition_id": "0xc", "token_home": "H",
                      "token_away": "A", "home": "lal", "away": "lac",
                      "game_start_utc": pd.Timestamp(gs, tz=UTC), "market_created_utc": T0})


def test_candidate_maps_tokens_by_label_not_position():
    ev = {"id": "1", "slug": "nba-lac-lal-2026-10-23", "markets": [{
        "sportsMarketType": "moneyline", "id": "m", "conditionId": "0xc", "question": "q",
        "outcomes": json.dumps(["Lakers", "Clippers"]),  # home listed first on purpose
        "clobTokenIds": json.dumps(["TOK_LAL", "TOK_LAC"]), "volume": "1",
        "gameStartTime": "2026-10-24 02:00:00+00", "createdAt": "2026-10-17T06:51:09Z"}]}
    row = polymarket.candidate_table([ev]).iloc[0]
    assert row.token_home == "TOK_LAL" and row.token_away == "TOK_LAC"
    assert row.game_start_utc == pd.Timestamp("2026-10-24 02:00", tz=UTC)


def test_market_panel_end_of_hour_and_pregame_only(monkeypatch):
    # snapshots at hh:00:30 with price = hour index / 100
    snaps = pd.DataFrame({"ts": [T0 + pd.Timedelta(hours=h, seconds=30) for h in range(9)]})
    snaps["p"] = [h / 100 for h in range(9)]
    monkeypatch.setattr(polymarket, "fetch_price_history",
                        lambda tok, s, e: snaps.assign(p=snaps.p if tok == "H" else 1 - snaps.p))
    trades = pd.DataFrame({"ts": [T0 + pd.Timedelta(minutes=10), T0 + pd.Timedelta(hours=6, minutes=1)],
                           "size": [10.0, 99.0], "price": [0.5, 0.5], "conditionId": "0xc", "asset": "H"})
    monkeypatch.setattr(polymarket, "fetch_trades", lambda c, s, e: trades)
    out, chk = polymarket.hourly_market_panel(_game())
    assert list(out.hour) == list(pd.date_range(T0, periods=6, freq="h"))  # t+1h <= 06:00
    # row t carries the snapshot taken at t+1h
    assert out.p_home_obs.iloc[0] == pytest.approx(0.01)
    # last row (05:00) would need the 06:00:30 snapshot, which is after start -> excluded
    assert np.isnan(out.p_home_obs.iloc[-1]) and out.p_home.iloc[-1] == pytest.approx(0.05)
    assert out.volume_usd.iloc[0] == 5.0 and out.volume_usd.sum() == 5.0  # post-start trade dropped
    assert chk["max_abs_sum_dev"] == pytest.approx(0)


def test_bluesky_failed_window_is_nan_not_zero():
    w = pd.DataFrame({"team": ["lal"] * 3, "hour": [T0.isoformat(), (T0 + pd.Timedelta(hours=1)).isoformat(),
                                                     (T0 + pd.Timedelta(hours=2)).isoformat()],
                      "status": ["ok", "ok", "failed"],
                      "posts": [[{"uri": "u1"}, {"uri": "u2"}], [], []]})
    posts = bluesky.posts_table(w.assign(posts=[[{"uri": "u1", "created_at": None, "indexed_at": None}] * 2, [], []]))
    assert len(posts) == 1  # duplicate uri removed
    c = bluesky.hourly_counts(w, posts)
    assert c.bsky_posts.tolist()[:2] == [1.0, 0.0] and np.isnan(c.bsky_posts.iloc[2])


def test_abnormal_attention_uses_only_past():
    hours = pd.date_range(T0, periods=100, freq="h")
    base = pd.DataFrame({"team": "lal", "hour": hours, "bsky_posts": np.arange(100.0), "status": "ok"})
    a = bluesky.abnormal_attention(base)
    changed = base.copy()
    changed.loc[60:, "bsky_posts"] = 1e6  # alter the future
    b = bluesky.abnormal_attention(changed)
    pd.testing.assert_series_equal(a.bsky_abnormal[:60], b.bsky_abnormal[:60])
    assert a.bsky_abnormal[:24].isna().all()  # needs >= 24 past hours


def test_gdelt_hour_assignment_and_incomplete_hours():
    stamps = pd.date_range(T0 + pd.Timedelta(minutes=15), T0 + pd.Timedelta(hours=2), freq="15min")
    man = pd.DataFrame({"file_ts": stamps, "status": "ok", "n_articles": 100})
    man.loc[man.file_ts == T0 + pd.Timedelta(hours=1, minutes=30), "status"] = "missing"
    art = pd.DataFrame({"file_ts": [T0 + pd.Timedelta(hours=1)], "team": ["lal"], "url": ["x"]})
    h = gdelt.hourly_counts(man, art, ["lal"]).set_index("hour")
    assert h.loc[T0, "gdelt_articles"] == 1.0  # file stamped 01:00 covers (00:45, 01:00]
    assert np.isnan(h.loc[T0 + pd.Timedelta(hours=1), "gdelt_articles"])


def test_team_patterns_avoid_ambiguous_nicknames():
    assert gdelt.PATTERNS["mia"].search("miami heat beat the bucks")
    assert not gdelt.PATTERNS["mia"].search("record heat wave")
    assert gdelt.PATTERNS["lal"].search("lakers win")


def _panel():
    out = []
    for slug, gs in [("nba-lac-lal-2026-10-20", "2026-10-20 05:00"), ("nba-bos-nyk-2026-10-20", "2026-10-20 05:00")]:
        g = _game(gs)
        g["slug"] = slug
        hours = pd.date_range(T0, periods=5, freq="h")
        mk = pd.DataFrame({"hour": hours, "p_home": [0.5, 0.52, 0.51, 0.55, 0.54], "price_observed": True,
                           "n_trades": 1, "volume_usd": [1.0, 2.0, 3.0, 4.0, 5.0]})
        soc = pd.DataFrame({"team": "lal", "hour": hours, "bsky_posts": 1.0, "bsky_abnormal": 0.0, "status": "ok"})
        soc = pd.concat([soc, soc.assign(team="lac")])
        gd = pd.DataFrame({"team": ["lal", "lac"] * 5, "hour": hours.repeat(2), "gdelt_articles": 2.0})
        out.append(integrate.build_game_panel(g, mk, soc, gd))
    return pd.concat(out, ignore_index=True)


def test_targets_are_next_hour_within_game():
    p = _panel()
    g = p[p.slug == p.slug.iloc[0]]
    assert g.abs_dp_next.iloc[0] == pytest.approx(abs(0.52 - 0.50))  # change over hour 1
    assert np.isnan(g.abs_dp_next.iloc[-1])  # no borrowing from the next game or in-game hour
    assert g.hours_to_game.iloc[0] == 4.0
    integrate.validate_panel(p)


def test_validate_rejects_rows_after_start():
    p = _panel()
    p.loc[0, "game_start_utc"] = T0  # first row now ends after start
    with pytest.raises(AssertionError):
        integrate.validate_panel(p)


def test_logo_split_never_shares_games():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"slug": np.repeat(list("abcd"), 20), "x": rng.normal(size=80)})
    df["y"] = df.x + rng.normal(size=80)
    res = models.evaluate(df, "y", {"m": ["x"]})
    assert res.test_game.nunique() == 4 and (res.groupby("test_game").n_test.first() == 20).all()
