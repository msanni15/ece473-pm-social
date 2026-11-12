# Reproducing the final-project replication

## Dataset stages and version history

- Original eight games: the Milestone II paths under `data/processed/`.
- October extension: `data/processed/final_social/`, 24 games from October 28–30.
- November replication: `data/processed/final_replication/`, 34 games across nine
  available dates during November 1–10. All selected games were collected.
- Shared isolated extension caches: `data/raw/final_social/`. Compressed discovery
  metadata preserve the original API responses; individual query/trade/ESPN caches
  allow a rerun without redownloading successful requests.

The first forward design was committed at `e73d81b`, with implementation at
`7f947ad`, before extension scoring. The broader two-way replication design was
committed at `efcef6a`; implementation at `c0a87ed` preceded November scoring.
Design files are `final_social_design.json` and `final_replication_design.json`.
Collection manifests record their SHA-256 hashes. Evaluation rejects a mismatch.
These are internal specification freezes, not external preregistration.

## Commands

Use Python 3.11 with the repository requirements. The collector may make public
API requests for uncached data. Successful windows are cached. The commands do not
change the original Milestone II outputs.

```bash
# Review materials and exploratory original-sample activity analysis:
python scripts/prepare_social_validation.py
python scripts/run_social_activity.py

# First chronological extension, fixed eight-game training:
python scripts/collect_final_social.py
python scripts/evaluate_final_social.py
python scripts/plot_final_social.py
python scripts/run_reverse_attention.py
python scripts/prepare_injury_cases.py

# Broader replication, fixed 32-game earlier training:
python scripts/collect_final_social.py --design reports/final_replication_design.json --output data/processed/final_replication
python scripts/evaluate_final_social.py --test-dir data/processed/final_replication --design reports/final_replication_design.json --include-later-training
python scripts/run_reverse_attention.py --test-dir data/processed/final_replication --design reports/final_replication_design.json --include-later-training --figure-name fig_final_reverse_replication.png
python scripts/plot_final_social.py --test-dir data/processed/final_replication --figure-name fig_final_social_replication.png
python -m pytest -q tests
```

## Evaluation interpretation

Each target uses the same eligible test rows for its model comparisons. Primary
ridge models use alpha=1 and training-only scaling; OLS is a declared sensitivity.
The forward tasks compare signed log-odds changes and future log total USDC volume.
The reverse task compares log total query-side posting against a baseline with
posting history, recent scoring, score margin, and time remaining. Exact future
minute windows and exact final-play cutoffs prevent targets from borrowing from
another game or from the final post-buzzer partial minute.

All test predictions are saved, along with per-game errors and both pooled and
equal-game summaries. Whole-game and date-cluster bootstrap sensitivities resample
paired losses, using 10,000 draws and seed 473. Repeated teams and multiple tested
endpoints remain reasons for caution; no profitability or causal effect is tested.

The initial reverse task was introduced after the first forward results were
known, so it is exploratory on that sample. It was frozen before November test
scoring. The final-minute correction was also known before November scoring;
pre-correction artifacts from the first extension remain available separately.

## Source-checked injury examples

`injury_source_checks.csv` records two cases identified before the replication.
The team’s October 26 preview corroborates Johnson’s opener ankle injury.
[Team-published source](https://www.nba.com/nuggets/news/nuggets-host-warriors-for-third-game-of-2026-27).
It does not establish the exact injury onset or first publication. The available
Walsh post describes limping but independent injury/diagnosis corroboration was not
established. Search failure is not proof that an injury did not happen.

The Cam Johnson post precedes an ESPN-recorded Aaron Gordon three-pointer by
4.58 seconds. That scoring play is an immediate competing explanation for price
movement near the post. The case figure plots market prices and score margins
relative to the **post**, not a verified injury-release time, and masks prices
whose latest trade is more than 30 seconds old. Neither case demonstrates that
Bluesky first reported information or caused a market move.

## Validation and outstanding human work

The combined synthetic suite has 37 passing tests in Python 3.11.18, including
future-target alignment, no cross-game/gap borrowing, conservative timestamps,
exact game-boundary handling, the ESPN Clippers alias, and reverse-feature timing.
Real-data checks verify disjoint training/test games, strict chronological order,
finite uniquely keyed predictions, all selected games collected, and full query
coverage. Relevant figure PNGs are inspected visually; source CSVs are retained.

The 100-post review sample remains unlabelled. Students must complete the review,
check source context and disagreement, and write the course's unaided sections.
No final paper, slides, or course-portal submission is represented as completed.
