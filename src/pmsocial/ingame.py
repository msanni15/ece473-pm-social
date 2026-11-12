"""Milestone II in-game minute panel: Polymarket prices/trades + ESPN game state (+ Bluesky).

Row `minute` covers [minute, minute + 1 min) in UTC. Values describe the minute (or its end)
and use only information time-stamped inside or before it:
  p_home       last trade price of the minute, as the home-win probability.
               CLOB 1-minute price points are irregular (gaps up to ~6 min in-game, verified
               2026-11-11) while trades occur in ~97-99% of in-game minutes, so trades are the
               main source; the minute's CLOB point is used when there is no trade, then
               forward fill (price_source = trades / clob / ffill). The END-of-minute price
               matters: the market moves within 5-10 s of a scoring play, so a within-minute
               average (p_vwap) or a mid-minute CLOB point (p_clob) lags the minute's scoring
               and makes next-minute changes spuriously predictable from it.
  n_trades,    taker trades / USDC notional (size * price) in the minute
  volume_usd
  flow_home    signed USDC: buying home (or selling away) is +, selling home (or buying away) is -
  score_*,     ESPN score / win probability after the last play inside the minute
  espn_wp_home
  pts_home/away points scored in the minute
"""
import numpy as np
import pandas as pd

from . import polymarket
from .config import INGAME_AFTER_MIN, INGAME_BEFORE_MIN

MIN = pd.Timedelta(minutes=1)
P_CLIP = 0.01  # log-odds are computed on prices clipped to [0.01, 0.99]


