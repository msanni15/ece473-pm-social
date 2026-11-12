# Enhanced-model validation and robustness handoff

AI-assisted methods/validation notes. These are not the students’ unaided final-paper findings or conclusion.

## What this branch adds

The standard enhanced models had already been run on Alicia’s branch at commit `9e0d1e0`. This branch independently reproduces those runs and adds saved held-out predictions, explicit macro versus pooled metrics, probability reconstruction, whole-game uncertainty checks, multiple-comparison adjustment, and an observed-price-history robustness sample. It leaves her model outputs and report untouched.

## Reproduction

```bash
python scripts/run_enhanced_evaluation.py
python -m pytest -q tests
```

Python 3.11.18, fixed bootstrap seed 473, 10,000 draws. All 29 tests pass. The 56 matching pilot/all-game model-summary rows reproduce Alicia’s macro RMSE values within 7e-16. Primary sample: 1,163 rows; observed-history sensitivity: 1,152 rows; eight games in each all-game sample.

## Design

- Same leave-one-game-out specifications, OLS and ridge alpha=1, and one/five-minute log-odds-change targets as the original runner. Every model and horizon uses the same eligible rows within a sample. No tuning on held-out games.
- Saves every held-out prediction with game, minute, target, estimator, feature set, and horizon. Forecast probabilities are reconstructed with inverse logit; probability errors are measured against the clipped endpoint implied by the log-odds target.
- Macro RMSE is the unweighted mean of game RMSEs. Pooled RMSE is the square root of total squared error divided by total test rows. Their relative changes need not match.
- Resamples complete games in paired bootstrap comparisons. Unlike resampling minutes, this preserves within-game serial dependence. Intervals are percentile sensitivity intervals conditional on the fitted held-out predictions; models are not retrained per bootstrap draw.
- Two-sided sign-flip sensitivity test uses equal-game mean squared-error differences and all 2^G sign patterns. It assumes symmetric, independent game differences; shared training folds violate strict independence, so it is exploratory rather than exact observational inference.
- Holm correction covers five social-feature sets by two horizons (ten tests), separately within each sample and estimator. It is not a global correction across every sensitivity analysis. The B1-versus-B0 comparison is outside this social family.
- Observed-history robustness requires every price from t-5 through t+5 to be observed and on the exact minute grid. Lagged features are built before filtering, so dropped rows never compress the time series. Models are refitted on that sample.

## Numerical validation table: all games, OLS

Negative change means lower pooled RMSE than B1. Percent changes are relative percentages, not probability percentage points. Intervals below are game-bootstrap intervals; the adjusted p-value is from the distinct sign-flip calculation.

| Horizon | Feature set | RMSE change (%) | Game-bootstrap 95% interval (%) | Games improved | Holm-adjusted game p |
|---|---|---:|---|---:|---:|
| 1 min | counts | +0.053 | [-0.053, +0.235] | 4/8 | 1.000 |
| 1 min | abnormal | +0.032 | [-0.054, +0.202] | 5/8 | 1.000 |
| 1 min | imbalance | +0.220 | [+0.053, +0.575] | 1/8 | 0.234 |
| 1 min | injury | +0.023 | [-0.009, +0.054] | 2/8 | 1.000 |
| 1 min | all | +0.201 | [-0.103, +0.627] | 4/8 | 1.000 |
| 5 min | counts | -0.443 | [-1.034, +0.188] | 5/8 | 1.000 |
| 5 min | abnormal | -0.061 | [-0.296, +0.250] | 4/8 | 1.000 |
| 5 min | imbalance | -0.090 | [-0.423, +0.144] | 4/8 | 1.000 |
| 5 min | injury | +0.072 | [-0.002, +0.197] | 2/8 | 1.000 |
| 5 min | all | +1.650 | [-1.441, +5.448] | 4/8 | 1.000 |

## Items for the report authors to check

- The original report’s all-game mean RMSE of about 0.258 and pooled RMSE of about 0.267 describe different aggregations. Label them consistently.
- Five-minute count features improve the pooled point estimate by about 0.443%; the game-bootstrap interval spans zero. In the observed-history sample, the corresponding point estimate is about 0.456% improvement.
- One-minute imbalance has an unadjusted game sign-flip p of about 0.023, but its ten-comparison Holm-adjusted p is about 0.234. Avoid presenting nominal significance from one of many tested features as definitive evidence.
- Existing pooled DM calculations use only h-1 autocovariance lags (none at one minute) and concatenate games. The added game-level checks are a sensitivity analysis for dependence, not a proof that either p-value calculation is exact.
- Lack of detected improvement does not establish zero predictive information, universal market efficiency, or a known minimum detectable effect. Eight games, noisy social counts, shared game events, and LOGO training dependence constrain interpretation.
- These are additional analyses after seeing pilot results, not a preregistered confirmatory test. New later games would be needed for an untouched prospective test.

## Files

- `data/processed/enhanced_predictions.parquet`: auditable held-out forecasts.
- `enhanced_folds.csv`, `enhanced_summary.csv`, `enhanced_comparisons.csv`, `enhanced_checks.json` under `data/processed/`.
- `figures/fig_m2_enhanced_uncertainty.png`: OLS feature comparisons with whole-game intervals.
- `src/pmsocial/enhanced_evaluation.py`, `scripts/run_enhanced_evaluation.py`, `tests/test_enhanced_evaluation.py`.
