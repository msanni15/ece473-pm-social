"""Descriptive minute-resolution lead/lag analysis; not causal identification.

Lag convention: corr(delta_logit[t], attention[t+lag]). Positive lag means the
market change precedes the measured attention. Total post counts do not have a
direction; home-away log-count imbalance is included as a directional sensitivity
check. Correlations are calculated within games on exact minute pairs, then
averaged equally across games. Constant series produce undefined correlations.

Event windows cover -10..+10 minutes. Minute 0 contains the event; the price
curve is the benefiting/scoring side's probability minus its value at minute -1.
Scoring events use that side's posts. Jump events use the side whose probability
increased. Windows must be complete for price and the relevant post count.
Overlapping scoring windows are retained and are not independent observations.
Curves average events within games, then average games equally. These plots can
show minute-scale timing patterns, not distinguish second-scale reactions or
establish which process causes the other.
"""
from pathlib import Path

import numpy as np
import pandas as pd


def minute_panel(market: pd.DataFrame, social: pd.DataFrame) -> pd.DataFrame:
    keys = ["slug", "minute"]
    m, s = market.copy(), social.copy()
    for frame in (m, s):
        frame["minute"] = pd.to_datetime(frame.minute, utc=True).astype("datetime64[ns, UTC]")
        if frame.duplicated(keys).any() or not frame.minute.eq(frame.minute.dt.floor("min")).all():
            raise ValueError("Input must have unique, minute-aligned (slug, minute) keys")
    if set(m.slug) != set(s.slug):
        raise ValueError("Market and social game sets differ; supply matching inputs")
    panel = m.merge(s, on=keys, how="left", validate="one_to_one", indicator=True)
    if (panel._merge != "both").any():
        raise ValueError("Social data does not cover every market minute")
    panel = panel.drop(columns="_merge").sort_values(keys).reset_index(drop=True)
    group = panel.groupby("slug", sort=False)
    contiguous = group.minute.diff().eq(pd.Timedelta(minutes=1))
    observed = panel.price_observed.fillna(False).astype(bool)
    previous_observed = group.price_observed.shift(1).fillna(False).astype(bool)
    ingame_pair = panel.in_game.fillna(False).astype(bool) & group.in_game.shift(1).fillna(False).astype(bool)
    valid = contiguous & observed & previous_observed & ingame_pair
    panel["dp"] = group.p_home.diff().where(valid)
    panel["dlogit"] = group.logit_p.diff().where(valid)
    panel["posts_total"] = panel.posts_home + panel.posts_away
    return panel


def event_centers(panel: pd.DataFrame, events: pd.DataFrame, kind: str, jump=0.05):
    if kind == "scoring":
        e = events.copy()
        e["ts"] = pd.to_datetime(e.ts, utc=True)
        e = e[e.scoring_play.fillna(False).astype(bool) & e.scoring_side.isin(["home", "away"])]
        e["minute"] = e.ts.dt.floor("min")
        e = e.rename(columns={"scoring_side": "side"})[["slug", "minute", "side"]]
        active = panel.loc[panel.in_game.fillna(False).astype(bool), ["slug", "minute"]]
        return e.merge(active, on=["slug", "minute"], how="inner", validate="many_to_one")
    if kind == "jumps":
        e = panel[panel.dp.abs() >= jump - 1e-12][["slug", "minute", "dp"]].copy()
        e["side"] = np.where(e.dp > 0, "home", "away")
        return e[["slug", "minute", "side"]]
    raise ValueError("kind must be scoring or jumps")


