# S6 Determinism Audit

Date: 2026-07-14

Scope: kernel decisions and record/replay identity. The comparison excludes only Event `timestamp`; no payload canonicalization or broad normalization is allowed.

## Findings

| Source | Finding | Resolution |
| --- | --- | --- |
| Event IDs | `uuid4()` made compression payload references differ across replay. | Fixed: Event IDs derive from `(run_id, seq)` with UUIDv5. Production still creates a random run ID; replay supplies the recorded run ID. |
| Run IDs | A fresh replay previously had no way to reuse the source run ID. | Fixed: `run()` accepts an explicit run ID. Prior Events remain fact; a conflicting explicit ID follows the kernel fatal path. |
| Timestamps | `datetime.now(UTC)` is nondeterministic. | Accepted record-only metadata: timestamps are written to Events and never read by decision logic. Identity tests remove only this field. |
| Retry state | A successful call did not reset `attempt`, leaking retry state into later provider steps. | Fixed: every new provider step starts at attempt 1; the flagship sequence verifies attempts `1, 2, 1, 1`. |
| Retry delay | Backoff uses wall-clock sleeping. | Already controlled: delay values are deterministic exponential backoff and the sleeper is injected. There is no random jitter. |
| Dict and set order | Context code uses sets for membership and core uses mappings for JSON objects. | Audited: sets do not drive output ordering; ordered source sequences drive emitted payloads. Structural comparison treats JSON object key order as non-semantic but does not sort or rewrite payloads. |
| Event ordering | State folding accepts a Sequence and sorts by `seq`. | Accepted: `seq` is the frozen ordering fact, JSONL validation requires contiguous ordered values, and replay compares the resulting Event sequence. |
| External tools | Real tools can be nondeterministic or mutating. | Explicit S6 boundary: `ReplayProvider` replaces only provider I/O. The flagship replay uses a deterministic, side-effect-free dispatcher. A general recorded-tool replay mechanism is not introduced in S6. |

## Result

All kernel-controlled nondeterminism that affects Event payloads or references is fixed. The only excluded field in record/replay structural identity is `timestamp`. External tool determinism remains a caller/adapter responsibility and is explicitly outside the approved S6 mechanism.
