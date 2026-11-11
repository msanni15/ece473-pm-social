"""GDELT news coverage from the raw GDELT 2.0 GKG 15-minute files.

The DOC 2.0 API (api.gdeltproject.org) returned HTTP 429 on every request from our
network on 2026-10-27, including the first, so it is unusable here. The raw GKG
files (data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip) need no
account and have full history. Each file lists articles GDELT processed in the
15 minutes ending at its timestamp.

We stream each file in memory, keep only articles matching any NBA team, and
cache the filtered rows per day. Matching is done for all 30 teams so the sample
can grow without re-downloading.
"""
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import apilog
from .config import DATA_RAW, GDELT_DOC_API, GDELT_FILES, TEAMS

RAW = DATA_RAW / "gdelt"
# GKG 2.1 column positions
URL, SOURCE, PERSONS, ORGS, TONE, ALLNAMES = 4, 3, 11, 13, 15, 23


def _patterns() -> dict[str, re.Pattern]:
    pats = {}
    for abbr, (full, nick, query) in TEAMS.items():
        terms = [full]
        if not query.startswith('"'):  # distinctive nickname, safe on its own
            terms.append(nick)
        if abbr == "okc":
            terms.append("OKC Thunder")
        pats[abbr] = re.compile(r"\b(" + "|".join(re.escape(t.lower()) for t in terms) + r")\b")
    return pats


PATTERNS = _patterns()


def probe_doc_api() -> int | None:
    """One logged request to the DOC API, to document its availability."""
    res = apilog.get(GDELT_DOC_API, {"query": '"Los Angeles Lakers"', "mode": "timelinevolraw",
                                     "format": "json", "timespan": "1d"},
                     source="gdelt_doc_api", retries=1, count_fn=lambda r: 1)
    return None if res is None else 1


def _process_file(ts: pd.Timestamp) -> dict:
    url = f"{GDELT_FILES}/{ts:%Y%m%d%H%M%S}.gkg.csv.zip"
    blob = apilog.get(url, source="gdelt_gkg_file", as_json=False, retries=3, timeout=120,
                      count_fn=lambda b: len(b))
    if blob is None:
        return {"file_ts": ts, "status": "missing", "n_articles": np.nan, "matches": []}
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        return {"file_ts": ts, "status": "corrupt", "n_articles": np.nan, "matches": []}
    lines = [l for l in text.split("\n") if l]
    matches = []
    for line in lines:
        f = line.split("\t")
        if len(f) <= ALLNAMES:
            continue
        hay = " ".join([re.sub(r"[-_/.]", " ", f[URL]), f[ORGS], f[PERSONS], f[ALLNAMES]]).lower()
        for abbr, pat in PATTERNS.items():
            if pat.search(hay):
                tone = f[TONE].split(",")[0] if f[TONE] else ""
                matches.append({"file_ts": ts, "team": abbr, "url": f[URL], "source": f[SOURCE],
                                "tone": float(tone) if tone else np.nan})
    return {"file_ts": ts, "status": "ok", "n_articles": len(lines), "matches": matches}


def collect(start: pd.Timestamp, end: pd.Timestamp, workers: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process all 15-minute files with timestamps in (start, end]. Returns (manifest, articles)."""
    RAW.mkdir(parents=True, exist_ok=True)
    mans, arts = [], []
    for day in pd.date_range(start.floor("D"), end, freq="D"):
        mpath, apath = RAW / f"manifest_{day:%Y%m%d}.csv", RAW / f"articles_{day:%Y%m%d}.csv"
        stamps = pd.date_range(day + pd.Timedelta(minutes=15), day + pd.Timedelta(days=1), freq="15min")
        stamps = stamps[(stamps > start) & (stamps <= end)]
        m = pd.DataFrame(columns=["file_ts", "status", "n_articles"])
        a = pd.DataFrame()
        if mpath.exists():
            m = pd.read_csv(mpath)
            m["file_ts"] = pd.to_datetime(m.file_ts, utc=True)
            if apath.exists() and apath.stat().st_size > 1:
                a = pd.read_csv(apath)
                a["file_ts"] = pd.to_datetime(a.file_ts, utc=True)
        # Only process files not already cached successfully (missing ones are retried).
        todo = [t for t in stamps if t not in set(m.loc[m.status == "ok", "file_ts"])]
        if todo:
            with ThreadPoolExecutor(workers) as ex:
                res = list(ex.map(_process_file, todo))
            new_m = pd.DataFrame([{k: r[k] for k in ("file_ts", "status", "n_articles")} for r in res])
            new_a = pd.DataFrame([x for r in res for x in r["matches"]])
            m = pd.concat([m[~m.file_ts.isin(todo)], new_m], ignore_index=True).sort_values("file_ts")
            a = pd.concat([a, new_a], ignore_index=True) if len(new_a) else a
            m.to_csv(mpath, index=False)
            a.to_csv(apath, index=False)
        m["file_ts"] = pd.to_datetime(m.file_ts, utc=True)
        mans.append(m)
        if len(a):
            a["file_ts"] = pd.to_datetime(a.file_ts, utc=True)
            arts.append(a)
    man = pd.concat(mans, ignore_index=True)
    man = man[(man.file_ts > start) & (man.file_ts <= end)]
    art = pd.concat(arts, ignore_index=True) if arts else pd.DataFrame(columns=["file_ts", "team", "url"])
    art = art[(art.file_ts > start) & (art.file_ts <= end)]
    # The same article URL can reappear in later files; keep its first appearance per team.
    art = art.sort_values("file_ts").drop_duplicates(["team", "url"]).reset_index(drop=True)
    return man.reset_index(drop=True), art


def hourly_counts(man: pd.DataFrame, art: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    """Articles per team per hour. A file stamped T covers (T-15min, T], so it belongs to
    hour floor(T - 1s). Hours with fewer than 4 processed files are NaN."""
    man = man.assign(hour=(man.file_ts - pd.Timedelta(seconds=1)).dt.floor("h"))
    cov = man.groupby("hour").agg(n_files_ok=("status", lambda s: (s == "ok").sum()),
                                  n_articles_all=("n_articles", "sum"))
    art = art.assign(hour=(art.file_ts - pd.Timedelta(seconds=1)).dt.floor("h"))
    cnt = art.groupby(["team", "hour"]).size()
    out = []
    for t in teams:
        g = cov.copy()
        g["team"] = t
        g["gdelt_articles"] = cnt.get(t, pd.Series(dtype=float)).reindex(g.index).fillna(0.0)
        g.loc[g.n_files_ok < 4, "gdelt_articles"] = np.nan
        out.append(g.reset_index())
    return pd.concat(out, ignore_index=True)
