# Milestone II: Bluesky methods and implementation handoff

Prepared November 11, 2026. Branch: `partner/bluesky-ingame`.

This is an AI-assisted methods and handoff document, not submission-ready
introduction, findings, or conclusion prose. The students should write those
sections independently under the course policy. Annotation labels below are
explicitly provisional AI-assisted text judgments, not a human validation study.

## Scope and research-design notes

The implemented social-data component supports testing whether minute-level
Bluesky attention adds forecasting information beyond market history and game
state in eight NBA games. GDELT is outside this component. The three pilot games
are Cavaliers–76ers, Knicks–Celtics, and Grizzlies–Jazz; the exported social tables
already include all eight selected games.

The written plan specifies next-minute **log-odds change**, not probability change:

`y(t,h) = logit(p(t+h)) - logit(p(t))`, with `h=1` and a five-minute check.

The model owner's contract clips price to `[0.01, 0.99]` before taking log-odds.
Forecast probabilities are reconstructed by
`logistic(logit(p(t)) + predicted_y(t,h))` under the same clipping convention.
RMSE of log-odds change is the plan's primary metric, with MAE and direction as
secondary metrics. Decide explicitly how zero changes count in direction accuracy.
RMSE in log-odds units and RMSE in probability units are different quantities.

The model owner's baselines are B0 (zero change) and B1 (market history, trading,
buy/sell pressure, and game state). Social features enter the enhanced regression
as additional predictors; this component does not execute trades or alter market
quotes. Zero log-odds change is a useful persistence benchmark, but should not be
described as a mathematical implication of efficient probability prices: a
nonlinear logit transformation need not preserve a martingale's zero mean change.

## Status and file handoff

- Completed: collection, all four attention measures, exact Parquet exports,
  synthetic unit tests, reproducible cached rerun, provisional relevance review.
- Completed with real market/ESPN inputs after market PR #2 was merged by Alicia:
  timing calculations, two event-study figures, lead-lag correlations, and
  all-eight-game injury-keyword timelines. The run includes 911 scoring-play
  windows and 185 large-price-jump windows; all have complete 21-minute windows.
  Forecast-model integration and results remain the market/model owner's work.
- Optional nickname expansion was not used. The existing Milestone I search term
  for each team is recorded in `data/processed/ingame_query_checks.csv`. Canonical
  queries are marked as inherited, with zero new relevance reviews, rather than
  presented as newly validated aliases.

Outputs:

- `data/processed/ingame_bluesky_posts.parquet`
- `data/processed/ingame_bluesky_minute.parquet`
- `data/processed/ingame_query_checks.csv`
- `data/raw/bluesky_ingame/`: 96 cache files, request log, collection summary, and
  `relevance_sample.csv` containing all 50 review labels and explanations.

No market/model files, shared configuration, requirements, README, or existing
Milestone I datasets were edited. This additional Markdown file was authorized
as an alternative to a Google Doc.

## Collection and timestamp methods

Games are the eight `selected == True` rows in `markets.csv`. Each game's fixed
window is `[scheduled tip - 2 hours, scheduled tip + 3 hours 30 minutes)`. There
are 330 minute rows per game and 2,640 rows overall. The minute table deliberately
includes pregame and potentially postgame minutes; the model owner must trim to
the actual game interval using ESPN, as specified in the plan.

Each team is searched separately in five one-hour intervals followed by one
30-minute interval. The collector imports the existing `_collect_window`, `_slim`,
and `posts_table` helpers without changing `bluesky.py`. `_collect_window` splits
queries reaching 100 posts, and its HTTP helper enforces at least 0.12 seconds
between requests. In this run all 96 top-level windows completed successfully;
the request log records 96 HTTP 200 responses, with no additional splitting needed.

The cache identity includes game, side, team, query, start, and end. Failed or
truncated entries are retried on subsequent runs. Raw post payloads and retrieval
times are retained. Successful HTTP retrieval and avoiding the result cap are
coverage checks, not proof of exhaustive search indexing or semantic relevance.

Timestamps in the Parquet exports are explicitly `datetime64[ns, UTC]`.
Following the agreed data contract, `sort_at = min(created_at, indexed_at)` and
minute binning uses `floor(sort_at, minute)`, not the enclosing request interval.
Posts outside the fixed game window are excluded. Post rows are deduplicated on
`(slug, side, uri)` across windows and queries; a post matching both sides remains
one row for each side. Missing post timestamps raise an error rather than being
silently assigned to a minute.

