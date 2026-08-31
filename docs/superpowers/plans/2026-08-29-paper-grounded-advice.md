# Paper-grounded research advice

## Goal

After the user explicitly chooses a saved paper and provides a public PDF URL (or the saved arXiv identifier is usable), read a bounded amount of paper text locally before asking DeepSeek to generate advice. Keep the existing evidence boundary: no private-file reads, code execution, or silent metadata fallback.

## Tasks

- [x] Add failing tests for bounded PDF extraction, source metadata, and explicit missing-PDF errors.
- [x] Implement a small local PDF reader using the existing `pypdf` dependency and strict size/timeout limits.
- [x] Extend paper analysis and reproduction-pipeline contracts to carry paper-reading provenance and include extracted text in the LLM context.
- [x] Add an explicit PDF URL field and user action in the research UI; render generated advice as compact readable rows with expandable detail.
- [x] Run targeted backend/frontend checks and update the external handoff record with verified results and remaining limits.
