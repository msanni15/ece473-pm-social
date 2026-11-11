# Milestone I Summary: Social media, news, and NBA prediction markets

*ECE 473 · Milestone I (due Oct 29, 2026) · data collected Oct 27, 2026*

## Question
Do Bluesky activity and GDELT news coverage about a team carry information about the **next hour's**
Polymarket price movement or trading volume for that team's game, beyond what the market's own recent
history already contains? For Milestone I, the goal was a validated pilot dataset and a first
baseline-vs-enhanced comparison. It was not meant to settle the question.

## Data pipeline (all real data, no credentials required)
| Source | What we collect | Access route (verified) |
|---|---|---|
| Polymarket | market metadata, both outcome tokens' hourly prices, every pregame taker trade | Gamma `/events`, CLOB `/prices-history`, Data `/trades` (paged backward with `end`) |
| Bluesky | every post matching a team query, searched in 1-hour windows | `api.bsky.app` `searchPosts` without login. Only page 1 is available, so full windows are split down to 15, 5, then 1 minute. |
| GDELT | articles mentioning a team, from all 15-minute GKG files | raw files at `data.gdeltproject.org`. The DOC API was rate-limited (HTTP 429) from our network. |

## Market selection
* **Candidates:** all 49 closed NBA game events from Oct 21–26, 2026, the opening week of the 2026-27 season.
* **Market used:** the moneyline (game-winner) market only.
* **Inclusion criteria:**
  * exactly one moneyline market
  * outcome labels match the two teams in the slug
  * volume ≥ $250k (all 49 qualified)
  * ≥ 48 pregame hourly price points
* **Ordering:** candidates were taken by volume, skipping any game whose team was already in the sample. This keeps a team's attention series from appearing in both a training game and a test game.

### The 8 selected games (UTC tip-off times)
| Game | Tip-off (UTC) | Total moneyline volume | Pregame hours | Pregame trades used | Pregame USDC volume |
|---|---|---|---|---|---|
| Hornets @ Nets | Oct 21 23:30 | $3.84M | 167 | 1,028 | $0.40M |
| Cavaliers @ 76ers | Oct 22 23:00 | $8.25M | 167 | 2,207 | $1.34M |
| Nuggets @ Thunder | Oct 23 01:30 | $5.11M | 163 | 1,160 | $0.25M |
| Bulls @ Bucks | Oct 23 20:00 | $4.00M | 164 | 881 | $0.48M |
| Knicks @ Celtics | Oct 23 23:00 | $3.80M | 167 | 1,205 | $0.74M |
| Rockets @ Spurs | Oct 24 01:30 | $3.17M | 163 | 566 | $0.08M |
| Raptors @ Timberwolves | Oct 25 23:00 | $3.34M | 167 | 1,805 | $1.30M |
| Grizzlies @ Jazz | Oct 27 01:00 | $5.56M | 163 | 1,036 | $1.74M |

Event IDs, market IDs, condition IDs and both token IDs are in `data/processed/markets.csv`. That file also lists every excluded candidate with its reason: 33 were "not needed (sample full)" and 8 were "team already in sample".

## Variables (hourly panel, UTC)
* **Row and window:** each row is one (game, hour t) pair and describes the interval [t, t+1h). Only hours ending at or before scheduled tip-off are kept.
* **`p_home`:** home-team win probability at the end of hour t, taken from the CLOB hourly snapshot. All snapshots land within the first 59 s of the hour.
* **`dp`, `abs_dp`:** the hourly change in probability and its absolute value.
* **`n_trades`, `volume_usd`:** the hour's trade count and USDC notional (size × price).
* **`bsky_posts_{home,away}`:** the hour's Bluesky post count per team.
* **`bsky_abn_{home,away}`:** abnormal attention, defined as log(1 + posts) minus its mean over the previous 72 hours. Hour t itself is excluded from that mean.
* **`gdelt_{home,away}`:** GDELT article count per team.
* **`hours_to_game`:** hours remaining until tip-off.
* **Targets:** `abs_dp_next` and `log_vol_next`, which are hour t+1's |Δp| and log(1 + volume).

The final panel has **1,321 game-hours across 8 games**. The model sample is 1,289 rows: rows with any missing feature or target are dropped, and every model uses the same rows.

## Descriptive results
* **Prices change rarely and in ticks.**
  * Median hourly |Δp| is 0; the 90th percentile is 1 percentage point (pp) and the maximum 9.5 pp.
  * Home teams were priced between 0.445 and 0.745 (Figure 1).
  * Many hours are flat because Polymarket prices move in 0.5-pp increments.
