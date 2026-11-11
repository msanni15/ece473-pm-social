# ECE 473: Social media, news, and prediction markets (Milestone I)

This pilot dataset and analysis link **Polymarket** NBA game-winner (moneyline) markets with hourly
**Bluesky** post counts and **GDELT** news-article counts. They are used to test whether outside
attention helps forecast next-hour price moves and trading volume beyond the market's own history.

* Sample: 8 regular-season games, Oct 21–26, 2026 (see `data/processed/markets.csv`)
* Results: `reports/milestone1_summary.md`
* Validation evidence: `reports/validation_report.md`

## Layout
```
src/pmsocial/         reusable modules
  config.py           paths, endpoints, team names/search terms, sample criteria
  apilog.py           HTTP GET with retry/backoff; logs every request to logs/api_requests.jsonl
  polymarket.py       market discovery/selection, hourly prices, trades
  bluesky.py          hourly post search, dedup, abnormal attention
  gdelt.py            raw GKG 15-min files -> team-matched articles -> hourly counts
  integrate.py        (game, hour) panel, features/targets, structural validation
  models.py           baseline vs enhanced linear models, leave-one-game-out CV
  plots.py            figures + descriptive table
scripts/run_pipeline.py   staged CLI
notebooks/milestone1.ipynb  Colab-compatible walkthrough (runs the pipeline, shows outputs)
tests/                unit tests on synthetic fixtures (logic only, never research data)
data/raw/             cached API responses (the genuine source data)
data/processed/       cleaned/merged datasets, checks, model results
figures/              PNG figures
reports/              Milestone I summary + validation report
logs/                 api_requests.jsonl (every request made) + run logs
```

## API requirements
**No accounts or keys are needed.** All of these were verified on 2026-10-27:

| Source | Endpoint | Notes |
|---|---|---|
| Polymarket metadata | `gamma-api.polymarket.com/events?tag_slug=nba` | public |
| Polymarket prices | `clob.polymarket.com/prices-history?market=<token>&fidelity=60` | long ranges are rejected, so requests are chunked in 5-day pieces |
| Polymarket trades | `data-api.polymarket.com/trades?market=<conditionId>&end=<ts>` | offset paging stops at about 5k trades, so we page backward in time with `end` |
| Bluesky | `api.bsky.app/xrpc/app.bsky.feed.searchPosts` | Without login, only page 1 (≤100 posts) is returned and cursor requests get 403. We query 1-hour windows and split any full window down to 15, 5, then 1 minute. `public.api.bsky.app` returns 403 for search. |
| GDELT | `data.gdeltproject.org/gdeltv2/<YYYYMMDDHHMMSS>.gkg.csv.zip` | The DOC API (`api.gdeltproject.org`) returned HTTP 429 on every request from our network, so we read the raw 15-minute GKG files instead. |

## Run locally
```bash
python3 -m venv .venv && source .venv/bin/activate     # or: uv venv --python 3.11
pip install -r requirements.txt
python -m pytest -q tests
python scripts/run_pipeline.py --all
```
Reruns use the cache in `data/raw/` and finish in about a minute, needing only one network request (a logged
probe of the GDELT DOC API).

To re-download everything from scratch, delete the `data/raw/*` contents first. That takes about 30–60 minutes,
mostly Bluesky hourly searches and about 1,500 GDELT files of about 5 MB each, which are streamed and not stored.

Individual stages: `python scripts/run_pipeline.py --stages merge analyze`.

## Run in Google Colab
1. Zip the project folder as `ece473-pm-social.zip` (the top-level folder inside the zip must be `ece473-pm-social/`).
   On a Mac, right-click the folder and choose **Compress**.
2. Open https://colab.research.google.com, then **File → Upload notebook**, and pick `notebooks/milestone1.ipynb`.
3. In Colab's left sidebar, click the 📁 **Files** icon, then the upload icon, and upload `ece473-pm-social.zip`.
   Wait for the upload to finish.
4. **Runtime → Run all.** The first cell unzips the project, the second installs the requirements, and the rest run
   the pipeline from the cached raw data and display tables and figures.

   *Alternative:* put the unzipped folder in Google Drive at `MyDrive/ece473-pm-social`, skip step 3,
   and approve the Drive-mount prompt when the first cell runs.

## Reproducibility notes
* All timestamps are UTC. Panel row `t` covers `[t, t+1h)`. Features use hour `t` and earlier, and targets are hour `t+1`.
  Only pregame hours are kept: an hour whose interval ends after scheduled tip-off is dropped.
* Missing data is never turned into zero:
  * A failed Bluesky window is stored as NaN.
  * A GDELT hour with fewer than 4 processed files is NaN.
  * Hours without a price snapshot are forward-filled and flagged (`price_observed`).
* The sample is fixed by the rules in `config.py`: moneyline volume ≥ $250k, at least 48 pregame hourly price
  points, highest volume first, and no team used twice.