def event_study(panel, centers, radius=10):
    indexed = {slug: g.set_index("minute") for slug, g in panel.groupby("slug")}
    offsets = np.arange(-radius, radius + 1)
    rows, used = [], []
    for event_id, e in enumerate(centers.itertuples(index=False)):
        if e.slug not in indexed:
            continue
        grid = pd.DatetimeIndex([e.minute + pd.Timedelta(minutes=int(k)) for k in offsets])
        window = indexed[e.slug].reindex(grid)
        cols = ["p_home", f"posts_{e.side}"]
        if window[cols].isna().any().any():
            continue
        probability = window.p_home if e.side == "home" else 1 - window.p_home
        price_delta = probability - probability.iloc[radius - 1]
        used.append({"event_id": event_id, "slug": e.slug, "minute": e.minute, "side": e.side})
        for i, lag in enumerate(offsets):
            rows.append({"event_id": event_id, "slug": e.slug, "lag": int(lag),
                         "p_side": float(probability.iloc[i]),
                         "price_change_pp": 100 * float(price_delta.iloc[i]),
                         "posts": float(window[f"posts_{e.side}"].iloc[i])})
    detail = pd.DataFrame(rows, columns=["event_id", "slug", "lag", "p_side", "price_change_pp", "posts"])
    if detail.empty:
        raise ValueError("No complete event windows; inspect missing coverage or event timestamps")
    by_game = detail.groupby(["slug", "lag"])[["p_side", "price_change_pp", "posts"]].mean().reset_index()
    curve = by_game.groupby("lag").agg(p_side=("p_side", "mean"), price_change_pp=("price_change_pp", "mean"),
                                       posts=("posts", "mean"), n_games=("slug", "nunique")).reset_index()
    return curve, by_game, pd.DataFrame(used)


def cross_correlations(panel, radius=10):
    rows = []
    for slug, game in panel.groupby("slug"):
        game = game.set_index("minute")
        for feature in ("posts_total", "imbalance"):
            for lag in range(-radius, radius + 1):
                times = game.index + pd.Timedelta(minutes=lag)
                future = game.reindex(times)
                attention = future[feature].to_numpy(dtype=float)
                active = (game.in_game.fillna(False).to_numpy(dtype=bool)
                          & future.in_game.fillna(False).to_numpy(dtype=bool))
                delta = game.dlogit.to_numpy(dtype=float)
                valid = np.isfinite(delta) & np.isfinite(attention) & active
                x, y = delta[valid], attention[valid]
                corr = float(np.corrcoef(x, y)[0, 1]) if len(x) >= 3 and x.std() > 0 and y.std() > 0 else np.nan
                rows.append({"slug": slug, "feature": feature, "lag": lag, "correlation": corr,
                             "n_pairs": int(valid.sum())})
    detail = pd.DataFrame(rows)
    summary = (detail.groupby(["feature", "lag"])
               .agg(correlation=("correlation", "mean"), n_games=("correlation", "count"),
                    n_pairs=("n_pairs", "sum")).reset_index())
    return summary, detail


def injury_review_table(posts: pd.DataFrame, panel: pd.DataFrame):
    """One candidate per actual post/game, retaining all matched query sides.

    Matching both team queries is not evidence that both teams suffered an injury.
    Keep the contractual side counts unchanged; deduplicate only this audit view.
    Labels are blank until a reviewer reads the texts. Novelty is not inferred.
    """
    p = posts[posts.kw_injury].copy()
    p["minute"] = p.sort_at.dt.floor("min")
    p = p.merge(panel[["slug", "minute", "in_game", "p_home", "score_diff"]],
                on=["slug", "minute"], how="left", validate="many_to_one")
    if p.in_game.isna().any():
        raise ValueError("Market input does not cover all injury-post minutes")
    p["matched_sides"] = p.groupby(["slug", "uri"]).side.transform(lambda x: ";".join(sorted(set(x))))
    p["side_matches"] = p.groupby(["slug", "uri"]).side.transform("size")
    p = p.drop_duplicates(["slug", "uri"]).sort_values(["slug", "sort_at", "uri"])
    cols = ["slug", "uri", "sort_at", "text", "matched_sides", "side_matches", "in_game", "p_home", "score_diff"]
    p = p[cols].reset_index(drop=True)
    p["review_category"] = ""
    p["review_note"] = ""
    p["reviewer"] = ""
    return p


