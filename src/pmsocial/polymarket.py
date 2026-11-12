"""Polymarket collection: game-market selection, hourly prices, and trades.

APIs (no authentication required, verified 2026-10-27):
  Gamma  /events             event + market metadata
  CLOB   /prices-history     per-token price time series
  Data   /v2/trades          executed trades, newest first, cursor pagination. Time
                             filters are ignored, so we page back past the start time.
                             (/trades v1 was retired with HTTP 410 by 2026-11-11.)
"""
import json
import re

import numpy as np
import pandas as pd

from . import apilog
from .config import (CLOB_API, DATA_API, DATA_RAW, GAMMA_API, MIN_MONEYLINE_VOLUME,
                     MIN_PREGAME_PRICE_HOURS, N_GAMES, SAMPLE_GAME_DATES, TEAMS)

RAW = DATA_RAW / "polymarket"
SLUG_RE = re.compile(r"^nba-([a-z]{3})-([a-z]{3})-(\d{4}-\d{2}-\d{2})$")


def _save(name: str, obj) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(obj))


def _load(name: str):
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def _to_utc(s) -> pd.Timestamp:
    return pd.Timestamp(s).tz_convert("UTC") if pd.Timestamp(s).tzinfo else pd.Timestamp(s, tz="UTC")


# ---------------------------------------------------------------- metadata
def fetch_nba_game_events(refresh: bool = False) -> list[dict]:
    """All closed NBA single-game events whose slug date lies in SAMPLE_GAME_DATES."""
    cached = None if refresh else _load("gamma_nba_events.json")
    if cached is not None:
        return cached
    lo, hi = SAMPLE_GAME_DATES
    events, offset = [], 0
    while True:
        page = apilog.get(f"{GAMMA_API}/events", {
            "tag_slug": "nba", "closed": "true", "limit": 100, "offset": offset,
            "order": "endDate", "ascending": "false",
        }, source="polymarket_gamma", min_interval=0.3, count_fn=len)
        if not page:
            break
        for ev in page:
            m = SLUG_RE.match(ev.get("slug", ""))
            if m and lo <= m.group(3) <= hi:
                events.append(ev)
        # stop once the page's end dates are older than the sample window
        oldest = min((e.get("endDate") or "9999") for e in page)
        if oldest[:10] < lo or len(page) < 100:
            break
        offset += 100
    _save("gamma_nba_events.json", events)
    return events


def _moneyline(ev: dict) -> dict | None:
    ml = [m for m in ev.get("markets", []) if m.get("sportsMarketType") == "moneyline"]
    return ml[0] if len(ml) == 1 else None


def candidate_table(events: list[dict]) -> pd.DataFrame:
    """One row per candidate game with identifiers; exclusions are recorded, not dropped."""
    rows = []
    for ev in events:
        away, home, date = SLUG_RE.match(ev["slug"]).groups()
        row = {"event_id": ev["id"], "slug": ev["slug"], "game_date_local": date,
               "away": away, "home": home, "exclusion": None}
        ml = _moneyline(ev)
        if ml is None:
            row["exclusion"] = "no unique moneyline market"
            rows.append(row)
            continue
        outcomes = json.loads(ml["outcomes"])
        tokens = json.loads(ml["clobTokenIds"])
        row.update({"market_id": ml["id"], "condition_id": ml["conditionId"],
                    "question": ml["question"], "volume": float(ml.get("volume") or 0),
                    "game_start_utc": _to_utc(ml["gameStartTime"]),
                    "market_created_utc": _to_utc(ml["createdAt"]),
                    "outcome_prices": ml.get("outcomePrices")})
        # Match tokens to teams by outcome label, never by list position.
        if away not in TEAMS or home not in TEAMS:
            row["exclusion"] = "unknown team abbreviation"
        else:
            label = {o: t for o, t in zip(outcomes, tokens)}
            a_nick, h_nick = TEAMS[away][1], TEAMS[home][1]
            if set(outcomes) != {a_nick, h_nick}:
                row["exclusion"] = f"outcome labels {outcomes} do not match {a_nick}/{h_nick}"
            else:
                row.update({"token_away": label[a_nick], "token_home": label[h_nick],
                            "outcome_away": a_nick, "outcome_home": h_nick})
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- prices
def fetch_price_history(token_id: str, start: pd.Timestamp, end: pd.Timestamp,
                        fidelity: int = 60) -> pd.DataFrame:
    """Price points for one outcome token at `fidelity` minutes, chunked to stay under the span limit."""
    name = f"prices_{token_id}.json" if fidelity == 60 else f"prices_f{fidelity}_{token_id}.json"
    pts = _load(name)
    if pts is None:
        pts, t0, t1 = [], int(start.timestamp()), int(end.timestamp())
        step = 5 * 86400 if fidelity >= 60 else 6 * 3600
        for s in range(t0, t1, step):
            res = apilog.get(f"{CLOB_API}/prices-history", {
                "market": token_id, "startTs": s, "endTs": min(s + step, t1), "fidelity": fidelity,
            }, source="polymarket_clob", min_interval=0.2, count_fn=lambda r: len(r.get("history", [])))
            if res is None:
                raise RuntimeError(f"price history failed for token {token_id}")
            pts.extend(res.get("history", []))
        _save(name, pts)
    df = pd.DataFrame(pts, columns=["t", "p"]).drop_duplicates("t").sort_values("t")
    df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df[["ts", "p"]].reset_index(drop=True)