def window(game: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    gs = game.game_start_utc
    return gs - pd.Timedelta(minutes=INGAME_BEFORE_MIN), gs + pd.Timedelta(minutes=INGAME_AFTER_MIN)


def logit(p):
    p = np.clip(p, P_CLIP, 1 - P_CLIP)
    return np.log(p / (1 - p))


def game_trades(game: pd.Series) -> pd.DataFrame:
    """Second-level trades in the window, with every price expressed as the home-win probability."""
    start, end = window(game)
    tr = polymarket.fetch_trades(game.condition_id, start, end)
    tr = tr[tr.ts < end].copy()
    home = tr.asset == game.token_home
    tr["token_side"] = np.where(home, "home", np.where(tr.asset == game.token_away, "away", None))
    tr["price"] = tr.price.astype(float)
    tr["size"] = tr["size"].astype(float)
    tr["price_home"] = np.where(home, tr.price, 1 - tr.price)
    tr["usd"] = tr["size"] * tr.price
    buys_home = (home & (tr.side == "BUY")) | (~home & (tr.side == "SELL"))
    tr["flow_home"] = np.where(buys_home, tr.usd, -tr.usd)
    tr.insert(0, "slug", game.slug)
    return tr[["slug", "ts", "token_side", "side", "size", "price", "price_home", "usd", "flow_home",
               "conditionId", "asset", "transactionHash"]].reset_index(drop=True)


def market_minutes(game: pd.Series, plays: pd.DataFrame, trades: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    start, end = window(game)
    grid = pd.date_range(start, end - MIN, freq="min")
    out = pd.DataFrame({"slug": game.slug, "minute": grid})

    snaps = {}
    for side, tok in (("home", game.token_home), ("away", game.token_away)):
        ph = polymarket.fetch_price_history(tok, start, end, fidelity=1)
        ph = ph[(ph.ts >= start) & (ph.ts < end)]
        snaps[side] = ph.groupby(ph.ts.dt.floor("min")).p.last()
    trades = trades.sort_values("ts", kind="stable")
    g = trades.assign(minute=trades.ts.dt.floor("min"), w=trades["size"] * trades.price_home).groupby("minute")
    last = g.price_home.last().reindex(grid).to_numpy()
    vwap = (g.w.sum() / g["size"].sum()).reindex(grid)
    clob = snaps["home"].reindex(grid).to_numpy()
    out["p_vwap"] = vwap.ffill().to_numpy()
    out["p_clob"] = pd.Series(clob).ffill().to_numpy()
    out["price_source"] = np.where(~np.isnan(last), "trades", np.where(~np.isnan(clob), "clob", "ffill"))
    out["price_observed"] = out.price_source != "ffill"
    out["p_home"] = pd.Series(np.where(~np.isnan(last), last, clob)).ffill().to_numpy()
    out["logit_p"] = logit(out.p_home)

    out["n_trades"] = g.size().reindex(grid).fillna(0).to_numpy()
    out["volume_usd"] = g.usd.sum().reindex(grid).fillna(0.0).to_numpy()
    out["flow_home"] = g.flow_home.sum().reindex(grid).fillna(0.0).to_numpy()

    pl = plays.dropna(subset=["ts"]).sort_values("ts", kind="stable")
    pl = pl[(pl.ts >= start) & (pl.ts < end)]
    pm = pl.assign(minute=pl.ts.dt.floor("min")).groupby("minute")
    last = pm[["score_home", "score_away", "sec_remaining", "espn_wp_home"]].last().reindex(grid)
    # Before the first play: score 0-0 and a full game left; ESPN win prob stays missing.
    fill0 = {"score_home": 0, "score_away": 0, "sec_remaining": 4 * 720, "espn_wp_home": np.nan}
    for c, v in fill0.items():
        out[c] = last[c].ffill().fillna(v).to_numpy()
    out["score_diff"] = out.score_home - out.score_away
    for side in ("home", "away"):
        pts = pl[pl.scoring_side == side].assign(minute=lambda d: d.ts.dt.floor("min"))
        out[f"pts_{side}"] = pts.groupby("minute").points.sum().reindex(grid).fillna(0).to_numpy()
    tip, final = pl.ts.min(), pl.ts.max()
    out["in_game"] = (out.minute >= tip.floor("min")) & (out.minute <= final.floor("min"))

    both = pd.concat([snaps["home"], snaps["away"]], axis=1, keys=["h", "a"]).dropna()
    ing = out[out.in_game]
    checks = {
        "slug": game.slug, "tip_utc": tip, "final_play_utc": final,
        "final_score": f"{int(pl.score_away.iloc[-1])}-{int(pl.score_home.iloc[-1])} (away-home)",
        "n_plays": len(plays), "n_plays_no_wallclock": int(plays.ts.isna().sum()),
        "n_scoring_plays": int(pl.scoring_play.sum()),
        "plays_out_of_order": int((plays.dropna(subset=["ts"]).ts.diff().dt.total_seconds() < 0).sum()),
        "in_game_minutes": int(ing.shape[0]),
        "in_game_price_from_trades_share": round(float((ing.price_source == "trades").mean()), 3),
        "in_game_price_observed_share": round(float(ing.price_observed.mean()), 3),
        "clob_sum_dev_median": float((both.h + both.a - 1).abs().median()) if len(both) else np.nan,
        "clob_sum_dev_max": float((both.h + both.a - 1).abs().max()) if len(both) else np.nan,
        "trade_vs_clob_median_abs": round(float((ing.p_home - ing.p_clob)[ing.price_source == "trades"]
                                                .abs().median()), 4),
        "n_trades_window": len(trades), "n_trades_in_game": int(ing.n_trades.sum()),
        "trades_wrong_market": int((trades.conditionId != game.condition_id).sum()),
        "trades_unknown_asset": int(trades.token_side.isna().sum()),
    }
    return out, checks


REACTION_OFFSETS = (-60, -30, -10, 0, 5, 10, 20, 30, 60, 120)


def scoring_reaction(trades: pd.DataFrame, events: pd.DataFrame, offsets=REACTION_OFFSETS) -> pd.DataFrame:
    """Price move toward the scoring team around each scoring play, from second-level trades.

    For play time T (ESPN wall clock) the reference is the last trade price before T-60s; the
    value at offset s is the last trade price at or before T+s, signed so + favours the scorer.
    """
    ev = events[events.scoring_play & events.ts.notna()]
    rows = []
    for slug, e in ev.groupby("slug"):
        t = trades[trades.slug == slug].sort_values("ts", kind="stable")
        ts, p = t.ts.dt.tz_convert(None).to_numpy(), t.price_home.to_numpy()
        for r in e.assign(ts=e.ts.dt.tz_convert(None)).itertuples():
            i0 = np.searchsorted(ts, (r.ts - pd.Timedelta(seconds=60)).to_datetime64(), side="right") - 1
            if i0 < 0:
                continue
            sign = 1 if r.scoring_side == "home" else -1
            row = {"slug": slug, "play_id": r.play_id, "points": r.points}
            for s in offsets:
                i = np.searchsorted(ts, (r.ts + pd.Timedelta(seconds=s)).to_datetime64(), side="right") - 1
                row[s] = sign * (p[i] - p[i0])
            rows.append(row)
    return pd.DataFrame(rows)


def build_panel(market: pd.DataFrame, bsky: pd.DataFrame | None) -> pd.DataFrame:
    """Join the Bluesky minute file onto the market minutes; add next-minute and 5-minute targets."""
    df = market.copy()
    if bsky is not None:
        df = df.merge(bsky, on=["slug", "minute"], how="left", validate="one_to_one")
        assert len(df) == len(market)
    df = df.sort_values(["slug", "minute"]).reset_index(drop=True)
    g = df.groupby("slug")
    df["dlogit"] = g.logit_p.diff()
    for h in (1, 5):
        df[f"dlogit_next{h}"] = g.logit_p.shift(-h) - df.logit_p
        # A target that ends after the final buzzer is not used.
        df.loc[~g.in_game.shift(-h).fillna(False).astype(bool), f"dlogit_next{h}"] = np.nan
    return df


def validate_panel(df: pd.DataFrame) -> dict:
    assert not df.duplicated(["slug", "minute"]).any(), "duplicate (slug, minute)"
    assert str(df.minute.dt.tz) == "UTC"
    steps = df.groupby("slug").minute.diff().dropna()
    assert (steps == MIN).all(), "gaps in minute grid"
    assert df.p_home.dropna().between(0, 1).all()
    return {"rows": len(df), "games": df.slug.nunique(), "in_game_rows": int(df.in_game.sum()),
            "missing_p_home": int(df.p_home.isna().sum())}
