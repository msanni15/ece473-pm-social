# Final-project status — November 12, 2026

## Scope now implemented

This project now studies both predictive directions: whether Bluesky attention
adds information about market prices/trading, and whether market activity adds
information about subsequent Bluesky attention. It includes **66 NBA games**,
with an initial eight-game pilot, 24-game chronological extension, and 34-game
November replication. The full fixed windows contain 21,780 game-minute rows,
9,477 inclusively flagged game-time minutes, 9,971 post-side rows (8,491 distinct
game/post pairs), and 7,692 ESPN scoring plays. Model eligibility is stricter than
these inventory counts because of exact final-play boundaries, lags, and targets.

The additional work is on PR #5 until merged. Original Milestone II outputs and
the report remain intact. A positive social-media forecasting result is not a
requirement for a defensible paper; the empirical claims must match the tests.

## Completed technical work

- Public-source collection, caching, and identity checks for all 66 games.
- A design committed before scoring each later test stage.
- Initial forward tests trained on eight games and evaluated on 24 later games.
- A broader replication trained on 32 earlier games and evaluated on 34 later
  games selected as up to four per available day, November 1–10. This spans nine
  dates; the available candidate metadata had no November 3 games and only two
  on November 5. Selection did not depend on forecasting performance or posting.
- Price, trading-volume, and reverse-attention experiments, with persistence and
  feature-appropriate baselines; training-only scaling and fixed ridge/OLS models.
- All predictions, per-game errors, pooled and equal-game metrics, and game/date
  bootstrap sensitivity intervals saved for review.
- Timestamp-confirmed forward sensitivity, explicit exact-final-play filtering,
  and preserved pre-correction results from the first extension.
- Reverse-direction social-history/game-state baseline and separate price-only
  and broader trading-feature increments.
- Injury-source/context checks and figures for two preidentified candidate posts.
- A 100-post outcome-blind review file and annotation protocol, with blank labels
  rather than a fabricated human-validation result.
- Thirty-seven synthetic tests pass in Python 3.11.18.

## Evidence artifacts for the authors

| Question | Dataset/model output | Figure |
|---|---|---|
| Do social features improve prices or volume? | `data/processed/final_replication/heldout_comparisons.csv` | `figures/fig_final_social_replication.png` |
| Do market features improve posting forecasts? | `data/processed/final_replication/reverse_attention_comparisons.csv` | `figures/fig_final_reverse_replication.png` |
| What happened in the earlier extension? | `data/processed/final_social/heldout_comparisons.csv` and `reverse_attention_comparisons.csv` | `fig_final_social_holdout.png`, `fig_final_reverse_attention.png` |
| Are injury matches genuine new information? | `data/processed/final_social/injury_source_checks.csv` and `injury_case_contexts.csv` | `fig_final_injury_case_contexts.png` |
| How will relevance/content be validated? | `data/processed/social_validation_sample.csv` | `reports/social_annotation_guide.md` |

### Numerical checks: November replication, ridge

These are evidence tables, not final-paper findings prose. Negative RMSE changes
mean improvement. The interval column resamples whole games; date-cluster results
are saved separately and should also be inspected. Repeated-team dependence and
multiple endpoints remain limitations.

| Target | Comparison | Pooled RMSE change (%) | Game-bootstrap interval (%) | Games improved |
|---|---|---:|---|---:|
| Next-minute signed price | Market/game state vs no change | −2.584 | [−4.086, −0.962] | 25/34 |
| Next-minute signed price | Add all original social features | −0.073 | [−0.349, +0.189] | 19/34 |
| Next-minute signed price | Add counts only | −0.101 | [−0.232, +0.022] | 21/34 |
| Next-five-minute log volume | Market/game state vs persistence | −14.828 | [−17.247, −12.437] | 34/34 |
| Next-five-minute log volume | Add all original social features | +0.348 | [−0.326, +0.977] | 21/34 |
| Next-five-minute log volume | Add counts only | +0.005 | [−0.215, +0.196] | 15/34 |
| Next-five-minute log posting | Posting history/game state vs persistence | −16.566 | [−18.935, −13.762] | 33/34 |
| Next-five-minute log posting | Add price movements | −0.188 | [−0.572, +0.215] | 20/34 |
| Next-five-minute log posting | Add price and trading features | −0.405 | [−1.176, +0.495] | 21/34 |

The eight-game pilot's baseline comparison should not be generalized as "nothing
beats no change" across the final dataset. Nor does a price-error improvement
establish executable trading profit: last-trade prices contain spread effects,
and no historical order-book/cost backtest has been implemented. Authors should
write their own interpretation of the full evidence rather than reuse the
pilot's conclusions unchanged.

## What remains for a complete final submission

1. **Validate the social content.** Students label the prepared sample, document
   disagreements and context checks, and distinguish relevance from novelty and
   team mentions from injured-team attribution. The old AI annotations are still
   provisional; the new sample has not been human reviewed.
2. **Finish source verification.** Team-published follow-up supports the existence
   of Cam Johnson's ankle injury, but not its exact onset or first public report.
   The Walsh symptom post remains uncorroborated. These cannot be advertised as
   two verified breaking-news events or evidence of social-media leadership.
3. **Write the paper.** `final_paper_scaffold.md` supplies methods and artifact
   structure. Students must write the course's unaided introduction, findings,
   and conclusion, add names/contributions, check citations, and decide which
   robustness outputs belong in the main text versus an appendix.
4. **Review limitations and claims.** Retrospective market snapshots do not prove
   what traders saw at each second; search indexing is incomplete and timestamps
   are imperfect; calendar days and teams recur; some inference is exploratory.
   No causal or profitability result should be claimed.
5. **Present and submit.** Slides, the final manuscript/PDF, and course-portal
   submission are not yet completed. The final paper is due December 15.

Additional feature development after these test outcomes are seen is exploratory
unless tested on a genuinely unexamined later sample. The existing results should
remain visible rather than being replaced by whichever new model looks best.
