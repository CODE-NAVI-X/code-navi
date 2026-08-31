# Research downstream quality implementation plan

1. Add regression tests for downstream refresh contracts, task linkage controls, and unverified Pipeline evaluation.
2. Run those tests to confirm the current behavior fails where expected.
3. Implement the smallest API-type, refresh-prop, selector, linkage-control, evaluation, and workflow-presentation changes.
4. Run the focused Python tests, Ruff, diff check, and frontend lint, TypeScript, and build checks.
5. Commit only the B worktree changes locally and document any unavailable browser, server, account, or real-user checks.
