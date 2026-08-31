# Research Upstream Quality Design

## Goal

Let a complete first research request reach the existing, user-confirmed academic-search handoff without contradictory readiness state, then rank and deduplicate local academic metadata so original papers are easier to select and save as traceable evidence.

## Scope

This slice changes only the Research clarification and academic-search upstream path. It does not change the research page layout, five-dimensional evaluation, reproduction outcome wording, Learning, Practice, deployment, or remote resources.

## A1: One shared readiness contract

`assess_readiness` will remain the single source of truth for profile progress. Its result will expose one explicit eligibility condition that is used consistently by:

- the conversation response's `ready_for_plan` and stage;
- rule/model decision transitions to `prepare_search`;
- offline research-plan generation; and
- `ResearchConversationSearchService.plan` before a user explicitly starts a search.

The rule fallback will recognize a complete first request's topic, research question, method, dataset, metric, constraints, and timeline without asking again for the topic or question. It still treats model output as phrasing only and retains the rules-only fallback.

## A2: Deterministic original-paper-first search results

After only user-confirmed searches of the existing allow-listed metadata/abstract sources, the academic tool will normalize and merge records. It will:

1. deduplicate by normalized DOI, then normalized title, then arXiv identifier/formal-version relation;
2. use deterministic source-independent metadata signals for title, author, year, and query-keyword relevance;
3. classify candidates as original paper, review, or downstream application only as a metadata/abstract-derived inference; and
4. order original-paper candidates ahead of otherwise comparable reviews or downstream applications.

Classification and ranking never download full text, execute code, or change metadata/abstract limits. The returned evidence retains factual metadata, inferred relevance/classification, and `to_verify` statements for unobserved details.

## A3: Upstream EvidenceBundle identity contract

Each explicitly saved bundle keeps its stable `bundle_id` and `conversation_id`; each retained paper gets a deterministic, bundle-scoped paper identifier. Returned and restored bundles carry the same identifiers along with source, title, authors, year, DOI, arXiv identifier, URL, information scope, and epistemic-boundary fields. This is the only new contract needed by downstream consumers; no B-owned evaluation or UI behavior changes.

## Tests and acceptance evidence

Tests will be local and deterministic. They will add five differently phrased complete research requests, verify all reach the shared second-stage gate in one message, and use fixed GCN/Cora records to verify Kipf and Welling's original GCN paper is in the top three while arXiv/formal duplicates occupy one candidate slot. API/service tests will verify stable bundle and paper identifiers plus preserved `fact`, `inference`, `to_verify`, and `source_scope` boundaries.