* **Trading is concentrated in the final hours before tip-off.** Only 26–41% of pregame hours contain any trade (Figure 5). Mean hourly volume is $4.8k, but the maximum is $1.38M, all in the last hours before tip-off.
* **Bluesky attention is real but uneven.**
  * Mean posts per team-hour range from 0.7 (Nets, Thunder) to 21.9 (Knicks).
  * Spikes line up with identifiable events. Examples: Knicks/Celtics around the Oct 20–21 opener (up to 495 posts per hour), and the 76ers around the LeBron James debut (Figure 2).
* **GDELT coverage** is steadier, with a mean of about 4 articles per team-hour and clear pre-game peaks (Figure 3).
* **Raw relationship with next-hour market activity:** essentially none.
  * Bluesky abnormal attention vs. next-hour |Δp| has Spearman ρ = 0.01; vs. next-hour log volume, ρ = −0.03 (Figure 4).

## Preliminary forecasting comparison (leave-one-game-out, 8 folds)
| Target | Train-mean | Baseline (market only) | + Bluesky | + Bluesky + GDELT |
|---|---|---|---|---|
| next-hour \|Δp\| (MAE, pp) | 0.366 | **0.340** | 0.349 | 0.349 |
| next-hour log(1+volume) (MAE) | 2.583 | **0.985** | 0.990 | 0.987 |

* **Baseline features:** current and lagged |Δp|, current and lagged log volume, and log hours to game.
* **Enhanced features:** the baseline plus home and away Bluesky abnormal attention, log total posts, and (in the last column) log GDELT articles.
* **Models:** OLS on standardized features. Ridge regression gives the same numbers to 3 decimals.

**Result: the external features did not improve out-of-sample forecasts in this pilot.**
* For |Δp|, the enhanced models were worse in 6–7 of 8 held-out games.
* For volume, they were better in 5 of 8 games, but worse on average by 0.002–0.005 MAE.
* The market-only baseline does improve clearly on a constant forecast, especially for volume, because volume is strongly persistent and rises near tip-off.
* A robustness check gives the same conclusion: dropping hours whose prices had to be forward-filled (838 rows left) still shows no gain from the social and news variables (`model_diffs_observed_prices.csv`).

This is a null or inconclusive result. It should not be read as evidence that attention is irrelevant, for the reasons below.

## Limitations
1. **Small sample.** There are 8 games and 8 folds, so differences of a few thousandths of MAE are well inside fold-to-fold noise. No significance testing has been done yet.
2. **Hourly resolution and coarse price ticks.** Polymarket prices move in 0.5-pp ticks, and most hours have |Δp| = 0. Effects that play out within minutes, such as injury news, are averaged away at this resolution.
3. **Attention measures are noisy.**
   * **Bluesky:** 82% of matched posts contain the search term in their text; the rest presumably matched on link cards or alt text. Each team has a single search query: ambiguous nicknames are searched by full name, which undercounts posts like "Heat win!".
   * **GDELT:** matches include league-wide roundups that mention a team only in passing. Only 29% of matched articles have the team nickname in their URL.
4. **Shared shocks.** League-wide events, such as opening night or a major trade, raise attention and market activity together. These are predictive associations, not causal effects.
5. **Pregame window only.** In-game hours are excluded, and the last partial hour before a :30 tip-off is dropped.
6. **API constraints.**
   * Bluesky's unauthenticated search caps each query at 100 posts. Our splitting kept every window below the cap: 13 hour windows were split, and none remained truncated.
   * The GDELT DOC API was unavailable from our network, so we used the raw files instead.

## Next steps (Milestone II, Nov 12)
1. **Expand the sample** to 40–80 games from the first 3–4 weeks of the season. The pipeline is cached and incremental, and GDELT matches already cover all 30 teams.
2. **Add statistical inference:** a Diebold-Mariano-style paired test on per-game loss differences, plus clustered regressions for in-sample association.
3. **Test alternative attention definitions:**
   * multiple queries per team (e.g. "Cavs", "Sixers")
   * stricter GDELT matching (URL or headline)
   * abnormal-news measures
   * 15-minute bins
4. **Try different horizons and targets:** 3-hour and 6-hour changes, the final 24 hours only, and direction of movement.
5. **Final paper:** the reverse direction (market moves leading to later attention) and sentiment, once the main result is established.
