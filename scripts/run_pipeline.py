"""Milestone I pipeline.

Usage:
    python scripts/run_pipeline.py --all
    python scripts/run_pipeline.py --stages select polymarket bluesky gdelt merge analyze

Raw API responses are cached under data/raw/, so reruns only fetch what is missing.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import bluesky, gdelt, integrate, models, polymarket  # noqa: E402
from pmsocial.config import BASELINE_HOURS, DATA_PROCESSED, FIGURES, REPORTS  # noqa: E402

STAGES = ["select", "polymarket", "bluesky", "gdelt", "merge", "analyze"]
P = DATA_PROCESSED


def _games() -> pd.DataFrame:
    g = pd.read_csv(P / "markets.csv", dtype={"token_home": str, "token_away": str,
                                              "event_id": str, "market_id": str})
    g = g[g.selected]
    for c in ("game_start_utc", "market_created_utc"):
        g[c] = pd.to_datetime(g[c], utc=True)
    return g.reset_index(drop=True)


def _social_window(games: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = (games.market_created_utc.min() - pd.Timedelta(hours=BASELINE_HOURS)).floor("h")
    return start, games.game_start_utc.max().ceil("h")


def stage_select():
    cands = polymarket.select_games(polymarket.candidate_table(polymarket.fetch_nba_game_events()))
    cands.to_csv(P / "markets.csv", index=False)
    print(cands[["slug", "volume", "selected", "exclusion"]].to_string())


def stage_polymarket():
    frames, checks = [], []
    for _, g in _games().iterrows():
        panel, chk = polymarket.hourly_market_panel(g)
        panel.insert(0, "slug", g.slug)
        frames.append(panel)
        checks.append(chk)
        print(chk)
    pd.concat(frames).to_parquet(P / "polymarket_hourly.parquet", index=False)
    pd.DataFrame(checks).to_csv(P / "polymarket_checks.csv", index=False)


def stage_bluesky():
    games = _games()
    start, end = _social_window(games)
    teams = sorted(set(games.home) | set(games.away))
    windows = []
    for t in teams:
        w = bluesky.collect_team(t, start, end)
        print(t, w.status.value_counts().to_dict(), flush=True)
        windows.append(w)
    w = pd.concat(windows, ignore_index=True)
    w["hour"] = pd.to_datetime(w.hour, utc=True)
    w = w[(w.hour >= start) & (w.hour < end)]
    posts = bluesky.posts_table(w)
    posts.to_parquet(P / "bluesky_posts.parquet", index=False)
    counts = bluesky.abnormal_attention(bluesky.hourly_counts(w, posts))
    counts.to_parquet(P / "bluesky_hourly.parquet", index=False)
    print("posts", len(posts), "window statuses", w.status.value_counts().to_dict())


def stage_gdelt():
    games = _games()
    start, end = _social_window(games)
    gdelt.probe_doc_api()
    man, art = gdelt.collect(start, end)
    teams = sorted(set(games.home) | set(games.away))
    art.to_parquet(P / "gdelt_articles.parquet", index=False)
    man.to_csv(P / "gdelt_manifest.csv", index=False)
    gdelt.hourly_counts(man, art, teams).to_parquet(P / "gdelt_hourly.parquet", index=False)
    print("files", man.status.value_counts().to_dict(), "matched articles", len(art))


def stage_merge():
    games = _games()
    mk = pd.read_parquet(P / "polymarket_hourly.parquet")
    bs = pd.read_parquet(P / "bluesky_hourly.parquet")
    gd = pd.read_parquet(P / "gdelt_hourly.parquet")
    panel = pd.concat([integrate.build_game_panel(g, mk[mk.slug == g.slug].drop(columns="slug"), bs, gd)
                       for _, g in games.iterrows()], ignore_index=True)
    checks = integrate.validate_panel(panel)
    panel.to_parquet(P / "panel.parquet", index=False)
    panel.to_csv(P / "panel.csv", index=False)
    (P / "panel_checks.json").write_text(json.dumps(checks, indent=2, default=str))
    print(json.dumps(checks, indent=2, default=str))


def stage_analyze():
    from pmsocial import plots
    panel = pd.read_parquet(P / "panel.parquet")
    df, folds, diffs = models.run_all(panel)
    folds.to_csv(P / "model_folds.csv", index=False)
    diffs.to_csv(P / "model_diffs.csv", index=False)
    summary = (folds.groupby(["target", "estimator", "model"])
               .agg(mean_mae=("mae", "mean"), mean_rmse=("rmse", "mean"), n_test_rows=("n_test", "sum"))
               .reset_index())
    summary.to_csv(P / "model_summary.csv", index=False)
    print("model rows", len(df), "games", df.slug.nunique())
    print(summary.to_string())
    print(diffs.to_string())
    # Robustness: only hours where the snapshots behind dp(t-1), dp(t), dp(t+1) were all
    # observed (no forward-filled prices creating artificial zero changes).
    obs = panel.groupby("slug").price_observed
    keep = (panel.price_observed & obs.shift(1).fillna(False).astype(bool)
            & obs.shift(2).fillna(False).astype(bool) & obs.shift(-1).fillna(False).astype(bool))
    rdf, _, rdiffs = models.run_all(panel[keep.to_numpy()])
    rdiffs.insert(0, "sample", f"observed-price rows only (n={len(rdf)})")
    rdiffs.to_csv(P / "model_diffs_observed_prices.csv", index=False)
    print(rdiffs.to_string())
    plots.make_all(panel, pd.read_parquet(P / "bluesky_hourly.parquet"), _games(), FIGURES, folds)
    plots.descriptive_table(panel).to_csv(P / "descriptive_stats.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", nargs="*", choices=STAGES, default=[])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    for d in (P, FIGURES, REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    for s in (STAGES if a.all else a.stages):
        print(f"=== stage: {s}", flush=True)
        globals()[f"stage_{s}"]()


if __name__ == "__main__":
    main()
