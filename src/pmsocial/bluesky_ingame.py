"""Bluesky in-game collection and the Milestone II minute data contract.

Counts use sort_at=min(created_at,indexed_at), never the containing search window.
Abnormal attention uses all 120 pre-tip minutes and is intended for in-game
forecasts only. An incomplete baseline yields NaN abnormal attention. Failed or
truncated queries invalidate the whole requested interval, including injury counts.
Optional aliases require a recorded manual review of at least 20 posts, >=70%
relevant. Existing configured queries remain the default; aliases are not assumed
equivalent to the canonical search.
"""
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .bluesky import _collect_window, _slim, posts_table
from .config import DATA_RAW, TEAMS

RAW = DATA_RAW / "bluesky_ingame"
INJURY = re.compile(r"injur|hurt|ankle|knee|locker room|ruled out|questionable|limp", re.I)
POST_COLUMNS = ["slug", "side", "team", "query", "uri", "text", "created_at",
                "indexed_at", "sort_at", "kw_injury"]
MINUTE_COLUMNS = ["slug", "minute", "posts_home", "posts_away", "abn_home", "abn_away",
                  "imbalance", "injury_home", "injury_away", "bsky_ok"]


def utc(values):
    """Explicit nanosecond UTC timestamps across supported pandas versions."""
    return pd.to_datetime(values, utc=True, errors="coerce", format="ISO8601").astype("datetime64[ns, UTC]")


def game_window(game):
    tip = pd.Timestamp(game.game_start_utc)
    if tip.tzinfo is None:
        raise ValueError("game_start_utc must be timezone aware")
    tip = tip.tz_convert("UTC")
    if tip != tip.floor("min"):
        raise ValueError("The 330-minute contract requires minute-aligned tip-off")
    return tip - pd.Timedelta(hours=2), tip + pd.Timedelta(hours=3, minutes=30)


def approved_queries(team: str, checks: pd.DataFrame | None = None) -> list[str]:
    canonical = TEAMS[team][2]
    aliases = []
    if checks is not None and len(checks):
        for r in checks[checks.team == team].itertuples():
            if r.query == canonical or str(r.approved).lower() != "true":
                continue
            n, relevant = int(r.n_reviewed), int(r.n_relevant)
            if n < 20 or not 0 <= relevant <= n or relevant / n < 0.7:
                raise ValueError(f"Alias {team}/{r.query} lacks a passing manual relevance check")
            aliases.append(r.query)
    aliases = list(dict.fromkeys(aliases))
    if len(aliases) > 1:
        raise ValueError(f"At most one nickname is allowed for {team}")
    return [canonical] + aliases


def collect_game(game, checks=None, raw_dir: Path = RAW, refresh=False) -> list[dict]:
    """Collect sequentially in <=1-hour chunks; cache keys include exact query/range.

    Reuse the existing splitter and its request throttle. Only successful cache
    entries are reused. Raw caches contain the original post payloads for audit.
    """
    start, end = game_window(game)
    raw_dir.mkdir(parents=True, exist_ok=True)
    windows = []
    for side in ("home", "away"):
        team = game[side]
        for query in approved_queries(team, checks):
            for since in pd.date_range(start, end, freq="h", inclusive="left"):
                until = min(since + pd.Timedelta(hours=1), end)
                key = {"version": 1, "slug": game.slug, "side": side, "team": team,
                       "query": query, "since": since.isoformat(), "until": until.isoformat()}
                digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
                path = raw_dir / f"{game.slug}_{side}_{digest}.json"
                cached = json.loads(path.read_text()) if path.exists() and not refresh else None
                if cached is None or cached.get("status") != "ok":
                    posts, status = _collect_window(query, since, until)
                    cached = {**key, "status": status, "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(),
                              "posts": posts}
                    path.write_text(json.dumps(cached))
                if any(cached.get(k) != v for k, v in key.items()):
                    raise ValueError(f"Cache identity mismatch: {path}")
                windows.append(cached)
                print(f"{game.slug} {side} {query} {since} {cached['status']} {len(cached['posts'])}", flush=True)
    return windows


