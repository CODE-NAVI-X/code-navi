import assert from "node:assert/strict";
import test from "node:test";

import {
  canAdvanceContextStructureItem,
  createDirectEntryRequestCache,
  directEntryRequestKey,
  shouldShowDirectStructureView,
} from "./practice-direct-entry.mjs";

const context = {
  source_session_id: "learning-session-1",
  knowledge_points: [{ name: "递归", source_ref: "note-1", mastery: 0.4 }],
  objective: "掌握递归终止条件",
  notes_summary: null,
};

test("returning to practice selection dismisses only the direct structure entry", () => {
  assert.equal(
    shouldShowDirectStructureView({
      view: "start",
      hasDirectContext: true,
      directEntryDismissed: false,
    }),
    true,
  );
  assert.equal(
    shouldShowDirectStructureView({
      view: "start",
      hasDirectContext: true,
      directEntryDismissed: true,
    }),
    false,
  );
  assert.equal(
    shouldShowDirectStructureView({
      view: "structure",
      hasDirectContext: false,
      directEntryDismissed: true,
    }),
    true,
  );
});

test("explain-only structure items remain reachable without a grade request", () => {
  assert.equal(
    canAdvanceContextStructureItem({ hasNext: true, explainOnly: true, graded: false }),
    true,
  );
  assert.equal(
    canAdvanceContextStructureItem({ hasNext: true, explainOnly: false, graded: false }),
    false,
  );
  assert.equal(
    canAdvanceContextStructureItem({ hasNext: false, explainOnly: true, graded: false }),
    false,
  );
});

test("a Strict Mode effect replay shares one direct-entry generation request", () => {
  const cache = createDirectEntryRequestCache();
  const firstKey = directEntryRequestKey(context, "learner-1");
  let calls = 0;
  const createRequest = () => ({ request: ++calls });

  assert.equal(cache.getOrCreate(firstKey, createRequest).request, 1);
  assert.equal(cache.getOrCreate(firstKey, createRequest).request, 1);

  const updatedKey = directEntryRequestKey(
    { ...context, objective: "掌握递归与回溯的边界" },
    "learner-1",
  );
  assert.equal(cache.getOrCreate(updatedKey, createRequest).request, 2);
});
