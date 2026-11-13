# Grounding review method

- Reviewer: Codex, AI-assisted content review; these are not independent human labels.
- Read all 15 test top-3 sets from test_audit_reading.txt; labels were not inferred from retrieval scores.
- Cross-checked the relevant content on physical PDF pages 45, 53, 67 and 68 against the university-hosted PDF: https://ou.edu.vn/wp-content/uploads/2024/09/So-Tay-SV-2024.pdf.
- Local PDF rendering was unavailable because the installed MiKTeX Poppler wrapper could not initialize. Source checking used the official PDF text, local traces and available user-provided page images; no claim of complete local visual inspection is made.
- Scale: 0 = no answer evidence; 1 = relevant but missing necessary information; 2 = sufficient evidence and source traceability across top-3.
- A/q18: 0 because the retrieved teaching-administration passages do not give the required course syllabus.
- B and C/q19: 1 because the applicability sentence is truncated before the intake year. The handbook title year does not establish intake applicability.
- The rest receive 2 for sufficient answer evidence. A/q19 uses the regulation context and applicability clause across ranks 1 and 2.
- Metadata correctness audit is separate and remains unfinished.
- Retrieval metrics, gold labels and configurations were not changed.