def injury_timelines(panel, posts, games, output):
    """All-game descriptive injury-candidate timelines; no event selection by outcome."""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    candidates = injury_review_table(posts, panel)
    n = panel.slug.nunique()
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.2 * n), squeeze=False)
    inventory = []
    for ax, (slug, g) in zip(axes[:, 0], panel.groupby("slug")):
        game = games[games.slug == slug].iloc[0]
        hits = candidates[candidates.slug == slug]
        inside = g[g.in_game]
        ax.plot(g.minute + pd.Timedelta(minutes=1), g.p_home, color="tab:blue", linewidth=1)
        if len(inside):
            ax.axvspan(inside.minute.min(), inside.minute.max() + pd.Timedelta(minutes=1),
                       alpha=.08, color="tab:blue")
        ax.axvline(game.game_start_utc, color="gray", linestyle="--", linewidth=.8)
        ax.scatter(hits.sort_at, np.full(len(hits), .035), marker="|", s=100,
                   color="tab:red", label="Unique injury-keyword posts")
        ax.set_ylim(0, 1)
        ax.set_xlim(g.minute.min(), g.minute.max() + pd.Timedelta(minutes=1))
        ax.set_ylabel("Home win\nprobability")
        ax.set_title(f"{slug} | {len(hits)} unique keyword posts; {int(hits.in_game.sum())} in game", fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=g.minute.dt.tz))
        ax.grid(alpha=.15)
        inventory.append({"slug": slug, "unique_keyword_posts": len(hits),
                          "unique_keyword_posts_in_game": int(hits.in_game.sum()),
                          "side_matched_keyword_rows": int(hits.side_matches.sum())})
    axes[-1, 0].set_xlabel("UTC time; red ticks = keyword matches (not verified breaking injury news)")
    fig.suptitle("Bluesky injury-keyword candidates and market context\nShading = ESPN in-game minutes; dashed line = scheduled tip-off", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .97))
    fig.savefig(output / "fig_m2_bluesky_injury_timelines.png", dpi=140)
    plt.close(fig)
    pd.DataFrame(inventory).to_csv(output / "fig_m2_bluesky_injury_inventory.csv", index=False)
    return candidates


def make_figures(panel, events, output: Path, radius=10):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for kind, title in [("scoring", "Scoring plays"), ("jumps", "Price jumps of at least 5 pp")]:
        centers = event_centers(panel, events, kind)
        curve, by_game, used = event_study(panel, centers, radius)
        stem = output / f"fig_m2_timing_{kind}"
        curve.to_csv(stem.with_suffix(".csv"), index=False)
        by_game.to_csv(output / f"fig_m2_timing_{kind}_by_game.csv", index=False)
        used.to_csv(output / f"fig_m2_timing_{kind}_events.csv", index=False)
        fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        ax[0].plot(curve.lag, curve.posts, marker=".", color="tab:orange")
        ax[0].set_ylabel("Bluesky posts per minute\n(scoring / benefiting side)")
        ax[0].set_ylim(bottom=0)
        ax[1].plot(curve.lag, 100 * curve.p_side, marker=".", color="tab:blue")
        ax[1].set_ylabel("Win probability (%)\n(scoring / benefiting side)")
        ax[1].set_xlabel("Minutes relative to event-containing minute")
        for a in ax:
            a.axvline(0, color="gray", linestyle="--", linewidth=1)
            a.grid(alpha=0.2)
        fig.suptitle(f"Bluesky attention around {title.lower()}\n{len(used)} events, {used.slug.nunique()} games; equal game weights; overlapping windows retained")
        fig.tight_layout()
        fig.savefig(stem.with_suffix(".png"), dpi=160)
        plt.close(fig)
        summary[kind] = {"candidate_events": len(centers), "complete_events": len(used),
                         "excluded_incomplete": len(centers) - len(used), "games": used.slug.nunique()}
    corr, detail = cross_correlations(panel, radius)
    corr.to_csv(output / "fig_m2_cross_correlation.csv", index=False)
    detail.to_csv(output / "fig_m2_cross_correlation_by_game.csv", index=False)
    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    for ax, feature, label in zip(axes, ["posts_total", "imbalance"], ["Total posts", "Home-away log-count imbalance"]):
        g = corr[corr.feature == feature]
        ax.plot(g.lag, g.correlation, marker=".")
        ax.axhline(0, color="gray", linewidth=1)
        ax.axvline(0, color="gray", linestyle="--", linewidth=1)
        ax.set_ylabel(f"{label}\nMean within-game correlation")
        ax.grid(alpha=0.2)
    axes[1].set_xlabel("Lag k: corr(market change at t, attention at t+k)\nPositive = market precedes attention; negative = attention precedes market")
    fig.suptitle("Minute-level cross-correlations; descriptive, no causal inference")
    fig.tight_layout()
    fig.savefig(output / "fig_m2_cross_correlation.png", dpi=160)
    plt.close(fig)
    return summary
