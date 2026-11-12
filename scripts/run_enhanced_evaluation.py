"""Run supplemental enhanced-model checks; preserve the market owner's outputs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from pmsocial import enhanced_evaluation as evaluation, ingame
from pmsocial.config import DATA_PROCESSED as P, FIGURES, PILOT_GAMES


def main():
    market = pd.read_parquet(P / "ingame_market_minute.parquet")
    social = pd.read_parquet(P / "ingame_bluesky_minute.parquet")
    panel = ingame.build_panel(market, social)
    primary = evaluation.models.model_frame(panel, True)
    clean = panel[evaluation.observed_history_mask(panel)].copy()
    # Features must be constructed before filtering: preserve exact lag semantics.
    eligible = set(zip(clean.slug, clean.minute))
    clean_frame = primary[[key in eligible for key in zip(primary.slug, primary.minute)]].reset_index(drop=True)
    frames = []
    for sample, data in [("pilot_3_games", panel[panel.slug.isin(PILOT_GAMES)]), ("all_8_games", panel)]:
        for estimator in ("ols", "ridge"):
            frames.append(evaluation.predictions(data, sample, estimator))
    # Pass a prepared frame explicitly rather than computing lags on a filtered grid.
    for estimator in ("ols", "ridge"):
        frames.append(evaluation.predictions_from_frame(clean_frame, "observed_history", estimator))
    pr = pd.concat(frames, ignore_index=True)
    folds, summary, comparisons = evaluation.summarize(pr)
    pr.to_parquet(P / "enhanced_predictions.parquet", index=False)
    folds.to_csv(P / "enhanced_folds.csv", index=False)
    summary.to_csv(P / "enhanced_summary.csv", index=False)
    comparisons.to_csv(P / "enhanced_comparisons.csv", index=False)
    info = {"primary_rows": len(primary), "observed_history_rows": len(clean_frame),
            "games": primary.slug.nunique(), "bootstrap_draws": 10000, "seed": 473,
            "primary_design": "leave-one-game-out; unchanged OLS/Ridge alpha=1 specifications",
            "uncertainty": "exploratory whole-game bootstrap and symmetric game-level sign-flip; overlapping training folds are not independent",
            "probability_metric": "against clipped probability endpoint implied by the logit target"}
    (P / "enhanced_checks.json").write_text(json.dumps(info, indent=2))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, horizon in zip(axes, (1, 5)):
        g = comparisons[(comparisons['sample'] == 'all_8_games') & (comparisons.estimator == 'ols') & (comparisons.horizon_min == horizon) & (comparisons.vs == 'B1')]
        for i, r in enumerate(g.itertuples()):
            ax.plot([r.bootstrap_low_pct, r.bootstrap_high_pct], [i, i], color='tab:blue')
            ax.scatter(r.rmse_change_pct, i, color='tab:blue')
        ax.set_yticks(range(len(g)), g.model.str.replace('B1+bsky_', '', regex=False))
        ax.axvline(0, color='gray', linestyle='--')
        ax.set_title(f'Next {horizon} minute(s)')
        ax.set_xlabel('Pooled RMSE change versus B1 (%)\nNegative = improvement')
        ax.grid(alpha=.15)
    axes[0].invert_yaxis()
    fig.suptitle('Bluesky incremental forecast performance (8 games, OLS)\nPaired whole-game bootstrap 95% intervals; exploratory')
    fig.tight_layout()
    fig.savefig(FIGURES / 'fig_m2_enhanced_uncertainty.png', dpi=160)
    plt.close(fig)
    print(json.dumps(info, indent=2))
    print(comparisons[(comparisons['sample']=='all_8_games') & (comparisons.estimator=='ols')].to_string(index=False))


if __name__ == '__main__':
    main()
