import { createElement, type ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({
  query: "set_id=A",
  fetchPracticeSet: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(harness.query),
}));

vi.mock("next/link", () => ({
  default: ({ children, ...props }: { children?: ReactNode; href: string }) =>
    createElement("a", props, children),
}));

vi.mock("@/components/learning/LearningFlowStepper", () => ({
  LearningFlowStepper: () => null,
}));

vi.mock("@/lib/api/practice", () => ({
  fetchPracticeSet: harness.fetchPracticeSet,
  fetchPracticeSetFromLearning: vi.fn(),
  generatePracticeSetFromLearning: vi.fn(),
  generatePracticeSetWithContext: vi.fn(),
  gradePracticeCodeFill: vi.fn(),
}));

vi.mock("@/lib/api/compiler", () => {
  class CompilerApiError extends Error {
    status = 503;
  }

  return {
    CompilerApiError,
    analyzeProblemImport: vi.fn(),
    askStructureTutor: vi.fn(),
    createPracticeLaunch: vi.fn().mockResolvedValue({
      launchId: "launch-1",
      localProfileId: "local-profile",
      learnerId: "learner-1",
      workspaceId: "workspace-1",
      taskId: null,
      sourceActivityId: null,
      capability: "practice",
      mode: "free_run",
      focus: null,
      expiresAt: "2099-01-01T00:00:00Z",
    }),
    evaluatePythonRun: vi.fn(),
    evaluateStructureExercise: vi.fn(),
    executePython: vi.fn(),
    fetchCompilerRecords: vi.fn().mockResolvedValue([]),
    fetchCompilerRuntime: vi.fn().mockResolvedValue({
      ready: false,
      language: "python",
      version: "3.11",
      limits: { wallTimeMs: 1, memoryBytes: 1, sourceBytes: 1 },
      message: "disabled",
      ai: { status: "disabled", message: "disabled" },
    }),
    fetchStructureExercises: vi.fn().mockResolvedValue({
      schemaVersion: "test",
      topics: [],
      exercises: [],
    }),
    generateProblemSet: vi.fn(),
    requestCompilerGuidance: vi.fn(),
    submitPython: vi.fn(),
    submitStructureExercise: vi.fn(),
  };
});

vi.mock("@/lib/api/workspaces", () => ({
  getLocalProfileId: () => "local-profile",
}));

vi.mock("@/lib/language-basics", () => ({
  readLanguageBasics: () => "has_basics",
  saveLanguageBasics: vi.fn(),
}));

vi.mock("@/lib/learner", () => ({
  getOrCreateLearnerId: () => "learner-1",
  newUuidV4: () => "00000000-0000-4000-8000-000000000001",
}));

vi.mock("@/lib/practice-context", () => ({
  isPracticeContextV1: () => false,
}));

vi.mock("@/lib/practice-direct-entry.mjs", () => ({
  canAdvanceContextStructureItem: () => false,
  createDirectEntryRequestCache: () => ({ getOrCreate: vi.fn() }),
  directEntryRequestKey: vi.fn(),
  shouldShowDirectStructureView: () => false,
}));

vi.mock("@/lib/store/flow-store", () => ({
  clearFlowPayload: vi.fn(),
  getPersistedFlowPayload: () => null,
  useFlowStore: (selector: (state: { payload: null }) => unknown) => selector({ payload: null }),
}));

import PracticePage from "@/app/(student)/learning/practice/page";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function codeFillSet(setId: string, title: string): Record<string, unknown> {
  return {
    set_id: setId,
    kind: "code_practice",
    items: [
      {
        item_id: `${setId}-item-01`,
        position: 1,
        item_kind: "code_fill",
        knowledge_points: [title],
        judging: "llm_static",
        payload: {
          title,
          language: "python",
          complexity: "light",
          judge_mode: "llm_static",
          code_masked: "def solve():\n    return ______\n\n# ______",
          blanks: [
            { blank_id: "blank-1", hint: "first", step_no: 1 },
            { blank_id: "blank-2", hint: "second", step_no: 1 },
          ],
          steps: [
            { step_no: 1, title: "step", reason: "reason", sub_steps: [] },
          ],
          source: "generated",
          reference_code_hash: "hash",
        },
        grading_hint: null,
      },
    ],
    coverage: [title],
    generation_mode: "mock",
    provider_name: "mock",
    effective_context: null,
    effective_topic: null,
  };
}

describe("practice set restore navigation", () => {
  beforeEach(() => {
    harness.query = "set_id=A";
    vi.clearAllMocks();
  });

  it("only displays the new set after set_id changes from A to B", async () => {
    const setA = deferred<Record<string, unknown>>();
    const setB = deferred<Record<string, unknown>>();
    harness.fetchPracticeSet.mockImplementation((setId: string) =>
      setId === "A" ? setA.promise : setB.promise,
    );

    const { rerender } = render(<PracticePage />);
    await waitFor(() => expect(harness.fetchPracticeSet).toHaveBeenCalledWith("A"));

    setA.resolve(codeFillSet("A", "题目 A"));
    expect(await screen.findByRole("heading", { name: "题目 A" })).toBeInTheDocument();

    harness.query = "set_id=B";
    rerender(<PracticePage />);

    expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("正在准备练习，请稍候。")).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument();
    });
    expect(harness.fetchPracticeSet).toHaveBeenCalledWith("B");

    setB.resolve(codeFillSet("B", "题目 B"));
    expect(await screen.findByRole("heading", { name: "题目 B" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument();
  });

  it("does not keep displaying A when the new set is empty", async () => {
    const setA = deferred<Record<string, unknown>>();
    harness.fetchPracticeSet.mockImplementation((setId: string) =>
      setId === "A" ? setA.promise : Promise.resolve({ ...codeFillSet("B", "题目 B"), items: [] }),
    );

    const { rerender } = render(<PracticePage />);
    await waitFor(() => expect(harness.fetchPracticeSet).toHaveBeenCalledWith("A"));
    setA.resolve(codeFillSet("A", "题目 A"));
    expect(await screen.findByRole("heading", { name: "题目 A" })).toBeInTheDocument();

    harness.query = "set_id=B";
    rerender(<PracticePage />);

    await waitFor(() => {
      expect(screen.getByText("该练习集不包含可打开的代码挖空题。")).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument();
    });
  });

  it("does not keep displaying A when the new set fails to restore", async () => {
    const setA = deferred<Record<string, unknown>>();
    harness.fetchPracticeSet.mockImplementation((setId: string) =>
      setId === "A" ? setA.promise : Promise.reject(new Error("练习集不存在")),
    );

    const { rerender } = render(<PracticePage />);
    await waitFor(() => expect(harness.fetchPracticeSet).toHaveBeenCalledWith("A"));
    setA.resolve(codeFillSet("A", "题目 A"));
    expect(await screen.findByRole("heading", { name: "题目 A" })).toBeInTheDocument();

    harness.query = "set_id=invalid";
    rerender(<PracticePage />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("练习集不存在");
      expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument();
    });
  });

  it("clears the restored workspace when set_id is removed", async () => {
    const setA = deferred<Record<string, unknown>>();
    harness.fetchPracticeSet.mockReturnValue(setA.promise);

    const { rerender } = render(<PracticePage />);
    await waitFor(() => expect(harness.fetchPracticeSet).toHaveBeenCalledWith("A"));
    setA.resolve(codeFillSet("A", "题目 A"));
    expect(await screen.findByRole("heading", { name: "题目 A" })).toBeInTheDocument();

    harness.query = "";
    rerender(<PracticePage />);

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "题目 A" })).not.toBeInTheDocument(),
    );
  });
});
