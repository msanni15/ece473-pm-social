# Milestone I Validation Report

*Generated Oct 27, 2026. The evidence comes from `logs/api_requests.jsonl` (every pipeline request),
`data/processed/*_checks.*`, and the run logs in `logs/`.*

## 1. Data sources accessed
| Source | Endpoint | Pipeline requests (HTTP status) | Usable? |
|---|---|---|---|
| Polymarket Gamma | `/events?tag_slug=nba&closed=true` | 2 (200) | ✅ 49 game events, Oct 21–26 |
| Polymarket CLOB | `/prices-history` (fidelity 60, 5-day chunks) | 32 (200) | ✅ 1,148 home + 1,161 away hourly points (2,309 total) over 16 tokens |
| Polymarket Data | `/trades?market=…&end=…` | 15 (200) | ✅ 10,197 pregame taker trades (9,888 fall in full pregame hours used by the panel) |
| Bluesky | `api.bsky.app/xrpc/app.bsky.feed.searchPosts` | 6,209 (all 200) | ✅ 5,776 of 5,776 team-hours retrieved; 28,115 unique posts |
| Bluesky (documented host) | `public.api.bsky.app/...searchPosts` | manual probes: 403 | ❌ requires login for search |
| Bluesky cursor pages | `cursor=` on `api.bsky.app` | manual probe: 403 | ❌ worked around with time-window splitting |
| GDELT raw GKG | `data.gdeltproject.org/gdeltv2/*.gkg.csv.zip` | 1,516 (200), 24 (404) | ✅ 1,444 of 1,444 files in window processed; 31,809 team-matched articles (18,334 for sample teams) |
| GDELT DOC API | `api.gdeltproject.org/api/v2/doc/doc` | 5 (429), 1 (200) | ⚠️ throttled on 5 of 6 attempts; not used |

* **GDELT 404s:** all 24 were requests for files that did not exist yet, from the first run on the then-incomplete current day. Every file in the analysis window was retrieved.
* **Coverage window:**
  * Polymarket: market creation (Oct 15–20) through tip-off.
  * Bluesky and GDELT: Oct 12 00:00 to Oct 27 01:00 UTC. This includes 72 hours before the earliest market opened, which serves as the attention baseline.

## 2. Execution steps completed
| Step | Result |
|---|---|
| Read-only API probes before building | ✅ done for all 3 sources (see §1) |
| Single-game end-to-end test (Cavaliers @ 76ers) | ✅ all three sources collected and aligned |
| `run_pipeline.py --all`, full collection | ✅ select, polymarket, bluesky (~55 min), gdelt (~25 min), merge, analyze |
| Unit tests (`pytest`, 9 tests, synthetic fixtures only) | ✅ 9 passed (Python 3.11 with pandas 3.1; Python 3.12 with pandas 2.2.2) |
| Clean-environment rerun | ✅ fresh venv from `requirements.txt`, `data/processed` and `figures` emptied, full pipeline rerun from the raw cache: exit 0, 24 s |
| Reproducibility | ✅ clean-run outputs are **identical** to the original (markets, the three hourly source tables, panel, model folds, robustness results) |
| Colab-like library versions | ✅ pandas 2.2.2, numpy 2.0.2, scikit-learn 1.6.1, matplotlib 3.10: identical outputs |
| Notebook executed headless (`nbconvert --execute`) | ✅ 0 errors, 6 figures rendered, tests pass inside the notebook |
| Figures inspected visually | ✅ all 6 PNGs checked for correct titles, units, dates and legends |

*Not done:* running inside an actual Google Colab session. That needs your Google account. The Colab-like environment test and the headless notebook run above are the closest substitutes.

