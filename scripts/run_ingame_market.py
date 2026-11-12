"""Milestone II: in-game Polymarket + ESPN data for the selected games.

Usage:
    python scripts/run_ingame_market.py

Writes data/processed/ingame_events.parquet, ingame_trades.parquet, ingame_market_minute.parquet
and ingame_market_checks.csv. Raw responses are cached under data/raw/, so reruns are offline.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import espn, ingame  # noqa: E402
from pmsocial.config import DATA_PROCESSED as P  # noqa: E402


def games() -> pd.DataFrame:
    g = pd.read_csv(P / "markets.csv", dtype={"token_home": str, "token_away": str, "event_id": str,
                                              "market_id": str, "game_date_local": str})
    g = g[g.selected]
    for c in ("game_start_utc", "market_created_utc"):
        g[c] = pd.to_datetime(g[c], utc=True)
    return g.reset_index(drop=True)


def main():
    events, trades, minutes, checks = [], [], [], []
    for _, g in games().iterrows():
        plays = espn.plays_table(g)
        tr = ingame.game_trades(g)
        mm, chk = ingame.market_minutes(g, plays, tr)
        events.append(plays)
        trades.append(tr)
        minutes.append(mm)
        checks.append(chk)
        print(chk, flush=True)
    pd.concat(events, ignore_index=True).to_parquet(P / "ingame_events.parquet", index=False)
    pd.concat(trades, ignore_index=True).to_parquet(P / "ingame_trades.parquet", index=False)
    mm = pd.concat(minutes, ignore_index=True)
    print(ingame.validate_panel(mm))
    mm.to_parquet(P / "ingame_market_minute.parquet", index=False)
    pd.DataFrame(checks).to_csv(P / "ingame_market_checks.csv", index=False)


if __name__ == "__main__":
    main()
