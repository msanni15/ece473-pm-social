"""Run timing analysis once Alicia's market and ESPN Parquet files are available.

Run: python scripts/run_timing.py
Read-only inputs; all figure tables and images are written as figures/fig_m2_*.
The pre-tip abnormal-attention baseline must not be used for pre-tip forecasts.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from pmsocial import timing
from pmsocial.config import DATA_PROCESSED, FIGURES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", type=Path, default=DATA_PROCESSED / "ingame_market_minute.parquet")
    parser.add_argument("--events", type=Path, default=DATA_PROCESSED / "ingame_events.parquet")
    parser.add_argument("--social", type=Path, default=DATA_PROCESSED / "ingame_bluesky_minute.parquet")
    parser.add_argument("--output", type=Path, default=FIGURES)
    args = parser.parse_args()
    missing = [str(p) for p in (args.market, args.events, args.social) if not p.exists()]
    if missing:
        parser.error("Awaiting input files: " + ", ".join(missing))
    panel = timing.minute_panel(pd.read_parquet(args.market), pd.read_parquet(args.social))
    summary = timing.make_figures(panel, pd.read_parquet(args.events), args.output)
    (args.output / "fig_m2_timing_summary.json").write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps(summary, indent=2, default=int))


if __name__ == "__main__":
    main()
