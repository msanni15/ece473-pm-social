# Milestone II plan: in-game pilot (due Nov 12)

## What Milestone II requires
The proposal says: *Expand and clean the dataset and complete the primary empirical analysis. Compare
market-only models with models incorporating news and social-media information, evaluate results on
held-out events, and conduct initial robustness checks across sports, time horizons, and alternative
attention measures.*

The professor's feedback narrows this:
- **One social-media source** is enough, so we use Bluesky only and drop GDELT.
- **Analyse the games themselves.** Information and price movement happen during the game, and markets
  absorb information within seconds. We therefore model **in-game, minute by minute**.
- **Show results on a few games first.** We use 3 pilot games (`cle-phi`, `nyk-bos`, `mem-uta`), then all 8
  Milestone I games.
- **State the main metric and the baseline, and explain how the media data enters the price.** See
  "Analysis design" below.

## Analysis design
- **Target:** the change in the log-odds of the home team winning over the next minute,
  Δℓ = logit(p at t+1) − logit(p at t). A 5-minute horizon is a robustness check.
- **Main metric:** out-of-sample RMSE of Δℓ, with each game held out in turn. A Diebold–Mariano test
  checks whether the baseline-vs-Bluesky difference is real. Secondary metrics are MAE and how often
  the direction of the move is predicted correctly.
- **Baselines:**
  - **B0 (no change):** Δℓ = 0. This is the efficient-market benchmark.
  - **B1 (market + game state):** regression on recent price moves, trades, order flow, score margin,
    points scored in the last minute, and time remaining.
- **Enhanced model:** B1 plus Bluesky features.
- **How Bluesky enters the price:** the forecast is p̂(t+1) = logistic(logit p(t) + predicted Δℓ).
- **Attention measures (robustness):**
  1. raw post counts
  2. abnormal attention
  3. home-vs-away imbalance
  4. injury-keyword counts
- **Timing:** event studies around scoring plays and big price jumps show who reacts first, the market or
  Bluesky.

## Who owns what
Never edit the other person's files. Read-only imports from them are fine. If you need a change in a
file you don't own, ask its owner.

| | **Alicia** | **Partner** |
|---|---|---|
| Branch | `alicia/market-models` | `partner/bluesky-ingame` |
| Files | `src/pmsocial/polymarket.py`, `espn.py`, `ingame.py`, `ingame_models.py`, `ingame_plots.py`, `scripts/run_ingame_market.py`, `scripts/run_ingame_analysis.py`, `tests/test_ingame_market.py`; shared files `config.py`, `requirements.txt`, `README.md` | `src/pmsocial/bluesky_ingame.py`, `timing.py`, `scripts/run_ingame_social.py`, `scripts/run_timing.py`, `tests/test_ingame_social.py` |
| Produces (`data/processed/`) | `ingame_events.parquet`, `ingame_market_minute.parquet`, `ingame_trades.parquet`, `ingame_panel.parquet` | `ingame_bluesky_posts.parquet`, `ingame_bluesky_minute.parquet` |

Merge into `main` only through pull requests.

## Data contract
- **Games:** rows of `data/processed/markets.csv` with `selected == True`. Use the columns `slug`, `home`,
  `away` (lowercase team abbreviations) and `game_start_utc`.
- **Time:**
  - All timestamps are pandas `datetime64[ns, UTC]`.
  - `minute` is floored to the minute, and row `minute` covers [minute, minute + 1 min).
- **Window per game:** W = [game_start_utc − 2 h, game_start_utc + 3 h 30 min), which is 330 minutes.
  Produce one row per minute of W, even when a minute has zero posts. Alicia trims to the actual final
  buzzer later.
- **Missing vs. zero:** if a request for a time window failed, every minute in that window is **NaN**,
  never 0.

### Partner's output files
**`ingame_bluesky_posts.parquet`**, one row per post per game side:

| column | meaning |
|---|---|
| `slug`, `side`, `team` | game; `"home"`/`"away"`; lowercase team abbreviation |
| `query` | the search term that found the post |
| `uri`, `text` | post id and text |
| `created_at`, `indexed_at` | UTC timestamps from the API |
| `sort_at` | `min(created_at, indexed_at)`, the time Bluesky's `since`/`until` filter uses; **minute binning uses this column** |
| `kw_injury` | True if `text` matches `(?i)injur\|hurt\|ankle\|knee\|locker room\|ruled out\|questionable\|limp` |

Deduplicate on (`slug`, `side`, `uri`).

**`ingame_bluesky_minute.parquet`**, one row per (`slug`, `minute`) in W:

| column | meaning |
|---|---|
| `posts_home`, `posts_away` | posts with `sort_at` in that minute; NaN if that minute's search failed |
| `abn_home`, `abn_away` | log1p(posts) minus the mean of log1p(posts) over the 120 minutes before tip-off, i.e. [game_start − 2 h, game_start) |
| `imbalance` | log1p(posts_home) − log1p(posts_away) |
| `injury_home`, `injury_away` | count of `kw_injury` posts in that minute |
| `bsky_ok` | True if both sides' searches succeeded for that minute |

### Alicia's output files
**`ingame_events.parquet`** (from ESPN), one row per play:

| column | meaning |
|---|---|
| `slug`, `ts` | game; ESPN wall-clock time of the play (UTC) |
| `period`, `clock`, `text` | quarter, game clock, play description |
| `scoring_play`, `points` | whether it scored, and how many points |
| `scoring_side` | `"home"`/`"away"`, or empty |
| `score_home`, `score_away` | score after the play |
| `espn_wp_home` | ESPN's home win probability after the play |

**`ingame_market_minute.parquet`**, one row per (`slug`, `minute`) in W:

