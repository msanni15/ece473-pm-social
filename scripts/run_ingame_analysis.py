"""Milestone II analysis: in-game panel, models on the 3 pilot games and on all 8.

Usage:
    python scripts/run_ingame_analysis.py

Uses data/processed/ingame_market_minute.parquet and, if present, the partner's
ingame_bluesky_minute.parquet. Without the Bluesky file only B0 and B1 are evaluated.
Writes ingame_panel.parquet, ingame_model_folds.csv, ingame_model_tests.csv, ingame_model_summary.csv.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pmsocial import ingame, ingame_models, ingame_plots  # noqa: E402
from pmsocial.config import DATA_PROCESSED as P, FIGURES, PILOT_GAMES  # noqa: E402


def main():
    market = pd.read_parquet(P / "ingame_market_minute.parquet")
    bfile = P / "ingame_bluesky_minute.parquet"
    bsky = pd.read_parquet(bfile) if bfile.exists() else None
    panel = ingame.build_panel(market, bsky)
    checks = ingame.validate_panel(panel)
    panel.to_parquet(P / "ingame_panel.parquet", index=False)
    (P / "ingame_panel_checks.json").write_text(json.dumps(checks, indent=2))
    print("panel", checks, "| Bluesky file:", "yes" if bsky is not None else "not yet")

    trades = pd.read_parquet(P / "ingame_trades.parquet")
    events = pd.read_parquet(P / "ingame_events.parquet")
    reaction = ingame.scoring_reaction(trades, events)
    reaction.rename(columns=str).to_csv(P / "ingame_scoring_reaction.csv", index=False)
    offs = list(ingame.REACTION_OFFSETS)
    print("scoring plays", len(reaction), "mean move toward scorer (pp):",
          (reaction[offs].mean() * 100).round(2).to_dict())

    folds, tests = [], []
    for sample, games in (("pilot_3_games", list(PILOT_GAMES)), ("all_8_games", None)):
        df, f, t = ingame_models.run(panel, games, bsky is not None, sample)
        print(sample, "model rows", len(df), "games", df.slug.nunique())
        folds.append(f)
        tests.append(t)
    # Robustness: within-minute average price instead of the end-of-minute price. This lags the
    # minute's scoring, so next-minute changes look predictable from it (a timing artifact).
    vw = market.assign(p_home=market.p_vwap, logit_p=ingame.logit(market.p_vwap))
    _, f, t = ingame_models.run(ingame.build_panel(vw, None), None, False, "all_8_games_vwap_price")
    folds.append(f)
    tests.append(t)
    folds, tests = pd.concat(folds), pd.concat(tests)
    folds.to_csv(P / "ingame_model_folds.csv", index=False)
    tests.to_csv(P / "ingame_model_tests.csv", index=False)
    summary = (folds.groupby(["sample", "horizon_min", "estimator", "model"])
               .agg(mean_rmse=("rmse", "mean"), mean_mae=("mae", "mean"),
                    direction_hit=("direction_hit", "mean"), games=("rmse", "size"), n=("n_test", "sum"))
               .reset_index())
    summary.to_csv(P / "ingame_model_summary.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(summary[summary.estimator == "ols"].to_string(index=False))
        print(tests[tests.estimator == "ols"].to_string(index=False))

    FIGURES.mkdir(exist_ok=True)
    ingame_plots.fig_scoring_reaction(reaction, FIGURES)
    ingame_plots.fig_pilot_games(panel, list(PILOT_GAMES), FIGURES)
    ingame_plots.fig_models(folds, FIGURES)


if __name__ == "__main__":
    main()
