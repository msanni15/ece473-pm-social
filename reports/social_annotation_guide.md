# Social-information validation protocol

This prepares the final-project social component. It does not replace or relabel
the original Milestone II results. New analysis on the eight previously studied
games is development work; a later untouched chronological sample is needed for
fresh forecasting evidence.

## Review task

Run `python scripts/prepare_social_validation.py`. Review the resulting
`data/processed/social_validation_sample.csv` without opening price charts,
model errors, or subsequent game events while assigning text labels. The sample
contains 100 distinct game/post pairs selected approximately evenly across games,
subject to available posts. Sparse games are included rather than overwhelmed
by Knicks/Celtics activity. It is not a simple random sample of all posts; report
per-game relevance rather than interpreting the unweighted overall share as
population precision.

- `game_relevant`: `yes`, `no`, or `unclear`. A team mention alone does not establish
  relevance to the sampled game. Preserve uncertainty when context is missing.
- `information_type`: `play_reaction`, `availability_report`, `opinion`,
  `promotion`, `other`, or `unclear`. Availability reports may be old or repeated.
- `injured_team`: `home`, `away`, `neither`, or `unknown`. Determine the affected
  player/team from text or a documented source, not from the matching search side.
- `new_information`: `candidate_new`, `already_reported`, or `unknown`. A candidate
  label alone is not proof of first publication. Repetition of an absence reported
  before tip-off is not a new in-game injury event.
- `source_reference`: URL or broadcast/article reference used to resolve context.
- `reviewer` and `notes`: identify who reviewed the row and explain ambiguities.

Where possible, both students independently label an overlapping subset before
comparing decisions. Preserve their initial labels and adjudicate disagreements;
do not describe AI suggestions as independent human agreement. The review CSV is
initially blank on purpose. Labels should not be selected to improve forecast scores.

## Timestamp check

The agreed pilot bins on `min(created_at,indexed_at)`. The preparation script also
records timestamp discrepancies. A post created earlier than its indexing time
may enter an earlier pilot bin even if its availability to search by that minute
is not established. An indexed-time or index-confirmed-subset sensitivity check
would be conservative; neither timestamp alone proves when readers first learned
the information. Retain and disclose negative timestamp differences rather than
silently replacing them.

Rebinning indexed times is not automatically a complete indexed-time collection:
posts outside the original search windows may move into them and vice versa.
Design coverage accordingly before treating rebinned empty minutes as true zeros.
