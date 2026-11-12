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
    parser.add_argument("--posts", type=Path, default=DATA_PROCESSED / "ingame_bluesky_posts.parquet")
    parser.add_argument("--output", type=Path, default=FIGURES)
    args = parser.parse_args()
    missing = [str(p) for p in (args.market, args.events, args.social) if not p.exists()]
    if missing:
        parser.error("Awaiting input files: " + ", ".join(missing))
    panel = timing.minute_panel(pd.read_parquet(args.market), pd.read_parquet(args.social))
    summary = timing.make_figures(panel, pd.read_parquet(args.events), args.output)
    if args.posts.exists():
        from pmsocial.bluesky_ingame import RAW
        games = pd.read_csv(DATA_PROCESSED / "markets.csv")
        games["game_start_utc"] = pd.to_datetime(games.game_start_utc, utc=True)
        candidates = timing.injury_timelines(panel, pd.read_parquet(args.posts), games, args.output)
        RAW.mkdir(parents=True, exist_ok=True)
        review_path = RAW / "injury_review.csv"
        # Preserve annotations if the command is rerun. A changed post set needs
        # explicit review rather than silently reassigning existing labels.
        if not review_path.exists():
            candidates.to_csv(review_path, index=False)
        else:
            old = pd.read_csv(review_path)
            if set(zip(old.slug, old.uri)) != set(zip(candidates.slug, candidates.uri)):
                parser.error("Injury candidate set changed; reconcile injury_review.csv before rerunning")
        summary["injury_candidates"] = {"side_matched_rows": int(candidates.side_matches.sum()),
                                         "unique_post_game_pairs": len(candidates),
                                         "unique_post_game_pairs_in_game": int(candidates.in_game.sum())}
    (args.output / "fig_m2_timing_summary.json").write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps(summary, indent=2, default=int))


if __name__ == "__main__":
    main()