If any query required for a side fails or remains truncated, that side's counts
for the full queried interval become NaN. Successful empty intervals have zero
counts. `bsky_ok` is true only when both sides have valid search coverage.

## Four attention measures

1. **Raw attention:** `posts_home`, `posts_away`, the deduplicated counts in each
   minute. Total attention can be obtained by adding them; it is a sum of side
   matches, not necessarily a count of distinct posts across both teams.
2. **Abnormal attention:** `abn_side = log1p(posts_side) - baseline_side`, where
   `baseline_side` is the mean of `log1p(posts_side)` over all 120 pre-tip minutes.
   If any baseline minute is missing, the baseline and that side's abnormal series
   are NaN. **Use this feature only at/after tip-off**: using it to forecast during
   the two-hour pre-tip window would incorporate later pre-tip observations.
3. **Imbalance:** `log1p(posts_home) - log1p(posts_away)`. This measures relative
   posting attention; it does not measure positive versus negative sentiment.
4. **Injury attention:** `injury_home`, `injury_away`, counts of posts matching
   `injur|hurt|ankle|knee|locker room|ruled out|questionable|limp` case-insensitively.
   This is the specified substring rule, not a verified injury-news classifier;
   sarcasm, unrelated use, and old injury references can match.

## Data inventory for model integration

Counts are from the exported datasets. Post-tip columns cover scheduled tip
through the fixed window's end, **not an ESPN-verified tip-to-buzzer interval**.

| Game | Whole-window home posts | Whole-window away posts | Post-tip home posts | Post-tip away posts | Whole-window injury matches |
|---|---:|---:|---:|---:|---:|
| Hornets at Nets | 17 | 19 | 10 | 11 | 4 |
| Bulls at Bucks | 35 | 34 | 24 | 22 | 6 |
| Cavaliers at 76ers | 261 | 140 | 214 | 121 | 10 |
| Nuggets at Thunder | 11 | 317 | 8 | 269 | 9 |
| Rockets at Spurs | 25 | 22 | 18 | 17 | 5 |
| Grizzlies at Jazz | 15 | 56 | 10 | 47 | 5 |
| Knicks at Celtics | 289 | 439 | 241 | 323 | 10 |
| Raptors at Timberwolves | 136 | 170 | 109 | 142 | 43 |

The posts table has 1,986 deduplicated post-side rows, including 1,586 post-tip
rows. All 2,640 minute rows have `bsky_ok=True`; all contracted minute-feature
columns are populated. There are 92 whole-window injury-keyword matches.

## Provisional relevance audit: material for student review

Fifty post-side rows were sampled without replacement from the post-tip subset,
using random seed 473. This sample is weighted by observed posting volume, not
balanced across games, and can include post-buzzer posts until ESPN trimming is
available. Each sampled text was read by the AI assistant and annotated:

- `yes`: explicit matchup, score, lineup/injury reference, or identifiable game
  performance/reaction in the standalone text — 24 of 50 (48%).
- `unclear`: team-related or contextual material whose standalone text does not
  establish relevance to this particular game — 16 of 50 (32%).
- `no`: unrelated word use, general season/team discussion, or other topics —
  10 of 50 (20%).

These are provisional text-only labels. They do not verify linked pages, quoted
parents, images, factual claims, original reporting, or bot status. Ambiguous
posts were not silently counted as relevant or discarded from the denominator.
The 48% is the share explicitly supported by this strict text-only labeling,
not an estimate from independent human adjudication and not proof the other
52% are unrelated. Students should review the CSV, resolve contextual cases,
and rerun the audit after actual game-time trimming before using a final
game-relevance percentage in the report. The current data are not filtered using
these labels; they retain the agreed keyword-count definition.

## Timing methods and generated analysis artifacts

`timing.py` joins inputs by unique `(slug, minute)` keys and rejects unmatched
market minutes. Price differences require consecutive observed in-game prices;
they never bridge a missing minute, game boundary, or carried-forward price.

The event studies use offsets -10 to +10 minutes:

- **Scoring plays:** ESPN scoring timestamps define minute 0; home/away scoring
  side determines whether the plotted probability is `p_home` or `1 - p_home`,
  and which side's post counts are plotted.
- **Large price jumps:** minute changes of at least 0.05 in absolute probability
  define events; the benefiting side determines orientation.

Only windows complete for the probability and oriented side's post counts enter
the curves. Event counts and exclusions are saved. Events are averaged within
each game, then games are weighted equally. Both average oriented probability
and changes relative to minute -1 are saved in CSV; the figure shows average
oriented probability and posts. Overlapping scoring windows are retained, so
individual event windows are not independent evidence.