def build_posts(windows: list[dict], games: pd.DataFrame) -> pd.DataFrame:
    frames = []
    bounds = {g.slug: game_window(g) for _, g in games.iterrows()}
    for w in windows:
        if w["status"] != "ok" or not w["posts"]:
            continue
        slim = [_slim(p) for p in w["posts"]]
        parsed = posts_table(pd.DataFrame([{"team": w["team"], "hour": w["since"], "posts": slim}]))
        parsed["created_at"] = utc(parsed.created_at)
        parsed["indexed_at"] = utc(parsed.indexed_at)
        if parsed[["created_at", "indexed_at"]].isna().any().any():
            raise ValueError("A retrieved post lacks valid timestamps; do not silently bin it")
        parsed["sort_at"] = parsed[["created_at", "indexed_at"]].min(axis=1)
        parsed["slug"], parsed["side"], parsed["query"] = w["slug"], w["side"], w["query"]
        parsed["kw_injury"] = parsed.text.fillna("").str.contains(INJURY)
        start, end = bounds[w["slug"]]
        frames.append(parsed[(parsed.sort_at >= start) & (parsed.sort_at < end)][POST_COLUMNS])
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=POST_COLUMNS)
    for c in ("created_at", "indexed_at", "sort_at"):
        out[c] = utc(out[c])
    out["kw_injury"] = out.kw_injury.astype(bool)
    return (out.drop_duplicates(["slug", "side", "uri"])
            .sort_values(["slug", "side", "sort_at", "uri"]).reset_index(drop=True))


def build_minutes(games: pd.DataFrame, windows: list[dict], posts: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, game in games.iterrows():
        start, end = game_window(game)
        grid = pd.date_range(start, end, freq="min", inclusive="left")
        frame = pd.DataFrame({"slug": game.slug, "minute": grid})
        side_ok = []
        for side in ("home", "away"):
            records = [w for w in windows if w["slug"] == game.slug and w["side"] == side]
            canonical = TEAMS[game[side]][2]
            queries = set(w["query"] for w in records) | {canonical}
            ok = pd.Series(True, index=grid)
            for query in queries:
                covered = pd.Series(False, index=grid)
                failed = pd.Series(False, index=grid)
                for w in records:
                    if w["query"] != query:
                        continue
                    interval = (grid >= pd.Timestamp(w["since"])) & (grid < pd.Timestamp(w["until"]))
                    if w["status"] == "ok":
                        covered.loc[interval] = True
                    else:
                        failed.loc[interval] = True
                ok &= covered & ~failed
            subset = posts[(posts.slug == game.slug) & (posts.side == side)].copy()
            subset["minute"] = subset.sort_at.dt.floor("min")
            counts = subset.groupby("minute").size().reindex(grid, fill_value=0).astype(float)
            injuries = subset.groupby("minute").kw_injury.sum().reindex(grid, fill_value=0).astype(float)
            counts.loc[~ok], injuries.loc[~ok] = np.nan, np.nan
            baseline = counts.loc[counts.index < game.game_start_utc]
            mean = np.log1p(baseline).mean() if len(baseline) == 120 and baseline.notna().all() else np.nan
            frame[f"posts_{side}"] = counts.to_numpy()
            frame[f"injury_{side}"] = injuries.to_numpy()
            frame[f"abn_{side}"] = np.log1p(counts.to_numpy()) - mean
            side_ok.append(ok.to_numpy())
        frame["imbalance"] = np.log1p(frame.posts_home) - np.log1p(frame.posts_away)
        frame["bsky_ok"] = side_ok[0] & side_ok[1]
        frames.append(frame[MINUTE_COLUMNS])
    out = pd.concat(frames, ignore_index=True)
    out["minute"] = utc(out.minute)
    validate_contract(games, out, posts)
    return out


def validate_contract(games, minutes, posts):
    if list(minutes.columns) != MINUTE_COLUMNS or list(posts.columns) != POST_COLUMNS:
        raise ValueError("Unexpected output columns")
    if minutes.duplicated(["slug", "minute"]).any() or posts.duplicated(["slug", "side", "uri"]).any():
        raise ValueError("Duplicate contract keys")
    for c in ("created_at", "indexed_at", "sort_at"):
        if str(posts[c].dtype) != "datetime64[ns, UTC]":
            raise ValueError(f"Incorrect timestamp dtype for {c}")
    if str(minutes.minute.dtype) != "datetime64[ns, UTC]":
        raise ValueError("Incorrect minute timestamp dtype")
    if set(minutes.slug) != set(games.slug):
        raise ValueError("Output games differ from selected games")
    for _, game in games.iterrows():
        start, end = game_window(game)
        actual = pd.DatetimeIndex(minutes.loc[minutes.slug == game.slug, "minute"])
        expected = pd.date_range(start, end, freq="min", inclusive="left").astype("datetime64[ns, UTC]")
        if not actual.equals(expected) or len(actual) != 330:
            raise ValueError(f"Incomplete minute grid: {game.slug}")
    for side in ("home", "away"):
        counts = minutes[f"posts_{side}"]
        injuries = minutes[f"injury_{side}"]
        if (counts.dropna() < 0).any() or (injuries.dropna() < 0).any() or (injuries > counts).any():
            raise ValueError("Invalid post counts")
    available = minutes[["posts_home", "posts_away"]].notna().all(axis=1)
    if not np.array_equal(available, minutes.bsky_ok):
        raise ValueError("bsky_ok differs from search availability")
