# Research downstream quality design

## Goal

Complete the existing research flow after a user has saved an EvidenceBundle:

1. Saved papers become selectable without a full page refresh.
2. A user can generate a Pipeline and explicitly link an experiment record to one of its tasks.
3. The evaluation presents evidence completeness, not experimental success.
4. The existing research view presents one five-step primary path while retaining supporting tools.

## Boundaries

- Consume A's persisted `academic-evidence.v1` and `reproduction-pipeline.v1` contracts without changing upstream extraction, search, classification, ranking, or deduplication rules.
- Preserve `fact`, `inference`, `to_verify`, and `source_scope` unchanged.
- `evidence_linked` means only that a user-submitted record names a Pipeline task.
- No automatic retrieval, full-text access, code execution, or claims of reproduction success.

## Design

- `ResearchConversation` owns a local downstream refresh version. Successful evidence saving, Pipeline creation, and experiment-record saving advance it; existing child panels refetch their persisted data when it changes.
- Paper selection uses A's stable `paper_id` together with `bundle_id`, falling back only for historical records that predate the identifier.
- The experiment panel reads the latest persisted Pipeline through the existing list API and exposes its task IDs as explicit user choices for `related_plan_item`.
- Evaluation treats a Pipeline whose relevant evidence is entirely `to_verify` as unverified planning: score zero, `needs_revision`, and explicit verification tasks. It never reports a checklist-complete plan from unverified entries.
- The workflow navigation describes five primary stages. Existing panels are shown through the existing collapsible section primitive: the current stage is open, completed stages summarize, and unavailable stages show only their name. Writing, citation, submission, and mind-map tools remain supplementary.

## Regression cases

- A saved evidence bundle refreshes the Pipeline selector and uses its stable paper identifier.
- An experiment record can target a listed Pipeline task and the regenerated Pipeline shows only an evidence link.
- No experiment record is not evaluable; partial records are partial/needs revision; records covering all categories are still evidence completeness rather than success.
- An all-`to_verify` Pipeline is not `checklist_complete` and cannot earn a full score.
