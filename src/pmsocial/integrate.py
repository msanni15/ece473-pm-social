"""Merge Polymarket, Bluesky and GDELT into one (game, hour) panel with features/targets.

Timing convention (all UTC). Row t covers the interval [t, t+1h):
  - market:  p_home at end of hour t; dp = change over hour t; trades in hour t
  - bluesky: posts whose search sort-time falls in [t, t+1h)
  - gdelt:   articles in GKG files stamped in (t, t+1h]
Features use row t and earlier; targets are hour t+1 quantities (abs_dp_next,
log_vol_next). Only rows whose target interval ends by game start are kept.
"""
import numpy as np
import pandas as pd


def build_game_panel(game: pd.Series, market: pd.DataFrame, bsky: pd.DataFrame,
                     gdelt: pd.DataFrame) -> pd.DataFrame:
    df = market.copy()
    df.insert(0, "slug", game.slug)
    df.insert(1, "condition_id", game.condition_id)
    df["home"], df["away"] = game.home, game.away
    df["game_start_utc"] = game.game_start_utc
    df["hours_to_game"] = (game.game_start_utc - (df.hour + pd.Timedelta(hours=1))).dt.total_seconds() / 3600

    for side in ("home", "away"):
        team = game[side]
        b = bsky[bsky.team == team][["hour", "bsky_posts", "bsky_abnormal", "status"]]
        b = b.rename(columns={"bsky_posts": f"bsky_posts_{side}", "bsky_abnormal": f"bsky_abn_{side}",
                              "status": f"bsky_status_{side}"})
        g = gdelt[gdelt.team == team][["hour", "gdelt_articles"]].rename(
            columns={"gdelt_articles": f"gdelt_{side}"})
        df = df.merge(b, on="hour", how="left").merge(g, on="hour", how="left")

    df["dp"] = df.p_home.diff()
    df["abs_dp"] = df.dp.abs()
    df["log_vol"] = np.log1p(df.volume_usd)
    df["abs_dp_lag1"] = df.abs_dp.shift(1)
    df["log_vol_lag1"] = df.log_vol.shift(1)
    df["bsky_posts_total"] = df.bsky_posts_home + df.bsky_posts_away
    df["log_bsky_total"] = np.log1p(df.bsky_posts_total)
    df["bsky_abn_mean"] = df[["bsky_abn_home", "bsky_abn_away"]].mean(axis=1, skipna=False)
    df["gdelt_total"] = df.gdelt_home + df.gdelt_away
    df["log_gdelt_total"] = np.log1p(df.gdelt_total)
    # Targets: next hour (shift within this game only).
    df["abs_dp_next"] = df.abs_dp.shift(-1)
    df["log_vol_next"] = df.log_vol.shift(-1)
    df["target_hour"] = df.hour + pd.Timedelta(hours=1)
    return df


def validate_panel(panel: pd.DataFrame) -> dict:
    """Structural checks; raises on violations that would invalidate the analysis."""
    dup = int(panel.duplicated(["slug", "hour"]).sum())
    after = int((panel.hour + pd.Timedelta(hours=1) > panel.game_start_utc).sum())
    tgt_after = int(((panel.target_hour + pd.Timedelta(hours=1) > panel.game_start_utc)
                     & panel.abs_dp_next.notna()).sum())
    gaps = int(panel.groupby("slug").hour.apply(lambda h: (h.diff().dropna() != pd.Timedelta(hours=1)).sum()).sum())
    tz_ok = str(panel.hour.dt.tz) == "UTC"
    res = {"rows": len(panel), "games": panel.slug.nunique(), "duplicate_game_hours": dup,
           "rows_ending_after_start": after, "targets_ending_after_start": tgt_after,
           "non_hourly_gaps": gaps, "tz_is_utc": tz_ok,
           "missing_by_column": panel.isna().sum()[lambda s: s > 0].to_dict()}
    assert dup == 0 and after == 0 and tgt_after == 0 and gaps == 0 and tz_ok, res
    return res
