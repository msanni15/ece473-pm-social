"""Prepare outcome-blind social-label review and timestamp sensitivity diagnostics.

Does not overwrite any Milestone II source data, features, or model results.
Run before expanding the sample or interpreting cleaned social-news features.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"


def main():
    posts = pd.read_parquet(P / "ingame_bluesky_posts.parquet")
    market = pd.read_parquet(P / "ingame_market_minute.parquet")
    posts["minute"] = posts.sort_at.dt.floor("min")
    posts["matched_sides"] = posts.groupby(["slug", "uri"]).side.transform(lambda s: ";".join(sorted(set(s))))
    posts = posts.merge(market[["slug", "minute", "in_game"]], on=["slug", "minute"], validate="many_to_one")
    unique = posts[posts.in_game].drop_duplicates(["slug", "uri"]).copy()
    unique["index_delay_seconds"] = (unique.indexed_at - unique.created_at).dt.total_seconds()
    unique["index_after_original_bin_end"] = unique.indexed_at >= unique.minute + pd.Timedelta(minutes=1)
    diag_cols = ["slug", "uri", "created_at", "indexed_at", "sort_at", "index_delay_seconds", "index_after_original_bin_end"]
    unique[diag_cols].to_csv(P / "social_timestamp_diagnostics.csv", index=False)
    # Shuffle within each game; round-robin selection gives each game a chance,
    # including sparse games. This is not a volume-weighted precision estimate.
    rng = np.random.default_rng(473)
    pools = [g.iloc[rng.permutation(len(g))].index.tolist() for _, g in unique.groupby("slug")]
    selected = []
    while len(selected) < min(100, len(unique)):
        for pool in pools:
            if pool and len(selected) < 100:
                selected.append(pool.pop())
    sample = unique.loc[selected, ["slug", "uri", "sort_at", "text", "matched_sides"]].copy()
    for c in ("game_relevant", "information_type", "injured_team", "new_information", "source_reference", "reviewer", "notes"):
        sample[c] = ""
    destination = P / "social_validation_sample.csv"
    if destination.exists():
        existing = pd.read_csv(destination)
        if set(zip(existing.slug, existing.uri)) != set(zip(sample.slug, sample.uri)):
            raise ValueError("Review population changed; reconcile existing annotations explicitly")
    else:
        sample.to_csv(destination, index=False)
    info = {"seed": 473, "unique_ingame_posts": len(unique), "review_sample": len(sample),
            "sampling": "round-robin across games after within-game shuffling; not volume weighted",
            "sample_by_game": sample.groupby("slug").size().to_dict(),
            "index_after_original_bin_end": int(unique.index_after_original_bin_end.sum()),
            "negative_index_delay": int((unique.index_delay_seconds < 0).sum()),
            "review_status": "unlabelled; outcome-blind human review pending"}
    (P / "social_validation_checks.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
