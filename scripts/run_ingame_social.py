"""Collect the Partner's Milestone II Bluesky outputs without editing shared files.

Run: python scripts/run_ingame_social.py
Use --slugs SLUG ... for pilots, --refresh to retry all windows. Canonical queries
are used unless --query-checks supplies manually approved nickname checks.
Run without --slugs before handing off the full eight-game contract.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from pmsocial import apilog, bluesky_ingame as social
from pmsocial.config import DATA_PROCESSED, TEAMS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slugs", nargs="+")
    ap.add_argument("--query-checks", type=Path)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    games = pd.read_csv(DATA_PROCESSED / "markets.csv")
    games = games[games.selected.astype(str).str.lower() == "true"].copy()
    if args.slugs:
        unknown = set(args.slugs) - set(games.slug)
        if unknown:
            ap.error(f"Unknown selected games: {unknown}")
        games = games[games.slug.isin(args.slugs)]
    games["game_start_utc"] = social.utc(games.game_start_utc)
    checks_path = DATA_PROCESSED / "ingame_query_checks.csv"
    checks = pd.read_csv(args.query_checks) if args.query_checks else None
    if checks is None:
        checks = pd.DataFrame([{"team": t, "query": TEAMS[t][2], "kind": "canonical",
                                "n_reviewed": 0, "n_relevant": 0, "approved": True,
                                "notes": "Existing Milestone I query; no optional nickname added"}
                               for t in sorted(set(games.home) | set(games.away))])
    # The shared API helper normally appends to a shared tracked log. Keep this
    # branch's request evidence under its assigned raw-data directory instead.
    apilog.LOGS = social.RAW / "request_logs"
    windows = []
    for _, game in games.iterrows():
        windows.extend(social.collect_game(game, checks, refresh=args.refresh))
    posts = social.build_posts(windows, games)
    minutes = social.build_minutes(games, windows, posts)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    posts.to_parquet(DATA_PROCESSED / "ingame_bluesky_posts.parquet", index=False)
    minutes.to_parquet(DATA_PROCESSED / "ingame_bluesky_minute.parquet", index=False)
    checks.to_csv(checks_path, index=False)
    summary = []
    for slug, g in minutes.groupby("slug"):
        summary.append({"slug": slug, "minutes": len(g), "minutes_ok": int(g.bsky_ok.sum()),
                        "posts_home": float(g.posts_home.sum(min_count=1)),
                        "posts_away": float(g.posts_away.sum(min_count=1))})
    (social.RAW / "collection_summary.json").write_text(json.dumps(summary, indent=2))
    # Unlabelled material for the required manual relevance check; never invent
    # a relevance percentage or treat it as validated automatically.
    starts = games.set_index("slug").game_start_utc
    ingame = posts[posts.sort_at >= posts.slug.map(starts)]
    sample_path = social.RAW / "relevance_sample.csv"
    if not sample_path.exists():
        sample = ingame.sample(n=min(50, len(ingame)), random_state=473).copy()
        sample["relevant_to_game"] = ""
        sample["review_note"] = ""
        sample.to_csv(sample_path, index=False)
    print(pd.DataFrame(summary).to_string(index=False))
    print(f"Output: {len(minutes)} minute rows, {len(posts)} unique post-side rows")


if __name__ == "__main__":
    main()
