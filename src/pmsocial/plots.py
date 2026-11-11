"""Milestone I figures (matplotlib, PNG). All inputs are the real processed datasets."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import TEAMS  # noqa: E402

# Reference categorical palette (light mode), fixed order; text uses ink tokens.
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 9.5, "axes.titleweight": "bold", "lines.linewidth": 1.6,
    "legend.frameon": False,
})


def _label(slug: str) -> str:
    _, a, h, *d = slug.split("-")
    return f"{TEAMS[a][1]} @ {TEAMS[h][1]} ({'-'.join(d)[5:]})"


def _grid(n: int):
    fig, axes = plt.subplots(int(np.ceil(n / 2)), 2, figsize=(11, 2.3 * np.ceil(n / 2)), sharex=False)
    return fig, axes.ravel()


def _fmt_time(ax):
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))


def fig_probability(panel, out: Path):
    slugs = sorted(panel.slug.unique())
    fig, axes = _grid(len(slugs))
    for ax, s in zip(axes, slugs):
        g = panel[panel.slug == s]
        t = g.hour + pd.Timedelta(hours=1)  # p_home is the end-of-hour price
        ax.plot(t, g.p_home, color=S1)
        ax.set_title(_label(s), loc="left")
        ax.set_ylabel(f"P({TEAMS[g.home.iloc[0]][1]} win)")
        lo, hi = g.p_home.min(), g.p_home.max()
        ax.set_ylim(max(0, lo - 0.05), min(1, hi + 0.05))
        _fmt_time(ax)
    fig.suptitle("Polymarket home-team win probability before tip-off (hourly, UTC)", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig1_market_probability.png", dpi=150)
    plt.close(fig)


def fig_bluesky(bsky, games, out: Path):
    fig, axes = _grid(len(games))
    for ax, (_, g) in zip(axes, games.sort_values("slug").iterrows()):
        lo = g.market_created_utc.floor("h") - pd.Timedelta(hours=72)
        for side, col in (("away", S2), ("home", S1)):
            b = bsky[(bsky.team == g[side]) & (bsky.hour >= lo) & (bsky.hour < g.game_start_utc)]
            ax.plot(b.hour, b.bsky_posts, color=col, lw=1.1, label=f"{TEAMS[g[side]][1]} ({side})")
        ax.axvline(g.market_created_utc, color=INK2, lw=0.8, ls="--")
        ax.set_title(_label(g.slug), loc="left")
        ax.set_ylabel("posts / hour")
        ax.legend(loc="upper left", fontsize=8)
        _fmt_time(ax)
    fig.suptitle("Bluesky posts per hour mentioning each team (UTC); dashed line = market opens",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig2_bluesky_attention.png", dpi=150)
    plt.close(fig)


def fig_gdelt(panel, out: Path):
    slugs = sorted(panel.slug.unique())
    fig, axes = _grid(len(slugs))
    for ax, s in zip(axes, slugs):
        g = panel[panel.slug == s]
        ax.bar(g.hour, g.gdelt_total, width=1 / 24 * 0.85, color=S3, align="edge")
        ax.set_title(_label(s), loc="left")
        ax.set_ylabel("articles / hour")
        _fmt_time(ax)
    fig.suptitle("GDELT news articles per hour mentioning either team (pregame, UTC)", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig3_gdelt_news.png", dpi=150)
    plt.close(fig)


def _binned(ax, x, y, color, n_bins=8):
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    ax.scatter(x, y, s=8, color=color, alpha=0.18, lw=0)
    bins = pd.qcut(x, n_bins, duplicates="drop")
    m = pd.DataFrame({"x": x, "y": y, "b": bins}).groupby("b", observed=True).agg(
        x=("x", "mean"), y=("y", "mean"), se=("y", lambda v: v.std() / np.sqrt(len(v))))
    ax.errorbar(m.x, m.y, yerr=1.96 * m.se, color=INK, marker="o", ms=4, lw=1.2, capsize=2,
                label=f"mean within {n_bins} quantile bins ± 95% CI")
    rho = pd.Series(x).corr(pd.Series(y), method="spearman")
    ax.text(0.98, 0.95, f"Spearman ρ = {rho:.2f}\nn = {len(x)} game-hours", transform=ax.transAxes,
            ha="right", va="top", color=INK2, fontsize=8)
    ax.legend(loc="upper left", fontsize=8)


def fig_attention_vs_next(panel, out: Path):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    x = panel.bsky_abn_mean
    _binned(a1, x, panel.abs_dp_next * 100, S1)
    a1.set_xlabel("Bluesky abnormal attention at hour t\n(mean of both teams; log posts − trailing 72h mean)")
    a1.set_ylabel("|Δ probability| in hour t+1 (percentage points)")
    a1.set_title("Attention vs next-hour absolute price change", loc="left")
    _binned(a2, x, panel.log_vol_next, S2)
    a2.set_xlabel("Bluesky abnormal attention at hour t")
    a2.set_ylabel("log(1 + USDC volume) in hour t+1")
    a2.set_title("Attention vs next-hour trading volume", loc="left")
    fig.tight_layout()
    fig.savefig(out / "fig4_attention_vs_next_hour.png", dpi=150)
    plt.close(fig)


def fig_coverage(panel, out: Path):
    cov = panel.groupby("slug").agg(
        price=("price_observed", "mean"),
        bluesky=("bsky_posts_total", lambda s: s.notna().mean()),
        gdelt=("gdelt_total", lambda s: s.notna().mean()),
        trades=("n_trades", lambda s: (s > 0).mean()))
    cov.index = [_label(s) for s in cov.index]
    cols = ["price snapshot\nobserved", "Bluesky window\nretrieved", "GDELT files\ncomplete",
            "≥1 trade\nin hour"]
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(cov) + 1.4))
    im = ax.imshow(cov.to_numpy(), cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for i in range(cov.shape[0]):
        for j in range(cov.shape[1]):
            v = cov.iat[i, j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", color="white" if v > 0.6 else INK, fontsize=8)
    ax.set_xticks(range(4), cols)
    ax.set_yticks(range(len(cov)), cov.index)
    ax.grid(False)
    ax.set_title("Share of pregame hours with data, by source and game", loc="left")
    fig.colorbar(im, ax=ax, fraction=0.03, format=matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    fig.savefig(out / "fig5_data_coverage.png", dpi=150)
    plt.close(fig)


def fig_models(folds: pd.DataFrame, out: Path):
    f = folds[folds.estimator == "ols"]
    order = ["train_mean", "baseline", "enhanced_social", "enhanced_social_news"]
    names = ["Train mean", "Baseline (market only)", "+ Bluesky", "+ Bluesky + GDELT"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
    for ax, (tgt, unit, scale) in zip(axes, [("abs_dp_next", "MAE, percentage points", 100),
                                             ("log_vol_next", "MAE, log(1+USDC)", 1)]):
        g = f[f.target == tgt]
        for i, m in enumerate(order):
            v = g[g.model == m].mae * scale
            ax.scatter(v, np.full(len(v), i) + np.linspace(-0.12, 0.12, len(v)), s=12, color=S1, alpha=0.45, lw=0)
            ax.scatter([v.mean()], [i], s=60, color=INK, marker="|", lw=2)
            ax.text(v.mean(), i + 0.32, f"{v.mean():.3f}", ha="center", fontsize=8, color=INK2)
        ax.set_yticks(range(len(order)), names)
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        ax.set_title({"abs_dp_next": "Next-hour |Δ probability|",
                      "log_vol_next": "Next-hour trading volume"}[tgt], loc="left")
    fig.suptitle("Leave-one-game-out MAE (dots = held-out games, bar = mean); OLS", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig6_model_comparison.png", dpi=150)
    plt.close(fig)


def descriptive_table(panel: pd.DataFrame) -> pd.DataFrame:
    cols = {"p_home": "home win prob", "abs_dp": "|Δp| per hour", "n_trades": "trades / hour",
            "volume_usd": "USDC volume / hour", "bsky_posts_home": "Bluesky posts/h (home)",
            "bsky_posts_away": "Bluesky posts/h (away)", "gdelt_home": "GDELT articles/h (home)",
            "gdelt_away": "GDELT articles/h (away)"}
    d = panel[list(cols)].describe(percentiles=[0.5, 0.9]).T
    d.index = [cols[c] for c in d.index]
    return d.round(4)


def make_all(panel, bsky, games, out: Path, folds: pd.DataFrame | None = None):
    out.mkdir(parents=True, exist_ok=True)
    fig_probability(panel, out)
    fig_bluesky(bsky, games, out)
    fig_gdelt(panel, out)
    fig_attention_vs_next(panel, out)
    fig_coverage(panel, out)
    if folds is not None:
        fig_models(folds, out)
