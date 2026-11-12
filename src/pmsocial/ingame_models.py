"""Milestone II in-game forecasts: next-minute change in home-win log-odds, leave-one-game-out.

B0  no change (efficient-market benchmark): predicted change = 0
B1  market + game state: recent price changes, trading, signed order flow, score, time left,
    and the gap between ESPN's win probability and the market price
B1+ B1 plus a Bluesky feature set (needs data/processed/ingame_bluesky_minute.parquet)

Main metric: RMSE of the predicted change over held-out games. Diebold-Mariano tests compare
squared errors of each model against B1 (and B1 against B0) on the pooled held-out minutes.
"""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .ingame import logit

N_LAGS = 5
MARKET = ([f"dlogit_lag{k}" for k in range(N_LAGS)]
          + ["log_trades", "log_volume", "flow", "flow_lag1"])
GAME_STATE = ["score_diff", "score_diff_scaled", "pts_net", "pts_net_lag1", "time_left", "espn_gap"]
BASELINE = MARKET + GAME_STATE
BLUESKY = {
    "counts": ["log_posts_home", "log_posts_away"],
    "abnormal": ["abn_home", "abn_away"],
    "imbalance": ["imbalance", "imbalance_lag1"],
    "injury": ["injury_home", "injury_away"],
}
BLUESKY["all"] = sorted({c for v in BLUESKY.values() for c in v})
TARGETS = {1: "dlogit_next1", 5: "dlogit_next5"}


def _slog(x):
    return np.sign(x) * np.log1p(np.abs(x))


def model_frame(panel: pd.DataFrame, with_bluesky: bool) -> pd.DataFrame:
    """Features at minute t use data time-stamped inside minute t or earlier, within the same game."""
    df = panel.sort_values(["slug", "minute"]).copy()
    g = df.groupby("slug")
    for k in range(N_LAGS):
        df[f"dlogit_lag{k}"] = g.dlogit.shift(k)
    df["log_trades"] = np.log1p(df.n_trades)
    df["log_volume"] = np.log1p(df.volume_usd)
    df["flow"] = _slog(df.flow_home)
    df["flow_lag1"] = df.groupby("slug").flow.shift(1)
    df["score_diff_scaled"] = df.score_diff / np.sqrt(df.sec_remaining + 60)
    df["pts_net"] = df.pts_home - df.pts_away
    df["pts_net_lag1"] = df.groupby("slug").pts_net.shift(1)
    df["time_left"] = df.sec_remaining / 2880
    df["espn_gap"] = logit(df.espn_wp_home) - df.logit_p
    cols = BASELINE + list(TARGETS.values())
    if with_bluesky:
        df["log_posts_home"] = np.log1p(df.posts_home)
        df["log_posts_away"] = np.log1p(df.posts_away)
        df["imbalance_lag1"] = df.groupby("slug").imbalance.shift(1)
        cols += BLUESKY["all"]
    df = df[df.in_game]
    # Same rows for every specification and horizon, so errors are directly comparable.
    return df.dropna(subset=cols).reset_index(drop=True)


def _predict(df, target, specs, estimator):
    """Held-out predictions for every row, one fold per game."""
    out = df[["slug", "minute", target]].rename(columns={target: "y"}).copy()
    out["B0"] = 0.0
    out["train_mean"] = np.nan
    for name in specs:
        out[name] = np.nan
    for train, test in LeaveOneGroupOut().split(df, groups=df.slug.to_numpy()):
        tr, te = df.iloc[train], df.iloc[test]
        assert set(tr.slug).isdisjoint(te.slug)
        out.loc[out.index[test], "train_mean"] = tr[target].mean()
        for name, feats in specs.items():
            reg = LinearRegression() if estimator == "ols" else Ridge(alpha=1.0)
            m = make_pipeline(StandardScaler(), reg).fit(tr[feats], tr[target])
            out.loc[out.index[test], name] = m.predict(te[feats])
    return out


def diebold_mariano(e_a: np.ndarray, e_b: np.ndarray, h: int) -> tuple[float, float]:
    """DM statistic for squared-error loss, model a minus model b (negative = a better).

    Newey-West variance with h-1 lags (overlapping h-step targets); two-sided normal p-value.
    """
    d = e_a ** 2 - e_b ** 2
    n = len(d)
    dc = d - d.mean()
    var = dc @ dc / n
    for k in range(1, h):
        var += 2 * (1 - k / h) * (dc[k:] @ dc[:-k]) / n
    stat = d.mean() / np.sqrt(var / n)
    return float(stat), float(2 * stats.norm.sf(abs(stat)))


def evaluate(df: pd.DataFrame, specs: dict[str, list[str]], sample: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    folds, tests = [], []
    for h, target in TARGETS.items():
        for est in ("ols", "ridge"):
            pr = _predict(df, target, specs, est)
            models = ["B0", "train_mean", *specs]
            for slug, g in pr.groupby("slug"):
                for m in models:
                    e = g[m] - g.y
                    nz = g.y != 0
                    folds.append({"sample": sample, "horizon_min": h, "estimator": est, "test_game": slug,
                                  "model": m, "n_test": len(g),
                                  "rmse": float(np.sqrt(np.mean(e ** 2))), "mae": float(np.mean(np.abs(e))),
                                  "direction_hit": float((np.sign(g[m][nz]) == np.sign(g.y[nz])).mean())
                                  if m not in ("B0",) else np.nan})
            pairs = [("B1", "B0")] + [(m, "B1") for m in specs if m != "B1"]
            for a, b in pairs:
                ea, eb = (pr[a] - pr.y).to_numpy(), (pr[b] - pr.y).to_numpy()
                stat, p = diebold_mariano(ea, eb, h)
                per_game = pr.groupby("slug").apply(
                    lambda g: np.sqrt(np.mean((g[a] - g.y) ** 2)) < np.sqrt(np.mean((g[b] - g.y) ** 2)))
                tests.append({"sample": sample, "horizon_min": h, "estimator": est, "model": a, "vs": b,
                              "pooled_rmse_model": float(np.sqrt(np.mean(ea ** 2))),
                              "pooled_rmse_vs": float(np.sqrt(np.mean(eb ** 2))),
                              "rmse_change_pct": float(100 * (np.sqrt(np.mean(ea ** 2))
                                                              / np.sqrt(np.mean(eb ** 2)) - 1)),
                              "dm_stat": stat, "dm_p": p, "games_better": int(per_game.sum()),
                              "games": int(per_game.size), "n": len(pr)})
    return pd.DataFrame(folds), pd.DataFrame(tests)


def run(panel: pd.DataFrame, games: list[str] | None, with_bluesky: bool, sample: str):
    df = model_frame(panel if games is None else panel[panel.slug.isin(games)], with_bluesky)
    specs = {"B1": BASELINE}
    if with_bluesky:
        specs.update({f"B1+bsky_{k}": BASELINE + v for k, v in BLUESKY.items()})
    folds, tests = evaluate(df, specs, sample)
    return df, folds, tests
