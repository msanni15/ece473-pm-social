"""ESPN NBA play-by-play with wall-clock timestamps (public site API, no key).

Verified 2026-11-11: /scoreboard?dates=YYYYMMDD lists the games of a US date; /summary?event=ID
returns every play with `wallclock` (UTC, 1 s resolution), the running score, `scoringPlay`,
and ESPN's home win probability per play (`winprobability`, joined on playId).
"""
import json
import re

import pandas as pd

from . import apilog
from .config import DATA_RAW, ESPN_API, TEAMS

RAW = DATA_RAW / "espn"
PERIOD_SEC, OT_SEC = 720, 300


def _cached(name: str, url: str, params: dict, keep=None) -> dict:
    path = RAW / name
    if path.exists():
        return json.loads(path.read_text())
    res = apilog.get(url, params, source="espn", min_interval=0.5)
    if res is None:
        raise RuntimeError(f"ESPN request failed: {url} {params}")
    if keep:
        res = {k: res.get(k) for k in keep}
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res))
    return res


def find_event(game: pd.Series) -> dict:
    """The ESPN competition matching a Polymarket game, by full team names and home/away."""
    date = game.game_date_local.replace("-", "")
    sb = _cached(f"scoreboard_{date}.json", f"{ESPN_API}/scoreboard", {"dates": date})
    want = {"home": TEAMS[game.home][0], "away": TEAMS[game.away][0]}
    for ev in sb.get("events", []):
        teams = {c["homeAway"]: c["team"]["displayName"] for c in ev["competitions"][0]["competitors"]}
        if teams == want:
            return ev
    raise LookupError(f"no ESPN event for {game.slug}")


def _clock_sec(s: str) -> float:
    m = re.fullmatch(r"(\d+):(\d+(?:\.\d+)?)", s)
    return int(m.group(1)) * 60 + float(m.group(2)) if m else float(s)


def sec_remaining(period: int, clock: str) -> float:
    """Game seconds left in regulation; in overtime, seconds left in the current OT."""
    c = _clock_sec(clock)
    return c + (4 - period) * PERIOD_SEC if period <= 4 else c


def plays_table(game: pd.Series) -> pd.DataFrame:
    """One row per play, with UTC wall-clock time, score after the play, and ESPN win prob."""
    ev = find_event(game)
    s = _cached(f"summary_{ev['id']}.json", f"{ESPN_API}/summary", {"event": ev["id"]},
                keep=("plays", "winprobability", "header"))
    comp = s["header"]["competitions"][0]
    home_id = next(c["team"]["id"] for c in comp["competitors"] if c["homeAway"] == "home")
    wp = {w["playId"]: w["homeWinPercentage"] for w in s.get("winprobability") or []}
    rows = []
    for p in s["plays"]:
        team = (p.get("team") or {}).get("id")
        scoring = bool(p.get("scoringPlay"))
        rows.append({
            "slug": game.slug, "espn_event_id": ev["id"], "play_id": p["id"],
            "ts": pd.Timestamp(p["wallclock"]) if p.get("wallclock") else pd.NaT,
            "period": p["period"]["number"], "clock": p["clock"]["displayValue"],
            "text": p.get("text", ""), "scoring_play": scoring,
            "points": int(p.get("scoreValue") or 0) if scoring else 0,
            "scoring_side": ("home" if team == home_id else "away") if scoring else None,
            "score_home": int(p["homeScore"]), "score_away": int(p["awayScore"]),
            "espn_wp_home": wp.get(p["id"]),
        })
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df.ts, utc=True)
    df["sec_remaining"] = [sec_remaining(p, c) for p, c in zip(df.period, df.clock)]
    return df
