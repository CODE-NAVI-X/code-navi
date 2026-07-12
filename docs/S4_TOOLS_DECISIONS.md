# S4 Tools and Permissions Decisions

Status: **FROZEN for S4 v1 as of 2026-07-12.**

Amend only by explicit user decision. Record amendments in the changelog at the bottom.

This ledger freezes the conservative S4 implementation without reopening the S1,
S2, or S3 contracts. `docs/S4_TOOLS_DESIGN.md` remains the explanatory design
record; this document is the normative decision set.

## 1. Contract Compatibility

D1. S4 keeps the seven composable `ToolPermission` flags frozen by S2 D3:
`READ`, `WRITE`, `DESTRUCTIVE`, `EXECUTE`, `NETWORK`, `SENSITIVE`, and `PUBLISH`.
They are all-of capabilities, not mutually exclusive tiers.

D2. S4 adds no Event type. In particular, it does not add `tool_denied`,
`permission_checked`, or `provider_called`. Denials and ordinary tool errors are
structured `ToolResult` values; the S3 loop alone emits the existing
`tool_returned` and `message_added` Events.

D3. The S3 execution boundary remains exactly:

```python
tool_dispatcher.dispatch(call: ToolCall) -> ToolResult
```

`kernel/core/loop.py` is not modified by S4.

## 2. Registry and Run Binding

D4. `ToolRegistry` is a long-lived collection of explicit `(ToolSpec, handler)`
registrations. It never scans, auto-discovers, or performs import-time registration.
It stores no permission grant.

D5. `RunToolDispatcher` is a short-lived snapshot bound to one
`PermissionGrant` and one `ToolExecutionContext`. `run_scope` must match between
the grant and context, and their normalized workspace roots must be identical.
A host must create a fresh grant/dispatcher for each run.

D6. Grants are not global defaults, registry state, Event state, or persisted
resume state. Event history cannot restore a grant. A resumed run requires a new
host-provided grant and dispatcher.

D7. A registry may be frozen. A bound dispatcher receives a snapshot, so later
host registration cannot change the tool set visible to that run.

## 3. Tool Specification and Validation

D8. `ToolSpec` contains name, description, Draft 2020-12 argument schema,
required permission flags, and optional top-level `workspace_path_args` used to
scope WRITE tools.

D9. Tool names use `^[a-z][a-z0-9_.-]{0,63}$`. The argument schema root is an
object. Every tool declares at least one permission. Every WRITE tool declares at
least one workspace path argument.

D10. JSON Schema uses the `jsonschema` Draft 2020-12 reference implementation.
The registry validates the schema itself at registration and compiles a validator.
The dispatcher validates call arguments before permission or handler code sees them.

D11. Dispatch order is frozen as:

```text
registry lookup
-> JSON Schema validation
-> permission and workspace-scope check
-> handler execution
-> ToolResult normalization
```

Unknown tools, invalid arguments, and denied calls never invoke a handler.

## 4. Permission Semantics

D12. `READ` is the only ambient permission. `PermissionGrant` always includes it.
`WRITE`, `DESTRUCTIVE`, `EXECUTE`, `NETWORK`, `SENSITIVE`, and `PUBLISH` require
explicit per-run grant flags.

D13. Every required flag must be present. A composite tool is denied if any
non-READ required flag is missing.

D14. `DESTRUCTIVE` has a second gate: in addition to the flag, the exact tool
name must appear in `PermissionGrant.destructive_tool_names`. Either check alone
is insufficient.

D15. WRITE paths are normalized and must be inside a declared workspace root.
Relative paths are accepted only when exactly one root makes them unambiguous.
String-prefix checks are forbidden; resolved path containment is used so `..` and
existing symlink/junction escapes are rejected.

D16. Create and overwrite/delete capabilities should be separate tool specs.
An ordinary WRITE tool must not use a model-controlled `overwrite` parameter to
dynamically acquire destructive authority.

## 5. Results and Failures

D17. Tool success and failure use the existing `ToolResult` contract. Its
`result` contains a JSON envelope with `ok`, value or structured error, and audit
information. Its existing `permissions` field records the trusted ToolSpec
requirements.

D18. S4 structured error codes are `unknown_tool`, `invalid_arguments`,
`permission_denied`, `tool_error`, `tool_internal_error`, and
`invalid_tool_output`. The first three are zero-handler-call outcomes and are not
fatal run errors.

D19. Expected `ToolUserError` failures are safe model-visible tool errors.
Unexpected handler exceptions are normalized without exposing tracebacks.
`KeyboardInterrupt` and `SystemExit` are not swallowed.

D20. Dispatcher code emits no Event. The success or failure `ToolResult` returns
to S3, which retains sole ownership of Event emission.

## 6. Real Bash Tool

D21. The unrestricted Bash implementation lives in `kernel/tools/bash.py`, not
`kernel/core`. It requires at least `DESTRUCTIVE` and `EXECUTE`, including exact
tool-name authorization for `bash`.

D22. Bash permissions are static and reflect capability upper bounds. Command
text cannot lower them. The model cannot choose the Bash executable or inject
environment variables; both are trusted `ToolExecutionContext` values.

D23. Bash cwd must be an existing directory inside an authorized workspace root.
Execution has a bounded timeout, no stdin, a new process group, process-tree
termination on timeout, and bounded returned stdout/stderr.

D24. S4 does not add a READ-classified shell. Low-risk reads should be native READ
tools. Any future command runner remains at least `EXECUTE` under S2 D3.

## 7. Verification

D25. Registry tests cover explicit registration, duplicate/frozen behavior,
schema self-validation, unknown names, malformed arguments before handler entry,
successful normalization, and invalid handler output.

D26. Permission tests cover READ default behavior, every other flag's deny default,
all-of composition, per-tool destructive authorization, grant isolation between
runs, run-scope binding, workspace escape, and loop continuation after denial.

D27. Bash tests use a real filesystem canary and real Bash process. The canary
survives an ungranted call and is deleted only by a newly bound dispatcher with
both required flags and the exact destructive tool name.

## 8. Non-Goals Preserved

D28. S4 adds no confirmation UI, provider adapter, context truncation, persistence
backend, business approval flow, tool auto-discovery, or context-policy field on
`ToolSpec`.

Changelog:
- 2026-07-12 initial S4 v1 freeze after implementation and full regression tests.
