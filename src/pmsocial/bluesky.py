"""Bluesky post collection via app.bsky.feed.searchPosts (no authentication).

Verified 2026-10-27: api.bsky.app returns page 1 (<=100 posts) of a search without
login, honours `since`/`until`, and refuses cursor (page 2+) requests with 403.
We therefore query one-hour windows; a window returning a full page of 100 posts
is split into smaller windows until it is under the cap. A window that is still
full at 1-minute resolution is marked truncated (count is a lower bound).
A window whose request fails is recorded as missing, never as zero posts.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import apilog
from .config import BSKY_SEARCH, DATA_RAW, TEAMS

RAW = DATA_RAW / "bluesky"
PAGE = 100
SPLITS = [pd.Timedelta(minutes=15), pd.Timedelta(minutes=5), pd.Timedelta(minutes=1)]


def _iso(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _search(query: str, since: pd.Timestamp, until: pd.Timestamp):
    res = apilog.get(BSKY_SEARCH, {"q": query, "since": _iso(since), "until": _iso(until),
                                   "sort": "latest", "limit": PAGE},
                     source="bluesky", min_interval=0.12, count_fn=lambda r: len(r.get("posts", [])))
    return None if res is None else res.get("posts", [])


def _collect_window(query: str, since: pd.Timestamp, until: pd.Timestamp, level: int = 0):
    """Return (posts, status) where status in {'ok', 'truncated', 'failed'}."""
    posts = _search(query, since, until)
    if posts is None:
        return [], "failed"
    if len(posts) < PAGE:
        return posts, "ok"
    if level >= len(SPLITS):
        return posts, "truncated"
    out, status = [], "ok"
    for s in pd.date_range(since, until - pd.Timedelta(seconds=1), freq=SPLITS[level]):
        sub, st = _collect_window(query, s, min(s + SPLITS[level], until), level + 1)
        out.extend(sub)
        if st == "failed":
            return [], "failed"  # a partial hour is not a valid count
        if st == "truncated":
            status = "truncated"
    return out, status


def _slim(p: dict) -> dict:
    rec = p.get("record", {})
    return {"uri": p["uri"], "author_did": p["author"]["did"], "handle": p["author"].get("handle"),
            "created_at": rec.get("createdAt"), "indexed_at": p.get("indexedAt"),
            "text": rec.get("text", "")}


def collect_team(abbr: str, start: pd.Timestamp, end: pd.Timestamp, workers: int = 4) -> pd.DataFrame:
    """Hourly windows for one team over [start, end). Cached per (team, day)."""
    query = TEAMS[abbr][2]
    RAW.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(start.floor("D"), end - pd.Timedelta(seconds=1), freq="D")
    frames = []
    now = pd.Timestamp.now(tz="UTC")
    for day in days:
        path = RAW / f"{abbr}_{day:%Y%m%d}.json"
        cached = json.loads(path.read_text()) if path.exists() else []
        done = {r["hour"] for r in cached if r["status"] != "failed"}
        hours = [h for h in pd.date_range(day, day + pd.Timedelta(hours=23), freq="h")
                 if start <= h < end and h + pd.Timedelta(hours=1) <= now and h.isoformat() not in done]

        def run(h):
            posts, status = _collect_window(query, h, h + pd.Timedelta(hours=1))
            return {"team": abbr, "query": query, "hour": h.isoformat(), "status": status,
                    "posts": [_slim(p) for p in posts]}

        if hours:
            with ThreadPoolExecutor(workers) as ex:
                new = list(ex.map(run, hours))
            # Failed hours are kept (so they count as missing) and retried on the next run.
            redo = {r["hour"] for r in new}
            cached = sorted([r for r in cached if r["hour"] not in redo] + new, key=lambda r: r["hour"])
            path.write_text(json.dumps(cached))
        frames.append(cached)
    return pd.DataFrame([r for f in frames for r in f])


def posts_table(windows: pd.DataFrame) -> pd.DataFrame:
    """Flatten to one row per (team, unique post)."""
    rows = [{"team": w.team, "window_hour": w.hour, **p} for w in windows.itertuples() for p in w.posts]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["window_hour"] = pd.to_datetime(df.window_hour, utc=True)
    df["created_at"] = pd.to_datetime(df.created_at, utc=True, errors="coerce", format="ISO8601")
    df["indexed_at"] = pd.to_datetime(df.indexed_at, utc=True, errors="coerce", format="ISO8601")
    return df.drop_duplicates(["team", "uri"]).reset_index(drop=True)


def hourly_counts(windows: pd.DataFrame, posts: pd.DataFrame) -> pd.DataFrame:
    """Hourly post count per team. Failed windows -> NaN; truncated windows flagged."""
    w = windows[["team", "hour", "status"]].copy()
    w["hour"] = pd.to_datetime(w.hour, utc=True)
    w = w.drop_duplicates(["team", "hour"])
    n = posts.groupby(["team", "window_hour"]).size().rename("bsky_posts") if len(posts) else None
    w = w.merge(n.reset_index().rename(columns={"window_hour": "hour"}), on=["team", "hour"], how="left") \
        if n is not None else w.assign(bsky_posts=np.nan)
    w["bsky_posts"] = w.bsky_posts.fillna(0.0)
    w.loc[w.status == "failed", "bsky_posts"] = np.nan
    return w.sort_values(["team", "hour"]).reset_index(drop=True)


def abnormal_attention(counts: pd.DataFrame, window: int = 72, min_periods: int = 24) -> pd.DataFrame:
    """log1p(count) minus trailing mean over the previous `window` hours (excludes hour t)."""
    out = []
    for team, g in counts.groupby("team"):
        g = g.sort_values("hour").set_index("hour").asfreq("h")
        g["team"] = team
        x = np.log1p(g.bsky_posts)
        base = x.shift(1).rolling(window, min_periods=min_periods).mean()
        g["bsky_log"] = x
        g["bsky_abnormal"] = x - base
        out.append(g.reset_index())
    return pd.concat(out, ignore_index=True)
