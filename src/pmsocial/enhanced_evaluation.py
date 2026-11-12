"""Additional enhanced-model evaluation, with games as the uncertainty unit.

Reuses the agreed LOGO specifications without tuning on test games. Inference is
exploratory: eight games, overlapping training folds, and model selection limit
the precision of bootstrap intervals and paired sign-flip p-values. Sign-flips
assume independent, symmetric game-level loss differences; they are a sensitivity
check, not exact randomization inference for the observational study.
"""
from itertools import product

import numpy as np
import pandas as pd
from scipy.special import expit

from . import ingame_models as models


def holm(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    result = np.empty(len(p))
    result[order] = np.minimum(1, np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    return result


def game_uncertainty(losses, draws=10000, seed=473):
    """Paired whole-game bootstrap of pooled RMSE change; equal-game sign flip.

    losses: one row per game, n, sse_model, sse_base. Entire games are resampled,
    preserving serial dependence within games and the paired comparison.
    """
    if losses.empty or (losses.n <= 0).any():
        raise ValueError("Nonempty positive-size game loss table required")
    a, b = losses.sse_model.to_numpy(), losses.sse_base.to_numpy()
    if b.sum() <= 0:
        raise ValueError("Baseline squared error must be positive")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(losses), size=(draws, len(losses)))
    delta = 100 * (np.sqrt(a[indices].sum(axis=1) / b[indices].sum(axis=1)) - 1)
    differences = (a - b) / losses.n.to_numpy()
    signs = np.array(list(product([-1, 1], repeat=len(losses))))
    distribution = np.abs((signs * differences).mean(axis=1))
    p = np.mean(distribution >= abs(differences.mean()) - 1e-15)
    lo, hi = np.quantile(delta, [.025, .975])
    return {"bootstrap_low_pct": float(lo), "bootstrap_high_pct": float(hi),
            "game_signflip_p": float(p)}


def observed_history_mask(panel):
    """Require every price in t-5..t+5 observed and both target endpoints in-game.

    Five lagged one-minute differences need prices through t-5. The longer target
    ends at t+5. Compute before row selection, so missing minutes are not compressed.
    """
    panel = panel.sort_values(["slug", "minute"])
    valid = pd.Series(True, index=panel.index)
    group = panel.groupby("slug")
    for offset in range(-5, 6):
        observed = group.price_observed.shift(-offset).fillna(False).astype(bool)
        times = group.minute.shift(-offset)
        valid &= observed & times.eq(panel.minute + pd.Timedelta(minutes=offset))
    return valid


def predictions(panel, sample, estimator):
    frame = models.model_frame(panel, True)
    return predictions_from_frame(frame, sample, estimator)


def predictions_from_frame(frame, sample, estimator):
    frame = frame.reset_index(drop=True)
    if frame.slug.nunique() < 2:
        raise ValueError("At least two games required")
    specs = {"B1": models.BASELINE,
             **{f"B1+bsky_{k}": models.BASELINE + v for k, v in models.BLUESKY.items()}}
    frames = []
    for horizon, target in models.TARGETS.items():
        pr = models._predict(frame, target, specs, estimator)
        pr["logit_current"] = frame.logit_p.to_numpy()
        model_names = ["B0", "B1", *[k for k in specs if k != "B1"]]
        for name in model_names:
            out = pr[["slug", "minute", "y", "logit_current"]].copy()
            out["prediction"] = pr[name]
            out["probability_target_clipped"] = expit(out.logit_current + out.y)
            out["probability_prediction"] = expit(out.logit_current + out.prediction)
            out["sample"], out["estimator"], out["horizon_min"], out["model"] = sample, estimator, horizon, name
            frames.append(out)
    return pd.concat(frames, ignore_index=True)


def summarize(predictions):
    fold_rows, comparisons = [], []
    for keys, pr in predictions.groupby(["sample", "estimator", "horizon_min"]):
        sample, estimator, horizon = keys
        for (slug, name), g in pr.groupby(["slug", "model"]):
            error = g.prediction - g.y
            fold_rows.append({"sample": sample, "estimator": estimator, "horizon_min": horizon,
                              "slug": slug, "model": name, "n": len(g), "sse": float((error ** 2).sum()),
                              "rmse": float(np.sqrt(np.mean(error ** 2))), "mae": float(error.abs().mean()),
                              "probability_rmse": float(np.sqrt(np.mean((g.probability_prediction - g.probability_target_clipped) ** 2)))})
        pairs = [("B1", "B0")] + [(m, "B1") for m in pr.model.unique() if m.startswith("B1+")]
        for name, baseline in pairs:
            a = pr[pr.model == name].set_index(["slug", "minute"])
            b = pr[pr.model == baseline].set_index(["slug", "minute"])
            if not a.index.equals(b.index) or not np.array_equal(a.y, b.y):
                raise ValueError("Models do not share exact test rows/targets")
            loss = pd.DataFrame({"a": (a.prediction - a.y) ** 2, "b": (b.prediction - b.y) ** 2})
            games = loss.groupby("slug").agg(n=("a", "size"), sse_model=("a", "sum"), sse_base=("b", "sum"))
            comparison = {"sample": sample, "estimator": estimator, "horizon_min": horizon,
                          "model": name, "vs": baseline, "n": len(a), "games": len(games),
                          "pooled_rmse_model": float(np.sqrt(loss.a.mean())),
                          "pooled_rmse_base": float(np.sqrt(loss.b.mean())),
                          "rmse_change_pct": float(100 * (np.sqrt(loss.a.sum() / loss.b.sum()) - 1)),
                          "games_improved": int((games.sse_model < games.sse_base).sum()),
                          **game_uncertainty(games)}
            comparisons.append(comparison)
    folds = pd.DataFrame(fold_rows)
    comparisons = pd.DataFrame(comparisons)
    # One family: five social specifications x two horizons, within sample/estimator.
    comparisons["holm_p_social_family"] = np.nan
    social = comparisons[comparisons.vs == "B1"]
    for _, g in social.groupby(["sample", "estimator"]):
        comparisons.loc[g.index, "holm_p_social_family"] = holm(g.game_signflip_p)
    summary = folds.groupby(["sample", "estimator", "horizon_min", "model"]).agg(
        macro_rmse=("rmse", "mean"), macro_mae=("mae", "mean"),
        macro_probability_rmse=("probability_rmse", "mean"), sse=("sse", "sum"), n=("n", "sum"), games=("slug", "nunique")).reset_index()
    summary["pooled_rmse"] = np.sqrt(summary.sse / summary.n)
    return folds, summary, comparisons
