# Reproduction Pipeline A Design

**Scope:** Add the student-controlled paper-reproduction Pipeline. This document deliberately excludes project evaluation, scoring, evaluation tasks, citation formatting, paper full-text processing, and code execution.

## Chosen approach

Create a new, application-owned `reproduction_*` vertical slice. The slice receives a research conversation plus an explicitly selected paper from an already persisted `ConversationEvidenceBundle`. It persists a rules-only `reproduction-pipeline.v1` document, restores the latest saved version for the same selected paper, and exposes it through FastAPI and the existing `/research` page.

This keeps the Pipeline contract separate from `ExperimentEvidenceBundle` and lets the later evaluation module consume a single stable, read-only document. Reusing the existing experiment evidence record avoids a second task-status store: each Pipeline task has a stable `task_id`, and experiment evidence items use that ID through the existing `related_plan_item` field.

## Contract

`ReproductionPipeline` contains:

- `pipeline_id`, `conversation_id`, `source_bundle_id`, and selected-paper identity (`url`, title, platform, year, abstract scope);
- a list of named `ReproductionPipelineSection` items for reproduction goal, research question, known method, data/sample conditions, candidate baselines, metrics, experiment steps, resources, risks, ethics, and confirmation items;
- a Python-oriented, decomposable `ReproductionTask` list with stable IDs, non-executable learning descriptions, task state derived from stored `ExperimentEvidenceBundle` items, and related evidence references;
- an explicit two-week MVP checklist and one provenance note.

Each section and task carries `classification` (`fact`, `inference`, or `to_verify`), `basis`, and an explicit `source_scope`. Only paper metadata and directly available abstract text may be `fact`. Rules that organize the research profile or plan are `inference`. The generator marks every data-set detail, experimental setting, numeric threshold, claimed conclusion, reproduction condition, resource guarantee, and ethics approval outside the selected abstract as `to_verify`.

## API and persistence

- `POST /api/v1/research/conversations/{conversation_id}/reproduction-pipelines` accepts the source bundle ID and one selected-paper URL; it rejects missing or non-member papers with an honest client error and performs no search/tool call.
- `GET /api/v1/research/conversations/{conversation_id}/reproduction-pipelines` restores saved Pipelines without regenerating one.
- `GET /api/v1/research/reproduction-pipelines/{pipeline_id}` allows B to load the stable Pipeline by ID after A merges.
- A dedicated SQLAlchemy model and Alembic revision persist JSON data under `research_reproduction_pipelines`; no existing evidence or experiment table is modified.

## User interface

`ReproductionPipelinePanel` fetches saved evidence bundles, requires a paper selection, and only generates after the user presses the explicit button. It presents the source scope, classifications, sections, two-week MVP tasks, task status, and linked user-provided experiment evidence. It describes Python tasks as learning scaffolds and never renders runnable code or execution controls.

## Error handling and safety

No selected paper means no Pipeline request and a clear, safe instruction. The service never calls the academic search service, provider, filesystem, code runner, or project writer. Stored experiment evidence is displayed as user-submitted, not independently verified. The UI reports API errors without presenting empty data as success.

## Tests

Tests cover source membership, no selection, source-scope degradation, persistence and restoration, task-to-experiment-evidence association, and a no-network guard. Frontend contract/copy tests cover explicit selection, the safety message, classification labels, and the absence of success or execution claims. Migration tests cover the new table on an empty and upgraded database.