| column | meaning |
|---|---|
| `p_home` | Polymarket home-win price at the **end** of the minute: the last trade price, or the CLOB 1-minute snapshot when the minute has no trade, else carried forward. Trades exist in 96–100% of in-game minutes; CLOB snapshots alone have gaps of up to 6 minutes. |
| `p_vwap`, `p_clob` | the within-minute average trade price and the CLOB snapshot series, kept for robustness checks. **Do not use them for timing:** both lag the minute's scoring (see "Findings so far"). |
| `price_source` | `trades` / `clob` / `ffill` |
| `logit_p` | log-odds of `p_home`, with p clipped to [0.01, 0.99] |
| `price_observed` | False if the price was carried forward from an earlier minute |
| `n_trades`, `volume_usd` | trades and dollar volume in the minute |
| `flow_home` | signed USD of buying pressure on the home team |
| `score_home`, `score_away`, `score_diff` | score at the end of the minute |
| `pts_home`, `pts_away` | points scored in the minute |
| `sec_remaining` | game time remaining |
| `espn_wp_home` | ESPN's home win probability at the end of the minute |
| `in_game` | True from tip-off to the final buzzer |

## Findings so far (market side, Nov 11)
- **The market absorbs a basket within about 10 seconds.** Across 911 scoring plays in the 8 games, the
  price moves about 3 percentage points toward the scorer. About 2.3 points of that come within 5 seconds of
  ESPN's play time, and the move is complete by about 30 seconds. See
  `figures/fig_m2_scoring_reaction.png` and `data/processed/ingame_scoring_reaction.csv`.
- **With end-of-minute prices, nothing beats "no change".** B1 (market + game state) has the same RMSE as
  B0 at 1 minute (−0.04%, Diebold–Mariano p = 0.97) and is slightly worse at 5 minutes. Within-minute
  average prices make B1 look 17% better, but that is a timing artifact: the average lags baskets scored
  late in the minute.
- **What this means for Bluesky.** Posts arrive at about one per minute per team, so Bluesky cannot lead
  the market on scoring plays. Any value has to come from information that is not in the score, such as
  injuries or lineup news. The injury-keyword measure and the timing analysis are therefore central.
- **For task 5 (timing analysis):** the market's own reaction to scoring plays at second resolution is
  already done (above). Focus the event studies on **Bluesky's** reaction: posts per minute around scoring
  plays and big price jumps, and the lead–lag cross-correlation. You can overlay `p_home` from
  `ingame_market_minute.parquet`.

## Partner's tasks
1. **Setup.**
   - Clone the repo and run `git checkout -b partner/bluesky-ingame`.
   - Create a Python 3.11 environment and run `pip install -r requirements.txt`.
   - Run `pytest`; all 9 existing tests should pass.
2. **Collect in-game Bluesky posts** (`src/pmsocial/bluesky_ingame.py`, `scripts/run_ingame_social.py`).
   - Import and reuse `_collect_window`, `_slim` and `posts_table` from `src/pmsocial/bluesky.py`. Do not
     edit that file.
   - `_collect_window(query, since, until)` already handles Bluesky's 100-posts-per-search cap by
     splitting busy windows. It returns status `failed` when a request fails; treat those minutes as NaN.
   - Query each game's window W in **1-hour chunks** for both teams.
   - **Search terms:**
     - Each team's existing term is `TEAMS[abbr][2]` in `src/pmsocial/config.py`.
     - You may add **one** short nickname per team (Cavs, Sixers, Grizz, Wolves, …).
     - Keep a nickname only if at least 14 of 20 sampled posts are about that team. Record each check in
       `data/processed/ingame_query_checks.csv`.
     - Run each term as its own search, then deduplicate posts.
   - Cache raw responses under `data/raw/bluesky_ingame/` so reruns don't re-download.
   - The Bluesky API needs no login. Keep requests at least 0.12 s apart; `apilog.get` already does this
     when called through `_search`.
3. **Build `ingame_bluesky_minute.parquet`** exactly as the contract specifies, then push it. Alicia's
   models need it.
4. **Relevance check.** Read 50 random in-game posts and report the share that are actually about the game.
5. **Timing analysis** (`src/pmsocial/timing.py`, `scripts/run_timing.py`).
   - Start once Alicia has pushed `ingame_events.parquet` and `ingame_market_minute.parquet`.
   - Make two event-study figures, each averaging `p_home` (from the scoring team's perspective) and
     Bluesky posts per minute from −10 to +10 minutes:
     - one around **scoring plays**;
     - one around **big price jumps**, where |Δp| ≥ 0.05 within one minute.
   - Compute the cross-correlation between minute Δ`logit_p` and Bluesky posts at lags −10 to +10.
   - Save the figures to `figures/` as `fig_m2_*.png`.
   - These answer the question of who moves first.
6. **Tests** (`tests/test_ingame_social.py`), using synthetic data only:
   - failed windows give NaN, not 0;
   - minute binning on `sort_at` is correct;
   - deduplication works.
7. **Draft write-up sections** in a shared Google Doc:
   - the revised research question;
   - responses to the professor's six points, using the "Analysis design" section above;
   - the Bluesky data and the four attention measures, with counts per game;
   - the relevance check;
   - the timing results.

## Schedule
- **Tonight:**
  - Partner: tasks 1–3.
  - Alicia: in-game market and ESPN data.
- **Next:**
  - Partner: tasks 4–6.
  - Alicia: merge and models.
- **Nov 12 morning:**
  - Partner: task 7.
  - Alicia: figures and report assembly.
- **Hand-offs:**
  - The partner's task 5 needs Alicia's market and ESPN files.
  - Alicia's Bluesky models need the partner's minute file.