Cross-correlation is defined as
`corr(delta_logit(t), attention(t + lag))`, for lags -10 through +10.
**Positive lag means the market precedes attention; negative lag means attention
precedes the market.** Exact timestamp pairs are used, with both minutes inside
the game. Correlations are calculated within games and averaged equally across
games. Undefined correlations for constant series remain NaN. The requested
total-post measure and a directional imbalance sensitivity check are both saved.

Minute 0 includes the whole event-containing minute. These analyses cannot order
two reactions occurring within the same minute. Shared scoring shocks, other
news, repeated events, and the choice to select large market moves prevent a
causal interpretation. Generated curves and per-game CSVs are measurement
artifacts for the students to inspect and interpret independently; a visible
post-event rise is not a causal effect estimate or proof of individual post latency.

## Checklist for addressing the TA's six points

| Feedback | Design/method response to document |
|---|---|
| One social source is sufficient | Bluesky is the primary external source; no new GDELT work. |
| Justify horizon and examine games | In-game one-minute forecasts, five-minute robustness, ESPN game-state alignment. Minute data cannot establish millisecond efficiency. |
| Start with a few games | Run three named pilots before interpreting all eight games. The social exports support both. |
| Identify the main metric | Held-out-game RMSE of log-odds change; report per-game and aggregate values with clear weighting. |
| Identify the baseline | Both no-change B0 and market/game-state B1; enhanced model adds the social features to B1. |
| Explain incorporation into price | Predict log-odds increments, then apply the inverse-logit reconstruction above. |

Leave-one-game-out is the agreed evaluation design. When describing it, distinguish
generalization to a held-out game from a chronological, historically executable
forecast test. Statistical inference remains the model owner's responsibility;
eight games and overlapping five-minute targets require caution about effective
sample size and serial dependence.

## Reproduction

From a Python 3.11 environment containing the existing project requirements:

```bash
python -m pytest -q tests
python scripts/run_ingame_social.py
# After the market owner supplies both input files:
python scripts/run_timing.py
```

Collection reruns use the branch's raw caches and do not append to the shared
Milestone I request log. This implementation was checked in isolated Python
3.11.18: 25 tests passed, including the existing nine pilot tests and four market
tests. A cached full collection rebuild completed successfully. Timing plotting
was exercised on synthetic inputs in a temporary directory and then on the real
market/ESPN handoff. No synthetic plots were saved as research results.

`run_timing.py` writes `figures/fig_m2_timing_scoring.png`,
`fig_m2_timing_jumps.png`, `fig_m2_cross_correlation.png`, accompanying CSV tables,
and a JSON event-coverage summary. Those figures and tables have now been generated
from the real inputs. It also writes `fig_m2_bluesky_injury_timelines.png` and an
injury inventory CSV. The original minute and post Parquet files are unchanged.

## Injury-keyword audit handoff

The 92 keyword-matched post-side rows reduce to 64 distinct `(slug, uri)` pairs;
26 distinct posts fall inside the market file's ESPN-derived `in_game` minutes.
The audit CSV at `data/raw/bluesky_ingame/injury_review.csv` retains all matched
query sides. Matching both queries is not evidence that both teams had an injury.
The contractual `injury_home`/`injury_away` columns mean query-side matches, not
independently established attribution to an injured player's team.

The AI assistant read all 64 distinct texts and added provisional categories and
notes. Of the 26 in-game texts, the categories are: 7 literal-keyword false
positives, 10 repetitions of already-described availability information, 4 general
or hypothetical discussions, 1 generic report, 2 ambiguous reactions, and 2 live
injury/symptom candidates. These are not human-validated labels or verified events.

Examples requiring attention are a Cam Johnson ankle/return-status post at
2026-10-23 03:10:07 UTC (Nuggets–Thunder) and a post describing Walsh limping at
2026-10-24 00:50:28 UTC (Knicks–Celtics). The first attributes its information to
the broadcast; the second is a symptom observation, not a confirmed diagnosis.
Neither establishes that Bluesky first published the information or led the market.
Repeated Kawhi-availability posts during Raptors–Timberwolves concern a topic
already present in the pregame collection; some contain inconsistent knee-side
descriptions. Their count should not be equated with distinct new injury events.

The broad keyword feature was preserved for the partner's predefined models.
Any cleaned feature, source verification, or case-study selection should be declared
as additional exploratory analysis. In particular, weak baseline predictability
and fast basket reactions do not logically establish that all possible Bluesky
value must come from injuries.
