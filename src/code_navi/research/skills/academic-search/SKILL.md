---
name: academic-search
description: Prepare and execute source-restricted academic metadata searches from a confirmed research profile. Use after research-clarification hands off a topic or candidate question, when the user wants traceable papers from explicitly allowed scholarly databases rather than an unrestricted web search.
---

# Academic Search

Turn a confirmed research profile into an auditable search plan and an evidence bundle. Keep query planning offline. Access the network only after explicit user confirmation.

## Workflow

1. Read structured profile fields instead of using the raw chat sentence as the query.
2. Build one concise primary query and up to three alternatives from the topic, research question, context, method, and data requirements.
3. Show the query, evidence scope, and allow-listed sources before execution.
4. Require explicit confirmation of both query and sources.
5. Dispatch only the registered `academic_search` Tool with `READ + NETWORK` permission.
6. Return every source status, access time, result URL, and failure reason. Preserve successful sources when another source fails.
7. Persist each EvidenceBundle with its conversation. Reuse a non-expired bundle only when the normalized query and ordered source selection match exactly, and label the response as a cache hit.

## Evidence boundary

- Treat titles, authors, years, identifiers, URLs, and source-returned abstracts as `fact` metadata.
- Treat keyword relevance as `inference`, never as proof that a paper supports a claim.
- Mark methods, datasets, findings, and conclusions as `to_verify` until full text is inspected.
- State `metadata_and_abstract_only`; do not imply that the full paper was downloaded or read.
- Never fabricate papers, citations, abstracts, identifiers, source coverage, or successful searches.

## Source and permission boundary

- Search only sources present in the host allow-list and selected by the user.
- Do not fall back to a browser or unrestricted web search.
- Do not search while restoring a conversation, clarifying a requirement, or preparing a plan.
- Do not expose provider keys, proxy credentials, or raw upstream error bodies.
- Reject unsupported sources before any network request.

## Failure behavior

- Return `timeout`, `network_error`, `disabled`, `no_results`, or `unavailable` per source.
- Keep partial results when at least one source succeeds.
- Show every selected source status and duration even when the combined result contains papers.
- Suggest changing the query or source selection only after reporting what actually ran.
- Allow retries only within the host's bounded per-source policy; never retry indefinitely.
