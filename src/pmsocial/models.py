"""Baseline vs. enhanced linear forecasts with leave-one-game-out evaluation."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BASELINE = ["abs_dp", "abs_dp_lag1", "log_vol", "log_vol_lag1", "log_hours_to_game"]
SOCIAL = ["bsky_abn_home", "bsky_abn_away", "log_bsky_total"]
NEWS = ["log_gdelt_total"]
TARGETS = ["abs_dp_next", "log_vol_next"]


def model_frame(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["log_hours_to_game"] = np.log1p(df.hours_to_game)
    cols = BASELINE + SOCIAL + NEWS + TARGETS
    # Same rows for every specification, so MAE differences are comparable.
    return df.dropna(subset=cols).reset_index(drop=True)


def evaluate(df: pd.DataFrame, target: str, specs: dict[str, list[str]], estimator="ols") -> pd.DataFrame:
    """Per-held-out-game MAE/RMSE for each feature spec, plus a train-mean benchmark."""
    rows = []
    groups = df.slug.to_numpy()
    for train, test in LeaveOneGroupOut().split(df, groups=groups):
        tr, te = df.iloc[train], df.iloc[test]
        assert set(tr.slug).isdisjoint(te.slug)
        y_tr, y_te = tr[target].to_numpy(), te[target].to_numpy()
        preds = {"train_mean": np.full(len(te), y_tr.mean())}
        for name, feats in specs.items():
            reg = LinearRegression() if estimator == "ols" else Ridge(alpha=1.0)
            m = make_pipeline(StandardScaler(), reg).fit(tr[feats], y_tr)
            preds[name] = m.predict(te[feats])
        for name, p in preds.items():
            rows.append({"target": target, "estimator": estimator, "test_game": te.slug.iloc[0],
                         "n_test": len(te), "model": name,
                         "mae": float(np.mean(np.abs(p - y_te))),
                         "rmse": float(np.sqrt(np.mean((p - y_te) ** 2)))})
    return pd.DataFrame(rows)


def run_all(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = model_frame(panel)
    specs = {"baseline": BASELINE, "enhanced_social": BASELINE + SOCIAL,
             "enhanced_social_news": BASELINE + SOCIAL + NEWS}
    folds = pd.concat([evaluate(df, t, specs, est) for t in TARGETS for est in ("ols", "ridge")],
                      ignore_index=True)
    summary = (folds.groupby(["target", "estimator", "model"])
               .agg(mean_mae=("mae", "mean"), mean_rmse=("rmse", "mean"), folds=("mae", "size"))
               .reset_index())
    base = folds[folds.model == "baseline"].set_index(["target", "estimator", "test_game"]).mae
    diffs = []
    for m in ("enhanced_social", "enhanced_social_news"):
        d = folds[folds.model == m].set_index(["target", "estimator", "test_game"]).mae - base
        g = d.groupby(level=[0, 1])
        diffs.append(pd.DataFrame({"model": m, "mean_mae_diff_vs_baseline": g.mean(),
                                   "folds_improved": g.apply(lambda x: int((x < 0).sum())),
                                   "folds": g.size()}).reset_index())
    return df, folds, pd.concat(diffs, ignore_index=True)
