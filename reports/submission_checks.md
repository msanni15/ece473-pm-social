# Items for the students to resolve before submission

This checklist identifies remaining work; it does not replace unaided findings
or conclusion writing required by the course.

## Required author decisions and review

- Replace `[names]` with the actual authors and add a factual contribution statement.
- Review the provisional relevance and injury annotations. The original 50-post
  sample is post-tip, not strictly tip-to-final-buzzer. Do not describe AI labels
  as independent human validation or treat unclear cases as confirmed negatives.
- Supply your own interpretation of the timing figures in Section 6.
- Reconcile the findings/interpretation with the additional evaluation: failure
  to detect an improvement is not proof of no information or universal efficiency.
  The one-minute imbalance nominal significance does not survive the added
  ten-comparison Holm adjustment using game-level tests.
- The specific claim that effects below a fraction of a percent cannot be detected
  needs a power analysis; small sample size alone does not establish that cutoff.
- Keep mean per-game RMSE distinct from pooled RMSE and its percentage change.
  Both are provided, but they summarize different quantities.
- Claims about ESPN timestamp lag, first publication of injury news, or a causal
  effect of scoring on posting need evidence beyond visual ordering of curves.
- State that the primary design is held-out-game generalization, not a strictly
  chronological forecast backtest. New later games would provide a fresh holdout.

## Technical status

- Collection and real timing artifacts are merged through PR #1.
- Standard enhanced models and report are merged through PR #3.
- Supplemental enhanced-model validation and report integration are on
  `partner/enhanced-models`, PR #4. Merge that PR after review so report links to
  its new figure and methods resolve on main.
- Python 3.11.18 combined suite: 29 passing tests. No missing report image/link
  targets in the integrated branch. No submission was made to the course portal.
