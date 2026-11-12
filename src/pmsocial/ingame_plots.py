"""Milestone II figures (market side): scoring reaction, pilot price paths, model comparison."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import TEAMS
from .plots import INK, INK2, S1, S2, S3, _label  # shared palette and rcParams

MODEL_NAMES = {"B0": "B0: no change", "B1": "B1: market + game state",
               "B1+bsky_counts": "B1 + Bluesky counts", "B1+bsky_abnormal": "B1 + abnormal attention",
               "B1+bsky_imbalance": "B1 + home/away imbalance", "B1+bsky_injury": "B1 + injury posts",
               "B1+bsky_all": "B1 + all Bluesky"}


def fig_scoring_reaction(reaction: pd.DataFrame, out: Path):
    offs = [c for c in reaction.columns if isinstance(c, (int, np.integer))]
    v = reaction[offs] * 100
    m, se = v.mean(), v.std() / np.sqrt(len(v))
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.fill_between(offs, m - 1.96 * se, m + 1.96 * se, color=S1, alpha=0.18, lw=0)
    ax.plot(offs, m, color=S1, marker="o", ms=4)
    ax.axvline(0, color=INK2, lw=0.8, ls="--")
    ax.text(1, m.max() * 0.15, "ESPN play time", color=INK2, fontsize=8)
    ax.set_xlabel("seconds from the scoring play")
    ax.set_ylabel("price move toward scorer\n(percentage points)")
    ax.set_title(f"Polymarket absorbs a basket within ~10 seconds\n{len(v)} scoring plays in 8 games; "
                 "mean ± 95% CI, relative to the price 60 s before", loc="left")
    fig.tight_layout()
    fig.savefig(out / "fig_m2_scoring_reaction.png", dpi=150)
    plt.close(fig)


def fig_pilot_games(panel: pd.DataFrame, games, out: Path):
    has_bsky = "posts_home" in panel
    rows = 2 if has_bsky else 1
    fig, axes = plt.subplots(rows, len(games), figsize=(4 * len(games), 2.6 * rows), squeeze=False)
    for j, s in enumerate(games):
        g = panel[(panel.slug == s) & panel.in_game]
        mins = (g.minute - g.minute.iloc[0]).dt.total_seconds() / 60
        home, away = s.split("-")[2], s.split("-")[1]
        ax = axes[0, j]
        ax.plot(mins, g.p_home, color=S1, label="Polymarket")
        ax.plot(mins, g.espn_wp_home, color=S2, lw=1.1, label="ESPN model")
        ax.set_ylim(0, 1)
        ax.set_title(_label(s), loc="left")
        ax.set_ylabel(f"P({TEAMS[home][1]} win)")
        if has_bsky:
            b = axes[1, j]
            b.plot(mins, g.posts_home, color=S1, lw=1, label=TEAMS[home][1])
            b.plot(mins, g.posts_away, color=S3, lw=1, label=TEAMS[away][1])
            b.set_ylabel("Bluesky posts / min")
            b.legend(loc="upper left", fontsize=8)
        axes[-1, j].set_xlabel("minutes since tip-off")
    fig.suptitle("Pilot games: in-game home win probability (end of each minute)", x=0.01, ha="left",
                 fontweight="bold")
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper right", ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_m2_pilot_games.png", dpi=150)
    plt.close(fig)


def fig_models(folds: pd.DataFrame, out: Path, sample="all_8_games"):
    f = folds[(folds["sample"] == sample) & (folds.estimator == "ols") & folds.model.isin(MODEL_NAMES)]
    order = [m for m in MODEL_NAMES if m in set(f.model)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.45 * len(order) + 1.8))
    for ax, h in zip(axes, (1, 5)):
        g = f[f.horizon_min == h]
        for i, m in enumerate(order):
            v = g[g.model == m].rmse
            ax.scatter(v, np.full(len(v), i) + np.linspace(-0.12, 0.12, len(v)), s=12, color=S1, alpha=0.45, lw=0)
            ax.scatter([v.mean()], [i], s=60, color=INK, marker="|", lw=2)
            ax.text(v.mean(), i - 0.24, f"mean {v.mean():.3f}", ha="center", fontsize=8, color=INK2)
        ax.set_yticks(range(len(order)), [MODEL_NAMES[m] for m in order])
        ax.set_ylim(len(order) - 0.6, -0.6)
        ax.xaxis.set_major_locator(plt.MaxNLocator(6))
        ax.set_xlabel("RMSE of change in log-odds (lower is better)")
        ax.set_title(f"Next {h} minute{'s' if h > 1 else ''}", loc="left")
    fig.suptitle("Leave-one-game-out forecast error, 8 games (dots = held-out games, bar = mean; OLS)",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig_m2_model_comparison.png", dpi=150)
    plt.close(fig)