# ---------------------------------------------------------------- trades
# v2 field names -> the v1 names the rest of the pipeline uses. Profile fields are not kept.
V2_FIELDS = {"transaction_hash": "transactionHash", "token_id": "asset", "condition_id": "conditionId",
             "outcome_index": "outcomeIndex", "side": "side", "size": "size", "price": "price",
             "timestamp": "timestamp", "outcome": "outcome"}


def fetch_trades(condition_id: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """All taker trades for a market in [start, end].

    The full history back to `start` is cached once per market (trades_v2_{id}.json), so
    pregame and in-game calls share one download.
    """
    name = f"trades_v2_{condition_id}.json"
    cache = _load(name)
    t0 = int(start.timestamp())
    if cache is None or (cache["paged_back_to"] > t0 and not cache["complete"]):
        trades, cursor = [], None
        while True:
            params = {"condition_id": condition_id, "limit": 500}
            if cursor:
                params["cursor"] = cursor
            res = apilog.get(f"{DATA_API}/v2/trades", params, source="polymarket_data",
                             min_interval=0.2, count_fn=lambda r: len(r.get("data", [])))
            if res is None:
                raise RuntimeError(f"trades request failed for {condition_id}")
            page = [{k: t.get(k) for k in V2_FIELDS} for t in res.get("data", [])]
            trades.extend(page)
            more = res.get("pagination", {}).get("has_more", False)
            if not page or not more or min(t["timestamp"] for t in page) < t0:
                break
            cursor = res["pagination"]["next_cursor"]
        cache = {"paged_back_to": min((t["timestamp"] for t in trades), default=t0),
                 "complete": not more, "trades": trades}
        _save(name, cache)
    df = pd.DataFrame(cache["trades"]).rename(columns=V2_FIELDS)
    if df.empty:
        return df
    df = df.drop_duplicates(["transactionHash", "asset", "size", "price", "timestamp", "side"])
    df["ts"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df[(df.ts >= start) & (df.ts <= end)]
    return df.sort_values("ts").reset_index(drop=True)


# ---------------------------------------------------------------- hourly panel
def hourly_market_panel(game: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Hourly UTC panel for one game, pregame only.

    Row t describes the interval [t, t+1h). Grid rows satisfy t+1h <= game start.
      p_home      home-win price at the END of hour t: the CLOB hourly snapshot taken
                  at ~(t+1h):00:30 (snapshots are labelled by their floored hour).
                  Snapshots at/after game start are discarded; gaps are forward-filled
                  and flagged by price_observed=False.
      n_trades,   taker trades / USDC notional (size*price) executed in [t, t+1h).
      volume_usd
    """
    start = game.market_created_utc.floor("h")
    gs = game.game_start_utc
    end = gs + pd.Timedelta(hours=6)  # prices a bit past start, used only for validation

    ph = fetch_price_history(game.token_home, start, end)
    pa = fetch_price_history(game.token_away, start, end)
    tr = fetch_trades(game.condition_id, start, gs)

    checks = {"slug": game.slug, "n_price_home": len(ph), "n_price_away": len(pa),
              "n_trades": len(tr)}
    both = (ph.assign(h=ph.ts.dt.floor("h")).groupby("h").p.last().to_frame("p_home")
            .join(pa.assign(h=pa.ts.dt.floor("h")).groupby("h").p.last().rename("p_away"), how="inner"))
    both = both[both.index < gs]
    checks["max_abs_sum_dev"] = float((both.p_home + both.p_away - 1).abs().max()) if len(both) else np.nan
    if len(tr):
        checks["trades_wrong_market"] = int((tr.conditionId != game.condition_id).sum())
        checks["trades_unknown_asset"] = int((~tr.asset.isin([game.token_home, game.token_away])).sum())
        checks["trades_after_start"] = int((tr.ts >= gs).sum())
        checks["earliest_trade"] = tr.ts.min()

    grid = pd.date_range(start, gs - pd.Timedelta(hours=1), freq="h", tz="UTC")
    pre = ph[ph.ts < gs]
    snap = pre.groupby(pre.ts.dt.floor("h")).p.last()  # snapshot near top of each hour
    out = pd.DataFrame(index=grid)
    out.index.name = "hour"
    out["p_home_obs"] = snap.reindex(grid + pd.Timedelta(hours=1)).to_numpy()
    out["price_observed"] = out.p_home_obs.notna()
    out["p_home"] = out.p_home_obs.ffill()

    tr_pre = tr[tr.ts < gs].copy() if len(tr) else tr
    if len(tr_pre):
        tr_pre["hour"] = tr_pre.ts.dt.floor("h")
        tr_pre["usd"] = tr_pre["size"].astype(float) * tr_pre["price"].astype(float)
        g = tr_pre.groupby("hour")
        out["n_trades"] = g.size().reindex(grid).fillna(0)
        out["volume_usd"] = g.usd.sum().reindex(grid).fillna(0.0)
    else:
        out["n_trades"] = 0
        out["volume_usd"] = 0.0
    checks["n_pregame_hours"] = len(grid)
    checks["n_pregame_price_hours"] = int(out.price_observed.sum())
    checks["n_pregame_trades"] = int(len(tr_pre))
    return out.reset_index(), checks


def select_games(cands: pd.DataFrame) -> pd.DataFrame:
    """Apply inclusion criteria in volume order; keep the top N_GAMES that pass."""
    cands = cands.sort_values("volume", ascending=False).copy()
    low = cands.exclusion.isna() & (cands.volume < MIN_MONEYLINE_VOLUME)
    cands.loc[low, "exclusion"] = f"moneyline volume < ${MIN_MONEYLINE_VOLUME:,}"
    cands["selected"] = False
    used_teams: set[str] = set()
    for i, row in cands[cands.exclusion.isna()].iterrows():
        if cands.selected.sum() >= N_GAMES:
            cands.loc[i, "exclusion"] = "not needed (sample full)"
            continue
        # Distinct teams keep a team's attention series out of both train and test games.
        if {row.away, row.home} & used_teams:
            cands.loc[i, "exclusion"] = "team already in sample"
            continue
        ph = fetch_price_history(row.token_home, row.market_created_utc.floor("h"),
                                 row.game_start_utc + pd.Timedelta(hours=6))
        n_pre = int((ph.ts < row.game_start_utc).sum())
        cands.loc[i, "n_pregame_price_points"] = n_pre
        if n_pre < MIN_PREGAME_PRICE_HOURS:
            cands.loc[i, "exclusion"] = f"only {n_pre} pregame price points"
        else:
            cands.loc[i, "selected"] = True
            used_teams |= {row.away, row.home}
    return cands
