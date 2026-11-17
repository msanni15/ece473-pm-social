# Presentation and paper package

Prepared November 17, 2026. These files use the final 32-training/34-test-game
replication, not the older eight-game milestone results.

- [PowerPoint presentation](presentation.pptx): 12 editable slides, with presenter
  notes and evidence references. Add team names and review your closing statement.
- [Presentation PDF](presentation.pdf): matching content, for sharing or presenting.
- [Editable paper draft](final_paper_draft.docx) and [PDF draft](final_paper_draft.pdf):
  methods, related-research notes, figures, and numerical appendices assembled.
  The course's unaided introduction, findings, and conclusion remain explicit
  author placeholders. These drafts are not submission-ready final manuscripts.
- [Results and review workbook](results_workbook.xlsx): all final comparisons,
  per-game errors, selected-game registry, data checks, blank human review sheet,
  and separate provisional AI suggestions. Do not confuse the two label sheets.
- [Presenter guide](presenter_guide.md): notes and questions to rehearse.
- [Evidence audit](evidence_audit.json): comparison numbers recomputed directly
  from saved held-out predictions, with hashes for the underlying files.

## Author actions before use

1. Add names and an accurate contribution/AI-use statement. Distinguish work you
   checked and interpreted from code generated with AI assistance.
2. Review the slide content and notes. If the assigned slot is short, omit the
   injury case slide and shorten the limitations/methods discussion.
3. Write the reserved paper sections yourself. Verify bibliography records and
   source links before final submission; the manuscript uses the 2017 author
   version of the soccer/Twitter paper rather than guessing publication metadata.
4. Review the post labels, or retain them explicitly as provisional AI text-only
   judgments. No independent human relevance estimate is currently established.
5. Confirm course formatting, presentation duration, and submission instructions;
   those details were not supplied. No course-portal submission has been made.

## Rebuild

In an environment with the existing research requirements and optional document
packages from `requirements-deliverables.txt`:

```bash
python scripts/prepare_review_suggestions.py
python scripts/build_submission_package.py
python scripts/audit_submission_evidence.py
```

The PowerPoint and PDF are generated from the same content specification.
Direct edits to the PowerPoint or Word files will not be retained by a rebuild;
edit their source specification or retain a separate final author-edited copy.
If you complete labels in Excel, retain the edited workbook and export the
`Human_review` sheet as CSV to update the source review file before rebuilding.
Otherwise rebuilding the workbook uses the still-unlabelled source CSV.

The provided paper PDF is a draft, not a final journal-format submission. It
intentionally contains placeholders and outstanding-validation notices.
