# Automatic Paper Ingestion Implementation Plan

**Goal:** Let a user select a saved paper and have Code Navi automatically resolve a public academic copy or accept a local PDF, then send bounded paper text to DeepSeek for targeted advice.

**Architecture:** Keep the existing evidence-bound JSON contracts and DeepSeek text adapter. Add deterministic arXiv title/author matching through the existing academic source allow-list, plus a local PDF-bytes endpoint that parses text server-side. The model receives paper metadata, bounded text, research profile, and reproduction intent; it never browses arbitrary URLs or executes paper code.

**Verification:** Add offline tests for resolver matching, local PDF parsing, upload API wiring, and frontend no-URL flow; run targeted pytest, Ruff, frontend lint/typecheck/build, and `git diff --check`.

---

- [x] Add failing tests for automatic arXiv resolution and local PDF bytes.
- [x] Implement resolver and bounded byte parsing with explicit provenance.
- [x] Add upload API and frontend file action; make paper analysis auto-resolve when no URL is supplied.
- [x] Strengthen targeted prompts so advice is tied to the selected paper and reproduction goal while preserving schema validation.
- [x] Run verification and update the handoff record (`118 passed, 1 warning` in the broader research regression set).
