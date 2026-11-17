# Presenter guide

Suggested rehearsal: about nine minutes plus transitions; adapt to the actual assigned duration. Do not assume the course slot is nine minutes.

The deck is AI-assisted. Review the evidence and formulate your own opening and closing explanations. The final-paper reserved sections remain for your unaided writing.

## Slide 1: Social attention and NBA prediction markets

Suggested time: 30 seconds.

Introduce the project in your own words. We study short-horizon activity, not simply which team wins. The original pilot and the later final test are distinct stages.

Evidence: Source: reports/final_project_status.md

## Slide 2: Two questions, with separate forecasting baselines

Suggested time: 40 seconds.

The reverse task must control for posting persistence. A correlation or post-event rise alone cannot answer either incremental-prediction question.

Evidence: Designs: reports/final_social_design.json; final_replication_design.json

## Slide 3: Separate development, extension and replication

Suggested time: 40 seconds.

Do not call all 66 games held out. Only the final 34 form the last replication test. Earlier stages informed the final design; no test-based hyperparameter search was used.

Evidence: Registries: data/processed/final_social/ and final_replication/selected_games.csv

## Slide 4: One minute: known features first, future target second

Suggested time: 50 seconds.

The first extension used an inclusive final-minute flag. That was corrected transparently, with old outputs retained. The correction preceded the November replication. Creation/indexing timestamps have a separate sensitivity check.

Evidence: scripts/evaluate_final_social.py; src/pmsocial/social_activity.py

## Slide 5: Attention is measured; news content needs validation

Suggested time: 50 seconds.

Search coverage succeeded for all collected minutes but is not proof of exhaustive indexing or relevance. AI review suggestions are separate from the blank human-label file. Injury keywords include figurative uses and repeated availability reports.

Evidence: reports/social_annotation_guide.md; data/processed/social_validation_sample.csv

## Slide 6: Score the comparison, not just one fitted model

Suggested time: 50 seconds.

RMSE is not percentage accuracy. Relative RMSE changes are percentages of error, not probability percentage points. Multiple endpoints are reported rather than selecting a favorable specification.

Evidence: data/processed/final_replication/*comparisons.csv; *folds.csv

## Slide 7: The final baseline comparisons have measured gains

Suggested time: 45 seconds.

Price pooled RMSE: 0.239637 to 0.233446. Volume pooled RMSE: 1.610940 to 1.372064. The old eight-game no-change comparison must not be generalized to this larger final test.

Evidence: 34-game test; ridge; heldout_comparisons.csv; model=market

## Slide 8: Increment from Bluesky: small point estimates, uncertainty

Suggested time: 70 seconds.

Left: next-minute signed price; right: next-five-minute log volume. Negative is lower error versus the market baseline. The complete social bundle gives −0.073% for price and +0.348% for volume; both game intervals span zero. Counts-only estimates and other horizons remain visible in the workbook. Do not state that no information can ever exist.

Evidence: data/processed/final_replication/heldout_comparisons.csv; 32 train / 34 test

## Slide 9: Reverse direction: market features predicting posting

Suggested time: 55 seconds.

Reference is posting history plus game state, not a constant forecast. Adding price/trading gives about 0.405% lower five-minute error, but both game/date intervals include zero. Post-event timing is descriptive and does not show that prices caused fans to post.

Evidence: data/processed/final_replication/reverse_attention_comparisons.csv

## Slide 10: Injury candidates need event-time and source checks

Suggested time: 45 seconds.

Red marks posting time, not injury onset. Cam Johnson’s ankle injury has team follow-up corroboration, but first publication is unresolved. A scoring play is logged 4.58 seconds after the post. The Walsh limping post lacks independent diagnosis corroboration. Neither demonstrates a news trading edge.

Evidence: data/processed/final_social/injury_source_checks.csv; source/context checks remain provisional

## Slide 11: Robustness and limitations are part of the evidence

Suggested time: 40 seconds.

Use the workbook to inspect sensitivity rather than claim a universal result. The final sample spans nine dates. Results can reflect last-trade spread effects and cannot be converted into profit claims.

Evidence: reports/final_replication_methods.md; results_workbook.xlsx

## Slide 12: Finish with author-reviewed interpretation

Suggested time: 25 seconds.

This is a draft presentation package. Formulate your own closing statement. The final-paper introduction, findings and conclusion remain for unaided author writing. Do not say the paper or human validation is completed.

Evidence: reports/final_paper_scaffold.md; deliverables/presenter_guide.md

## Questions to rehearse

- **Are you predicting the winner?** The main price task forecasts the next-minute log-odds increment. It is distinct from evaluating winner probabilities at settlement.
- **What is the strongest benchmark?** No change for signed price; trailing-window persistence for volume/posting, then feature-appropriate market or posting-history/game-state regressions.
- **Does 2.58% mean 2.58 probability points?** No. It is the relative reduction in pooled forecast RMSE compared with the named baseline.
- **What happens when Bluesky is added?** On the final ridge test, the full bundle changes next-minute price RMSE by −0.073%; the game interval crosses zero. For five-minute log volume it changes error by +0.348%, also with an interval crossing zero.
- **Does that prove social media has no information?** No. These feature definitions and this dataset do not establish a reliable incremental forecasting gain. Content measures, other samples and other horizons can differ.
- **Does the reverse result establish causation?** No. Market/price features give small uncertain increments after controls; shared events can explain associations.
- **How many games train and test?** The final replication uses 32 earlier training games and 34 later test games. The total inventory is 66; all 66 are not held out.
- **Was the human relevance review completed?** No. There are 100 explicit AI text-review suggestions in a separate sheet; they are not independent human validation.
- **Are injury cases verified breaking news?** No. One injury has follow-up corroboration but not an established release time; the other symptom post is uncorroborated. Nearby scoring is a competing explanation.
- **Is the paper ready to submit?** No. Authors must finish the reserved sections, names/contributions, content review or provisional-label disclosure, and formatting checks.

## Optional contribution statement structure

List the responsibilities each student actually owned, including decisions, data validation, model evaluation, interpretation and presentation. Disclose AI-generated code/materials. Do not claim independently implemented or manually validated work when that is not what occurred.
