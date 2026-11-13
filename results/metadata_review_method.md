# Metadata source review

- Reviewer: Codex AI-assisted source-content review, not independent human labels.
- Scope: all 45 test results (15 per strategy), including repeated retrieval records.
- Checked document ID, source URL, physical PDF page, section and local source offsets/text.
- Source: https://ou.edu.vn/wp-content/uploads/2024/09/So-Tay-SV-2024.pdf (167-page official hosted PDF).
- Cross-checked page-aware PDF text for physical pages 44, 45, 50, 52, 53, 58, 67, 68, 69 and 76. Web PDF page indices are zero-based; audit page numbers are one-based.
- Section scopes: student affairs on 44/45; training regulations on 50/52/53/58/67; non-specialist language regulation on 69/76 and the portion of page 68 after its regulation heading.
- Page 68 has two sections; the retrieved language chunks belong after the verified boundary, so the page is not assigned wholesale to one section.
- Review used page-aware text, not a complete visual rendering inspection. Local renderer initialization was unavailable, as documented in grounding_review_method.md.
- All 45 source spans passed exact comparison against local sections.jsonl in metadata_integrity_check.csv.
- Result: A 15/15, B 15/15, C 15/15 metadata complete and correct for this sample.
- Truncated or irrelevant chunks can still have correct source metadata; coherence, grounding and retrieval are evaluated separately.
- Test filter compliance is recorded in test_filter_compliance.csv. A/B do not apply filters; observed compliance does not demonstrate filter enforcement or benefit.
- Usefulness: source/page enable citation lookup and section narrows retrieval. Limitation: section labels are coarse and depend on correctly maintained document boundaries; they cannot repair missing evidence within a chunk.
