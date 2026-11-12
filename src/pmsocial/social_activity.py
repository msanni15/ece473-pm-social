"""Exploratory attention/activity targets; never replace the original price test.

All eight existing games have been inspected. These results are development-only.
Minute t features are available at the end of t; future windows are t+1..t+h.
"""
import numpy as np
import pandas as pd

from . import ingame_models as original


def future_sum(frame, column, horizon):
    """Sum exact future minute rows, retaining missing data as missing."""
    group = frame.groupby("slug", sort=False)
    result = pd.Series(0., index=frame.index)
    for offset in range(1, horizon + 1):
        values = group[column].shift(-offset)
        contiguous = group.minute.shift(-offset).eq(frame.minute + pd.Timedelta(minutes=offset))
        active = group.in_game.shift(-offset).fillna(False).astype(bool)
        result = result + values.where(contiguous & active)
    return result


def build_frame(panel, horizon=5):
    panel = panel.sort_values(["slug", "minute"]).reset_index(drop=True).copy()
    group = panel.groupby("slug", sort=False)
    panel["future_log_volume"] = np.log1p(future_sum(panel, "volume_usd", horizon))
    next_price = group.logit_p.shift(-horizon)
    endpoint = group.minute.shift(-horizon).eq(panel.minute + pd.Timedelta(minutes=horizon))
    # Requiring every intermediate minute inside the game avoids crossing boundaries.
    window_ok = future_sum(panel.assign(_one=1.), "_one", horizon).notna()
    panel["future_abs_move"] = (next_price - panel.logit_p).abs().where(endpoint & window_ok)
    past_volume, past_abs = [], []
    for _, g in panel.groupby("slug", sort=False):
        regular = g.minute.diff().dropna().eq(pd.Timedelta(minutes=1)).all()
        if not regular:
            raise ValueError("Complete minute grids required for activity targets")
        past_volume.append(g.volume_usd.rolling(horizon, min_periods=horizon).sum())
        past_abs.append((g.logit_p - g.logit_p.shift(horizon)).abs())
    panel["past_log_volume"] = np.log1p(pd.concat(past_volume).sort_index())
    panel["past_abs_move"] = pd.concat(past_abs).sort_index()
    frame = original.model_frame(panel, True)
    return frame.dropna(subset=["future_log_volume", "future_abs_move", "past_log_volume", "past_abs_move"]).reset_index(drop=True)


def evaluate(frame, target, estimator="ridge"):
    extras = ["past_log_volume", "past_abs_move"]
    specs = {"market": original.BASELINE + extras,
             "market_social": original.BASELINE + extras + original.BLUESKY["all"]}
    prediction = original._predict(frame, target, specs, estimator)
    prediction["persistence"] = frame.past_log_volume if target == "future_log_volume" else frame.past_abs_move
    if target == "future_abs_move":
        prediction["zero_move"] = 0.
    # Both targets are nonnegative. Use the same declared clipping for each fitted model.
    for name in ("market", "market_social", "train_mean"):
        prediction[name] = prediction[name].clip(lower=0.)
    return prediction