## 3. Market identity and outcome checks (`polymarket_checks.csv`)
* **Token-to-team mapping:** tokens are assigned to teams by **outcome label**, never by list position. A unit test feeds reversed outcome order to confirm this.
* **Complementary prices:** p_home + p_away = 1 for every pregame hour in 7 games. The 8th (Raptors @ Timberwolves) deviates by at most 0.005, which is one tick.
* **Trade attribution:** 0 trades carry the wrong `conditionId`, 0 have an asset outside the market's two tokens, and 0 occur at or after tip-off.
* **Trade completeness:** trades were paged backward by timestamp until the API returned a short page. A direct query for trades before each market's earliest retrieved trade returned 0 rows (checked for Cavaliers @ 76ers), so early zero-trade hours are genuine zeros.

## 4. Timestamp and timezone checks
* **UTC everywhere:**
  * Polymarket timestamps are unix seconds.
  * Bluesky `since`/`until` are ISO-8601 with `Z`.
  * GDELT file names are UTC.
  * The panel's `hour` column is tz-aware UTC (asserted in `validate_panel`).
* **Price snapshot timing:** all 2,309 CLOB price points fall between 3 and 59 seconds past the hour, so labelling each one with its floored hour is unambiguous.
* **Price alignment fix:** an early version labelled an hour's price with the snapshot taken at the *start* of that hour, which would have overlapped with that hour's social data. This was corrected: row t now uses the snapshot at t+1h. A unit test covers it.
* **Bluesky window check:** 99.8% of posts have `createdAt` inside their query window (offset 0–1 h). The search filters on Bluesky's sort time, and that is what we bucket on.
* **GDELT hour assignment:** a file stamped T covers (T−15 min, T], so it is assigned to hour floor(T − 1 s). A unit test covers this.

## 5. Merged panel checks (`panel_checks.json`)
| Check | Result |
|---|---|
| Rows / games | 1,321 / 8 |
| Duplicate (game, hour) rows | 0 |
| Rows whose interval ends after tip-off | 0 |
| Targets whose interval ends after tip-off | 0 |
| Non-hourly gaps within a game | 0 |
| Bluesky windows failed or truncated | 0 / 0 (13 full windows were split and resolved) |
| GDELT hours with fewer than 4 files | 0 |
| Missing `p_home_obs` (no snapshot in that hour) | 188 (14%), forward-filled and flagged `price_observed=False`; a robustness model excludes them |
| Other missing values | only the structural ones: the first hour of each game before any price (8 rows), lags at series start, and the last row's next-hour target |

## 6. Leakage and split checks
* **Feature timing:** features use hour t and earlier, and targets are hour t+1. Shifts are applied within each game only; a unit test confirms the last row's target is NaN rather than borrowed from another game.
* **Abnormal attention:** uses `shift(1)` before the rolling mean. A unit test changes the future values and shows that past values don't change.
* **Train/test split:** leave-one-game-out. A runtime assertion in `models.evaluate` checks that training and test games are disjoint, and a unit test checks it too.
* **Teams across folds:** each team appears in only one game, so no team's attention series spans training and test.
* **Selection timing:** the sample was chosen using only volume and data-availability criteria, never outcomes or model results.

## 7. Relevance checks
* **Bluesky:**
  * Ambiguous nicknames are searched by full name. Bare "Heat" returned 96 posts in one test hour, nearly all unrelated; "Miami Heat" returned 4, all relevant.
  * 82% of collected posts contain the query term in their text (per team: 56–88%), and 4% have no text.
* **GDELT:**
  * Sampled URLs are mostly NBA coverage: previews, recaps and fan sites.
  * Some league-wide roundups and a few off-topic matches also appear, e.g. a GTA article mentioning the Miami Heat arena, and a Dolphins ownership story.
  * Only 29% of matched articles have the team nickname in their URL.

## 8. Unresolved limitations
1. The GDELT DOC API is effectively unavailable from this network; the raw-file workaround is complete and needs no account.
2. Bluesky depends on an undocumented behaviour: `api.bsky.app` allows unauthenticated page-1 search. If that changes, the fallback is a login with an app password (a code change in `bluesky._search`).
3. The pilot has only 8 games, so model comparisons are underpowered.
4. Attention measures are keyword-based and include some noise (see §7).
5. The notebook has not yet been run inside an actual Google Colab session (see §2).
