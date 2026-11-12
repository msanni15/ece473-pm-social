"""Milestone II market-side tests. Synthetic fixtures only; network calls are monkeypatched."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import espn, ingame, polymarket  # noqa: E402

GS = pd.Timestamp("2026-10-22 23:00", tz="UTC")
GAME = pd.Series({"slug": "nba-aaa-bbb-2026-10-22", "game_start_utc": GS, "condition_id": "c1",
                  "token_home": "H", "token_away": "A"})


def _trade(ts, asset, side, size, price):
    return {"transactionHash": f"{ts}{asset}{side}", "asset": asset, "conditionId": "c1", "side": side,
            "size": size, "price": price, "timestamp": int(pd.Timestamp(ts).timestamp()),
            "ts": pd.Timestamp(ts)}


@pytest.fixture
def patched(monkeypatch):
    trades = pd.DataFrame([
        _trade("2026-10-22 23:20:10Z", "H", "BUY", 10, 0.60),   # +6 USD toward home
        _trade("2026-10-22 23:20:40Z", "A", "BUY", 10, 0.30),   # home price 0.70, -3 USD
        _trade("2026-10-22 23:22:05Z", "A", "SELL", 5, 0.20),   # home price 0.80, +1 USD
    ])
    monkeypatch.setattr(polymarket, "fetch_trades", lambda cid, s, e: trades[(trades.ts >= s) & (trades.ts <= e)])
    clob = pd.DataFrame({"ts": [pd.Timestamp("2026-10-22 23:21:30Z")], "p": [0.66]})
    monkeypatch.setattr(polymarket, "fetch_price_history", lambda tok, s, e, fidelity=60: clob)
    plays = pd.DataFrame({
        "ts": pd.to_datetime(["2026-10-22 23:15:00Z", "2026-10-22 23:20:30Z", "2026-10-23 01:30:00Z"]),
        "scoring_play": [False, True, False], "points": [0, 3, 0], "scoring_side": [None, "home", None],
        "score_home": [0, 3, 3], "score_away": [0, 0, 0], "sec_remaining": [2880, 2700, 0],
        "espn_wp_home": [0.5, 0.55, 1.0], "play_id": ["1", "2", "3"]})
    return plays


def test_trade_prices_are_home_probability_and_flow_signed(patched):
    tr = ingame.game_trades(GAME)
    assert tr.price_home.tolist() == pytest.approx([0.60, 0.70, 0.80])
    assert tr.flow_home.tolist() == pytest.approx([6.0, -3.0, 1.0])


def test_minute_price_last_trade_then_clob_then_ffill(patched):
    mm, _ = ingame.market_minutes(GAME, patched, ingame.game_trades(GAME))
    row = mm.set_index("minute")
    m20, m21, m22, m23 = (pd.Timestamp(f"2026-10-22 23:{x}Z") for x in ("20", "21", "22", "23"))
    assert row.loc[m20, "p_home"] == pytest.approx(0.70)  # end of minute, not the average
    assert row.loc[m20, "p_vwap"] == pytest.approx((10 * 0.6 + 10 * 0.7) / 20)  # share-weighted
    assert row.loc[m21, "price_source"] == "clob" and row.loc[m21, "p_home"] == pytest.approx(0.66)
    assert row.loc[m22, "price_source"] == "trades"
    assert row.loc[m23, "price_source"] == "ffill" and not row.loc[m23, "price_observed"]
    assert row.loc[m20, "pts_home"] == 3 and row.loc[m20, "score_diff"] == 3
    # ESPN win probability is missing before the first play rather than borrowed from later.
    assert np.isnan(row.loc[pd.Timestamp("2026-10-22 23:14Z"), "espn_wp_home"])
    assert row.loc[pd.Timestamp("2026-10-22 23:14Z"), "in_game"] == False  # noqa: E712
    assert row.loc[m20, "in_game"]


def test_targets_never_cross_final_buzzer(patched):
    mm, _ = ingame.market_minutes(GAME, patched, ingame.game_trades(GAME))
    panel = ingame.build_panel(mm, None)
    last_in_game = panel[panel.in_game].minute.max()
    assert np.isnan(panel.loc[panel.minute == last_in_game, "dlogit_next1"]).all()
    assert np.isnan(panel.loc[panel.minute == last_in_game - pd.Timedelta(minutes=4), "dlogit_next5"]).all()
    assert panel[panel.minute > last_in_game].dlogit_next1.isna().all()
    assert ingame.validate_panel(panel)["rows"] == len(panel)


def test_espn_clock_to_seconds_remaining():
    assert espn.sec_remaining(1, "12:00") == 2880
    assert espn.sec_remaining(4, "0:34.5") == pytest.approx(34.5)
    assert espn.sec_remaining(4, "16.9") == pytest.approx(16.9)
    assert espn.sec_remaining(5, "5:00") == 300
