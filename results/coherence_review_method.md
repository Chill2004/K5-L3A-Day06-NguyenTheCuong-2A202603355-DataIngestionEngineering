# Coherence review

- Reviewer: Codex AI-assisted content review; not independent human labels.
- Sample selection follows the pre-test protocol: first non-whitespace character after repeated-header removal on physical pages 39-48, one anchor per page.
- Selected the covering chunk with the lowest start offset (chunk ID breaks ties). Source offsets and chunk IDs are retained in coherence_labels.csv.
- Read the full 20 distinct A/B chunks and their source context in coherence_audit_reading.txt. C uses the same B chunks and therefore the same coherence labels; no independent C sample was drawn.
- Rubric: 0 = insufficient subject/context to understand; 1 = partially understandable but incomplete/context missing; 2 = self-contained and intact idea.
- A complete statement plus a cut-off next statement receives 1. A heading without explanatory content receives 1 when the topic remains intelligible. A fragment alone without interpretable subject would receive 0. Do not assign 0 solely because a boundary is cut if meaningful statements remain.
- Only B/C page 42 in this sample retains a complete, understandable set of research/publication-support statements without an unfinished trailing provision; score 2. Other sampled chunks score 1 for the individually documented omissions.
- A mean: 1.0/2 (10 samples); B and C mean: 1.1/2 (10 samples each).
- Limitation: fixed page-start sampling overrepresents headings and page continuations and covers only the first ten selected pages. These scores must not be generalized to the entire corpus. No anchors were changed after seeing the scores.
- No chunking, retrieval settings, gold or test metrics were changed during review.
