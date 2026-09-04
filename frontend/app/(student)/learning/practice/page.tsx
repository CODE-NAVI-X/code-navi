"use client";

import { Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  FileUp,
  FolderTree,
  Import,
  List,
  Loader2,
  Play,
  RotateCcw,
  Save,
  Search,
  Sparkles,
} from "lucide-react";
import { LearningFlowStepper } from "@/components/learning/LearningFlowStepper";
import {
  CompilerAiFeedback,
  CompilerExecutionResult,
  ImportedCompilerProblem,
  CompilerRecord,
  CompilerApiError,
  CompilerPracticeFocus,
  CompilerPracticeLaunch,
  CompilerRuntimeStatus,
  CompilerJudgeResult,
  CompilerStructureExercise,
  CompilerStructureSubmissionResult,
  fetchStructureExercises,
  GeneratedPracticeProblem,
  analyzeProblemImport,
  askStructureTutor,
  createPracticeLaunch,
  evaluateStructureExercise,
  evaluatePythonRun,
  executePython,
  fetchCompilerRecords,
  fetchCompilerRuntime,
  generateProblemSet,
  requestCompilerGuidance,
  submitStructureExercise,
  submitPython,
} from "@/lib/api/compiler";
import { getLocalProfileId } from "@/lib/api/workspaces";
import {
  gradePracticeCodeFill,
  generatePracticeSetWithContext,
  type PracticeCodeFillPayload,
  type PracticeCodeFillGradeResponse,
  type PracticeGatewayItem,
  type PracticeGatewaySetResponse,
} from "@/lib/api/practice";
import { isPracticeContextV1, type PracticeContextV1 } from "@/lib/practice-context";
import {
  canAdvanceContextStructureItem,
  createDirectEntryRequestCache,
  directEntryRequestKey,
  shouldShowDirectStructureView,
} from "@/lib/practice-direct-entry.mjs";
import { clearFlowPayload, getPersistedFlowPayload, useFlowStore } from "@/lib/store/flow-store";
import { getOrCreateLearnerId, newUuidV4 } from "@/lib/learner";

type Difficulty = "easy" | "medium" | "hard" | "custom";

interface PracticeExercise {
  id: string;
  title: string;
  summary: string;
  difficulty: Difficulty;
  tags: string[];
  description: string;
  inputHint: string;
  outputHint: string;
  source: string;
  stdin: string;
  origin?: "built_in" | "python_file" | "uploaded_problem" | "generated_problem";
  judgeable?: boolean;
  problemId?: string;
  problemVersion?: number;
  orderReason?: string;
  warnings?: string[];
  sampleTests?: Array<{ stdin: string; expectedOutput: string }>;
}

type PracticeView = "start" | "workspace" | "structure";

type StructureCatalogState =
  | { status: "loading"; message: string }
  | { status: "ready"; message: string }
  | { status: "error"; message: string };

type DirectStructureState =
  | { status: "idle"; message: string }
  | { status: "loading"; message: string }
  | { status: "ready"; message: string }
  | { status: "fallback"; message: string }
  | { status: "empty"; message: string }
  | { status: "error"; message: string };

interface ContextStructureItem {
  item: PracticeGatewayItem;
  payload: PracticeCodeFillPayload;
}

interface ContextStructureSet {
  response: PracticeGatewaySetResponse;
  items: ContextStructureItem[];
}

const STRUCTURE_KIND_LABELS: Record<"structure_sequence" | "framework_fill", string> = {
  structure_sequence: "结构排序",
  framework_fill: "代码挖空",
};

type PracticeLaunchMode = "free_run" | "problem_submit";

type PracticeLaunchState =
  | { key: string; mode: PracticeLaunchMode; status: "loading"; launch: null; message: string }
  | { key: string; mode: PracticeLaunchMode; status: "ready"; launch: CompilerPracticeLaunch; message: string }
  | { key: string; mode: PracticeLaunchMode; status: "unavailable"; launch: null; message: string };

type TimelineNoticeState = { key: string; message: string };
type KeyedState<T> = { key: string; value: T } | null;

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: "入门",
  medium: "进阶",
  hard: "挑战",
  custom: "自定义",
};

const DIFFICULTY_BADGES: Record<Difficulty, string> = {
  easy: "border-[#9eb3a6] bg-[#e8f3df] text-[#365f2f]",
  medium: "border-[#d8c48a] bg-[#fff3c9] text-[#725414]",
  hard: "border-[#e7aaa0] bg-[#ffe3dd] text-[#80342b]",
  custom: "border-[#b7bec8] bg-[#edf1f5] text-[#344052]",
};

const EXERCISES: PracticeExercise[] = [
  {
    id: "palindrome",
    title: "字符串回文判断",
    summary: "字符串 · 条件判断",
    difficulty: "easy",
    tags: ["字符串", "分支"],
    description: "读取一行文本，忽略首尾空白后，判断它是否从左向右和从右向左完全一致。",
    inputHint: "一行字符串",
    outputHint: "YES 或 NO",
    source: `text = input().strip()

is_palindrome = text == text[::-1]
print("YES" if is_palindrome else "NO")
`,
    stdin: "level\n",
  },
  {
    id: "list-sum",
    title: "整数列表求和",
    summary: "列表 · 输入处理",
    difficulty: "easy",
    tags: ["列表", "循环"],
    description: "读取一行以空格分隔的整数，输出所有整数之和。输入行至少包含一个整数。",
    inputHint: "空格分隔的整数",
    outputHint: "一个整数",
    source: `numbers = list(map(int, input().split()))

total = 0
for number in numbers:
    total += number

print(total)
`,
    stdin: "12 8 -3 5\n",
  },
  {
    id: "word-frequency",
    title: "统计最高频单词",
    summary: "字典 · 文本统计",
    difficulty: "medium",
    tags: ["字典", "统计"],
    description: "读取一行由小写单词组成的文本，输出出现次数最多的单词；次数相同时输出字典序更小者。",
    inputHint: "空格分隔的小写单词",
    outputHint: "单词和出现次数",
    source: `words = input().split()
counts = {}

for word in words:
    counts[word] = counts.get(word, 0) + 1

best = min(counts, key=lambda word: (-counts[word], word))
print(best, counts[best])
`,
    stdin: "pear apple pear banana apple pear\n",
  },
  {
    id: "bracket-match",
    title: "括号序列校验",
    summary: "栈 · 边界处理",
    difficulty: "hard",
    tags: ["栈", "算法"],
    description: "判断只包含圆括号、方括号和花括号的字符串是否正确闭合，并保持嵌套顺序。",
    inputHint: "一行括号字符串",
    outputHint: "VALID 或 INVALID",
    source: `text = input().strip()
pairs = {")": "(", "]": "[", "}": "{"}
stack = []

for char in text:
    if char in "([{":
        stack.append(char)
    elif not stack or stack.pop() != pairs[char]:
        print("INVALID")
        break
else:
    print("VALID" if not stack else "INVALID")
`,
    stdin: "{[()]}\n",
  },
].map((exercise) => ({ ...exercise, origin: "built_in" as const })) as PracticeExercise[];

function importedProblemToExercise(
  problem: ImportedCompilerProblem,
  batchId: string,
): PracticeExercise {
  return {
    id: `${batchId}-${problem.importId}`,
    title: problem.title,
    summary: `${problem.tags.join(" · ")} · 上传题目`,
    difficulty: problem.difficulty,
    tags: ["上传", ...problem.tags],
    description: problem.description,
    inputHint: problem.inputHint,
    outputHint: problem.outputHint,
    source: problem.starterCode,
    stdin: "",
    origin: "uploaded_problem",
    judgeable: false,
    orderReason: problem.orderReason,
    warnings: problem.warnings,
    sampleTests: problem.sampleTests,
  };
}

function isBinaryProblemFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".docx") || name.endsWith(".pdf");
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function generatedProblemToExercise(
  problem: GeneratedPracticeProblem,
  batchId: string,
): PracticeExercise {
  return {
    id: `${batchId}-${problem.id}`,
    title: problem.title,
    summary: `${problem.tags.join(" · ")} · ${
      problem.source === "built_in" ? "内置" : problem.source === "uploaded" ? "上传" : "生成"
    }`,
    difficulty: problem.difficulty,
    tags: [problem.source === "built_in" ? "内置" : problem.source === "uploaded" ? "上传" : "生成", ...problem.tags],
    description: problem.description,
    inputHint: problem.inputHint,
    outputHint: problem.outputHint,
    source: problem.starterCode,
    stdin: problem.sampleTests[0]?.stdin ?? "",
    origin:
      problem.source === "built_in"
        ? "built_in"
        : problem.source === "uploaded"
          ? "uploaded_problem"
          : "generated_problem",
    judgeable: problem.judgeable,
    problemId: problem.problemId,
    problemVersion: problem.problemVersion,
    orderReason: problem.generationReason,
    warnings: problem.limitations,
    sampleTests: problem.sampleTests,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function gatewayItemToContextStructureItem(
  item: PracticeGatewayItem,
): ContextStructureItem | null {
  if (
    item.item_kind !== "code_fill" ||
    !Array.isArray(item.knowledge_points) ||
    item.knowledge_points.length === 0
  ) {
    return null;
  }
  const payload = item.payload;
  if (
    typeof payload.title !== "string" ||
    payload.title.length === 0 ||
    payload.language !== "python" ||
    (payload.complexity !== "light" && payload.complexity !== "heavy") ||
    (payload.judge_mode !== "llm_static" && payload.judge_mode !== "explain_only") ||
    typeof payload.code_masked !== "string" ||
    !Array.isArray(payload.blanks) ||
    !Array.isArray(payload.steps)
  ) {
    return null;
  }
  const blanks = payload.blanks;
  const steps = payload.steps;
  if (
    blanks.length < 2 ||
    !blanks.every(
      (blank) =>
        isRecord(blank) &&
        typeof blank.blank_id === "string" &&
        typeof blank.hint === "string" &&
        typeof blank.step_no === "number",
    ) ||
    steps.length < 1 ||
    !steps.every(
      (step) =>
        isRecord(step) &&
        typeof step.step_no === "number" &&
        typeof step.title === "string" &&
        typeof step.reason === "string" &&
        Array.isArray(step.sub_steps) &&
        step.sub_steps.every((subStep) => typeof subStep === "string"),
    )
  ) {
    return null;
  }
  return {
    item,
    payload: payload as unknown as PracticeCodeFillPayload,
  };
}

function selectStructureFallback(
  exercises: CompilerStructureExercise[],
  context: PracticeContextV1,
): CompilerStructureExercise | null {
  const names = context.knowledge_points.map((point) => point.name.trim().toLowerCase());
  return (
    exercises.find((exercise) => {
      const searchable = [
        exercise.domain,
        exercise.title,
        exercise.objective,
        exercise.instruction,
        exercise.prompt,
        ...exercise.hints,
      ]
        .join(" ")
        .toLowerCase();
      return names.some((name) => name && (searchable.includes(name) || name.includes(exercise.domain)));
    }) ?? exercises[0] ?? null
  );
}

function PracticeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const payload = useFlowStore((s) => s.payload);
  const [learnerId] = useState(() => getLearnerId());
  const [persistedPayload, setPersistedPayload] = useState<ReturnType<typeof getPersistedFlowPayload>>(() =>
    typeof window === "undefined" ? null : getPersistedFlowPayload(),
  );
  const urlKnowledgeName = searchParams.get("knowledge_name");
  const urlKnowledgeId = searchParams.get("knowledge_id");
  const knowledgeName =
    urlKnowledgeName ?? payload?.masteredKnowledgePoint.name ?? persistedPayload?.masteredKnowledgePoint.name;
  const knowledgeId =
    urlKnowledgeId ?? payload?.masteredKnowledgePoint.id ?? persistedPayload?.masteredKnowledgePoint.id;
  const workspaceId = searchParams.get("workspace_id") ?? undefined;
  const taskId = searchParams.get("task_id") ?? undefined;
  const sessionId = searchParams.get("session_id") ?? payload?.sessionId ?? persistedPayload?.sessionId ?? undefined;
  const practiceFocus = useMemo(
    () => buildPracticeFocus(knowledgeId, knowledgeName),
    [knowledgeId, knowledgeName],
  );
  const launchContextKey = useMemo(
    () =>
      JSON.stringify({
        learnerId,
        workspaceId: workspaceId ?? "",
        taskId: taskId ?? "",
        focusType: practiceFocus?.type ?? "",
        focusId: practiceFocus?.id ?? "",
        focusLabel: practiceFocus?.label ?? "",
      }),
    [learnerId, practiceFocus, taskId, workspaceId],
  );
  const freeRunLaunchKey = `${launchContextKey}:free_run`;
  const problemSubmitLaunchKey = `${launchContextKey}:problem_submit`;
  const recommendedIds = payload?.payloadData.exerciseIds ?? persistedPayload?.payloadData.exerciseIds ?? [];
  const practiceContextCandidate: unknown =
    payload?.practiceContext ?? persistedPayload?.practiceContext ?? null;
  const directPracticeContext = isPracticeContextV1(practiceContextCandidate)
    ? practiceContextCandidate
    : null;
  const practiceContext = directPracticeContext;
  const directEntryKey = directPracticeContext
    ? directEntryRequestKey(directPracticeContext, learnerId)
    : null;

  const [view, setView] = useState<PracticeView>("start");
  const [structureExercises, setStructureExercises] = useState<CompilerStructureExercise[]>([]);
  const [structureCatalogState, setStructureCatalogState] = useState<StructureCatalogState>({
    status: "loading",
    message: "正在加载核心结构练习。",
  });
  const [directStructureState, setDirectStructureState] = useState<DirectStructureState>(
    directPracticeContext
      ? { status: "loading", message: "正在按学习上下文生成核心结构练习。" }
      : { status: "idle", message: "" },
  );
  const [directStructureSet, setDirectStructureSet] = useState<ContextStructureSet | null>(null);
  const [activeStructureExercise, setActiveStructureExercise] =
    useState<CompilerStructureExercise | null>(null);
  const [directEntryDismissed, setDirectEntryDismissed] = useState(false);
  const [query, setQuery] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "all">("all");
  const [selectedExerciseId, setSelectedExerciseId] = useState(EXERCISES[0].id);
  const [activeExercise, setActiveExercise] = useState<PracticeExercise>(EXERCISES[0]);
  const [practiceSelectionVersion, setPracticeSelectionVersion] = useState(0);
  const activePracticeKey = `${launchContextKey}:exercise:${activeExercise.id}:selection:${practiceSelectionVersion}`;
  const [importedExercises, setImportedExercises] = useState<PracticeExercise[]>([]);
  const [problemImportText, setProblemImportText] = useState("");
  const [problemImportContentBase64, setProblemImportContentBase64] = useState<string | null>(null);
  const [problemImportFileName, setProblemImportFileName] = useState<string | null>(null);
  const [problemImportPreview, setProblemImportPreview] = useState<ImportedCompilerProblem[]>([]);
  const [problemImportBusy, setProblemImportBusy] = useState(false);
  const [problemImportMessage, setProblemImportMessage] = useState<string | null>(null);
  const [setPrompt, setSetPrompt] = useState(() =>
    // Prefill from a handed-over practice-context.v1: the objective is the
    // user's own wording, not an inference.
    practiceContext?.objective?.trim() ? practiceContext.objective : "围绕当前知识点生成 5 道递进练习",
  );
  const [setTargetCount, setSetTargetCount] = useState(5);
  const [setDifficultyLow, setSetDifficultyLow] = useState<"easy" | "medium" | "hard">("easy");
  const [setDifficultyHigh, setSetDifficultyHigh] = useState<"easy" | "medium" | "hard">("hard");
  const [setKnowledgeTags, setSetKnowledgeTags] = useState(() =>
    practiceContext ? practiceContext.knowledge_points.map((point) => point.name).join(", ") : "",
  );
  const [setIncludeUploaded, setSetIncludeUploaded] = useState(true);
  const [setBusy, setSetBusy] = useState(false);
  const [setMessage, setSetMessage] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<CompilerRuntimeStatus | null>(null);
  const [source, setSource] = useState(EXERCISES[0].source);
  const [stdin, setStdin] = useState(EXERCISES[0].stdin);
  const [enableAi, setEnableAi] = useState(false);
  const [runningState, setRunningState] = useState<{ key: string; sequence: number } | null>(null);
  const [resultState, setResultState] = useState<KeyedState<CompilerExecutionResult>>(null);
  const [aiFeedbackState, setAiFeedbackState] = useState<KeyedState<CompilerAiFeedback>>(null);
  const [judgeResultState, setJudgeResultState] = useState<KeyedState<CompilerJudgeResult>>(null);
  const [guidanceMessageState, setGuidanceMessageState] = useState<KeyedState<string>>(null);
  const [guidanceState, setGuidanceState] = useState<KeyedState<Array<{ role: "user" | "assistant"; content: string }>>>(null);
  const [guidanceBusy, setGuidanceBusy] = useState(false);
  const [records, setRecords] = useState<CompilerRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [launchStates, setLaunchStates] = useState<Record<PracticeLaunchMode, PracticeLaunchState>>({
    free_run: loadingLaunchState("", "free_run"),
    problem_submit: loadingLaunchState("", "problem_submit"),
  });
  const [timelineNotice, setTimelineNotice] = useState<TimelineNoticeState | null>(null);
  const operationSequenceRef = useRef(0);
  const activePracticeKeyRef = useRef(activePracticeKey);
  const directEntryRequestCacheRef = useRef(createDirectEntryRequestCache());
  const pythonFileInputRef = useRef<HTMLInputElement>(null);
  const problemFileInputRef = useRef<HTMLInputElement>(null);
  const effectiveFreeRunLaunchState =
    launchStates.free_run.key === freeRunLaunchKey
      ? launchStates.free_run
      : loadingLaunchState(freeRunLaunchKey, "free_run");
  const effectiveProblemSubmitLaunchState =
    launchStates.problem_submit.key === problemSubmitLaunchKey
      ? launchStates.problem_submit
      : loadingLaunchState(problemSubmitLaunchKey, "problem_submit");
  const result = resultState?.key === activePracticeKey ? resultState.value : null;
  const aiFeedback = aiFeedbackState?.key === activePracticeKey ? aiFeedbackState.value : null;
  const judgeResult = judgeResultState?.key === activePracticeKey ? judgeResultState.value : null;
  const guidanceMessage = guidanceMessageState?.key === activePracticeKey ? guidanceMessageState.value : "";
  const guidance = guidanceState?.key === activePracticeKey ? guidanceState.value : [];
  const running = runningState?.key === activePracticeKey;
  const effectiveTimelineNotice =
    timelineNotice?.key === activePracticeKey ? timelineNotice.message : null;

  useLayoutEffect(() => {
    activePracticeKeyRef.current = activePracticeKey;
  }, [activePracticeKey]);

  useEffect(() => {
    let active = true;
    if (directPracticeContext && !directEntryDismissed) {
      return () => {
        active = false;
      };
    }
    const launchRequests: Array<{ mode: PracticeLaunchMode; key: string }> = [
      { mode: "free_run", key: freeRunLaunchKey },
      { mode: "problem_submit", key: problemSubmitLaunchKey },
    ];
    for (const { mode, key } of launchRequests) {
      void createPracticeLaunch({
        localProfileId: getLocalProfileId(),
        learnerId,
        workspaceId,
        taskId,
        mode,
        focus: practiceFocus,
      })
        .then((launch) => {
          if (!active) return;
          setLaunchStates((current) => ({
            ...current,
            [mode]: readyLaunchState(key, mode, launch),
          }));
        })
        .catch((launchError) => {
          if (!active) return;
          setLaunchStates((current) => ({
            ...current,
            [mode]: unavailableLaunchState(key, mode, launchError),
          }));
        });
    }
    return () => {
      active = false;
    };
  }, [
    directEntryDismissed,
    directPracticeContext,
    freeRunLaunchKey,
    learnerId,
    practiceFocus,
    problemSubmitLaunchKey,
    taskId,
    workspaceId,
  ]);

  useEffect(() => {
    let active = true;
    if (!directPracticeContext || !directEntryKey) {
      void Promise.resolve().then(() => {
        if (!active) return;
        setDirectStructureState({ status: "idle", message: "" });
        setDirectStructureSet(null);
      });
      return () => {
        active = false;
      };
    }

    void Promise.resolve().then(() => {
      if (!active) return;
      setDirectStructureState({
        status: "loading",
        message: "正在按学习上下文生成核心结构练习。",
      });
      setDirectStructureSet(null);
      setActiveStructureExercise(null);
      setDirectEntryDismissed(false);
    });
    const load = directEntryRequestCacheRef.current.getOrCreate(directEntryKey, () =>
      Promise.allSettled([
        fetchStructureExercises(),
        generatePracticeSetWithContext({
          context: directPracticeContext,
          count: 5,
          profileId: learnerId,
        }),
      ]),
    );

    void load.then(
      ([catalogResult, gatewayResult]) => {
        if (!active) return;

        const catalogExercises =
          catalogResult.status === "fulfilled" && Array.isArray(catalogResult.value.exercises)
            ? catalogResult.value.exercises
            : [];
        setStructureExercises(catalogExercises);
        if (catalogResult.status === "fulfilled") {
          setStructureCatalogState({
            status: "ready",
            message: catalogExercises.length
              ? "核心结构练习已加载。"
              : "结构练习目录为空。",
          });
        } else {
          setStructureCatalogState({
            status: "error",
            message: "核心结构练习目录加载失败，请稍后重试。",
          });
        }

        if (!directPracticeContext) return;

        const generatedResponse =
          gatewayResult.status === "fulfilled" ? gatewayResult.value : null;
        const generatedItems =
          generatedResponse && Array.isArray(generatedResponse.items)
            ? generatedResponse.items
                .map(gatewayItemToContextStructureItem)
                .filter((item): item is ContextStructureItem => item !== null)
            : [];
        if (generatedResponse && generatedItems.length) {
          setDirectStructureSet({
            response: generatedResponse,
            items: generatedItems,
          });
          setDirectStructureState({
            status: "ready",
            message: `已按学习上下文生成 ${generatedItems.length} 道核心结构练习；题目绑定：${
              Array.isArray(generatedResponse.coverage)
                ? generatedResponse.coverage.join("、") || "当前知识点"
                : "当前知识点"
            }。`,
          });
          return;
        }

        const fallback = selectStructureFallback(catalogExercises, directPracticeContext);
        if (fallback) {
          setActiveStructureExercise(fallback);
          setDirectStructureState({
            status: "fallback",
            message:
              "上下文练习集暂未返回可练题目，已切换到现有静态结构题；学习上下文仍保留在本页。",
          });
          return;
        }

        const gatewayUnavailable = gatewayResult.status === "rejected";
        const catalogUnavailable = catalogResult.status === "rejected";
        setDirectStructureState({
          status: gatewayUnavailable || catalogUnavailable ? "error" : "empty",
          message:
            gatewayUnavailable && catalogUnavailable
              ? "上下文练习集和结构练习目录都加载失败，请稍后重试。"
              : gatewayUnavailable
                ? "上下文练习集生成失败，结构练习目录也没有可用题目。"
                : catalogUnavailable
                  ? "结构练习目录加载失败，暂时没有可用的核心结构题。"
                  : "上下文练习集未返回可练结构题，结构练习目录为空。",
        });
      },
    );

    return () => {
      active = false;
    };
  }, [directEntryKey, directPracticeContext, learnerId]);

  const exercises = useMemo(
    () => [...importedExercises, ...EXERCISES],
    [importedExercises],
  );

  const visibleExercises = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return exercises.filter((exercise) => {
      const matchesDifficulty = difficulty === "all" || exercise.difficulty === difficulty;
      const searchable = [exercise.title, exercise.summary, ...exercise.tags]
        .join(" ")
        .toLowerCase();
      return matchesDifficulty && (!normalized || searchable.includes(normalized));
    });
  }, [difficulty, exercises, query]);

  useEffect(() => {
    let active = true;
    if (directPracticeContext && !directEntryDismissed) {
      return () => {
        active = false;
      };
    }
    void fetchCompilerRuntime()
      .then((status) => {
        if (!active) return;
        setRuntime(status);
        if (status.ai.status !== "ready") setEnableAi(false);
      })
      .catch((runtimeError: Error) => {
        if (!active) return;
        setRuntime({
          ready: false,
          language: "Python",
          version: "3.12.0",
          limits: {
            wallTimeMs: 2000,
            memoryBytes: 134217728,
            sourceBytes: 65536,
          },
          message: runtimeError.message || "执行服务未连接",
          ai: {
            status: "disabled",
            message: "执行服务离线",
          },
        });
        setEnableAi(false);
      });
    void fetchCompilerRecords(learnerId)
      .then((items) => {
        if (active) setRecords(items);
      })
      .catch(() => {
        if (active) setRecords([]);
      });
    return () => {
      active = false;
    };
  }, [directEntryDismissed, directPracticeContext, learnerId]);

  function invalidateActiveOperation() {
    setPracticeSelectionVersion((version) => version + 1);
    setRunningState(null);
    setGuidanceBusy(false);
  }

  function openExercise(exercise: PracticeExercise) {
    invalidateActiveOperation();
    setSelectedExerciseId(exercise.id);
    setActiveExercise(exercise);
    setSource(exercise.source);
    setStdin(exercise.stdin);
    setResultState(null);
    setAiFeedbackState(null);
    setJudgeResultState(null);
    setGuidanceState(null);
    setGuidanceMessageState(null);
    setTimelineNotice(null);
    setError(null);
    setView("workspace");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function startSelectedPractice() {
    const exercise =
      visibleExercises.find((item) => item.id === selectedExerciseId) ?? visibleExercises[0];
    if (exercise) openExercise(exercise);
  }

  async function importPythonSource(file: File | null) {
    if (!file) return;
    const imported: PracticeExercise = {
      id: "imported",
      title: file.name.replace(/\.py$/i, "") || "自定义代码",
      summary: "本地导入 · Python",
      difficulty: "custom",
      tags: ["自定义", "Python"],
      description: "从本地导入的 Python 单文件练习。",
      inputHint: "按代码需要填写",
      outputHint: "按代码逻辑输出",
      source: await file.text(),
      stdin: "",
      origin: "python_file",
      judgeable: false,
    };
    setImportedExercises((items) => [imported, ...items.filter((item) => item.id !== imported.id)]);
    setSelectedExerciseId(imported.id);
    setQuery("");
    setDifficulty("all");
  }

  async function generatePracticeSet() {
    if (!setPrompt.trim()) {
      setSetMessage("请先填写学习目标。");
      return;
    }
    setSetBusy(true);
    setSetMessage(null);
    try {
      // §3.1 boundary: when a practice-context.v1 was handed over, its body is
      // submitted through POST /api/v1/practice/sets/generate's `context` field.
      // The direct path stays in core structure practice; only an ordinary
      // entry uses the legacy compiler generation flow below.
      if (directPracticeContext) {
        const gatewayResponse = await generatePracticeSetWithContext({
          context: directPracticeContext,
          count: setTargetCount,
          profileId: learnerId,
        });
        const contextStructureItems = gatewayResponse.items
          .map(gatewayItemToContextStructureItem)
          .filter((item): item is ContextStructureItem => item !== null);
        if (contextStructureItems.length > 0) {
          setDirectStructureSet({
            response: gatewayResponse,
            items: contextStructureItems,
          });
          setActiveStructureExercise(null);
          setSetMessage(
            `已按学习上下文生成 ${contextStructureItems.length} 道核心结构练习；覆盖：${
              gatewayResponse.coverage.join("、") || "当前知识点"
            }`,
          );
          setView("structure");
          return;
        }
        const fallback = selectStructureFallback(structureExercises, directPracticeContext);
        if (fallback) {
          setActiveStructureExercise(fallback);
          setDirectStructureState({
            status: "fallback",
            message: "上下文练习集未返回可练结构题，已切换到现有静态结构题。",
          });
          setSetMessage("上下文练习集未返回可练结构题，已切换到现有静态结构题。");
          setView("structure");
          return;
        }
        setDirectStructureState({
          status: "empty",
          message: "上下文练习集未返回可练结构题，结构练习目录也为空。",
        });
        return;
      }
      const response = await generateProblemSet({
        prompt: setPrompt,
        learnerId,
        targetCount: setTargetCount,
        difficultyRange: [setDifficultyLow, setDifficultyHigh],
        knowledgeTags: setKnowledgeTags
          .split(/[，,]/)
          .map((tag) => tag.trim())
          .filter(Boolean),
        includeUploadedProblems: setIncludeUploaded,
        uploadedProblems: importedExercises
          .filter((exercise) => exercise.origin === "uploaded_problem")
          .map((exercise) => ({
            id: exercise.id,
            title: exercise.title,
            description: exercise.description,
            difficulty:
              exercise.difficulty === "custom" ? "medium" : exercise.difficulty,
            tags: exercise.tags.filter((tag) => tag !== "上传"),
            source: exercise.source,
            inputHint: exercise.inputHint,
            outputHint: exercise.outputHint,
            sampleTests: exercise.sampleTests,
          })),
      });
      const batchId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? `set-${crypto.randomUUID()}`
          : `set-${Date.now()}`;
      const generated = response.orderedProblems.map((problem) =>
        generatedProblemToExercise(problem, batchId),
      );
      setImportedExercises((items) => [
        ...generated,
        ...items.filter((item) => !generated.some((next) => next.id === item.id)),
      ]);
      if (generated[0]) {
        setSelectedExerciseId(generated[0].id);
        setQuery("");
        setDifficulty("all");
      }
      setSetMessage(
        `${response.source === "rules_with_ai_planning" ? "AI 已规划" : "已生成"} ${
          generated.length
        } 道练习；覆盖：${response.coverage.join("、") || "综合"}`,
      );
    } catch (generationError) {
      if (directPracticeContext) {
        const fallback = selectStructureFallback(structureExercises, directPracticeContext);
        if (fallback) {
          setActiveStructureExercise(fallback);
          setDirectStructureState({
            status: "fallback",
            message: "上下文练习集生成失败，已切换到现有静态结构题。",
          });
          setSetMessage("上下文练习集生成失败，已切换到现有静态结构题。");
          setView("structure");
        } else {
          setDirectStructureState({
            status: "error",
            message: generationError instanceof Error ? generationError.message : "练习集生成失败。",
          });
        }
        return;
      }
      setSetMessage(generationError instanceof Error ? generationError.message : "练习集生成失败。");
    } finally {
      setSetBusy(false);
    }
  }

  async function importProblemTextFile(file: File | null) {
    if (!file) return;
    try {
      if (isBinaryProblemFile(file)) {
        setProblemImportText("");
        setProblemImportContentBase64(await fileToBase64(file));
        setProblemImportFileName(file.name);
        setProblemImportPreview([]);
        setProblemImportMessage(`已读取题目文件：${file.name}`);
        return;
      }
      const text = await file.text();
      setProblemImportText(text);
      setProblemImportContentBase64(null);
      setProblemImportFileName(file.name);
      setProblemImportPreview([]);
      setProblemImportMessage(`已读取题目文件：${file.name}`);
    } catch {
      setProblemImportMessage("题目文件读取失败，请确认文件是文本格式。");
    }
  }

  async function analyzeUploadedProblems() {
    if (!problemImportText.trim() && !problemImportContentBase64) {
      setProblemImportMessage("请先上传题目文件或粘贴题目文本。");
      return;
    }
    setProblemImportBusy(true);
    setProblemImportMessage(null);
    try {
      const analyzed = await analyzeProblemImport({
        text: problemImportText,
        filename: problemImportFileName ?? undefined,
        contentBase64: problemImportContentBase64 ?? undefined,
        learnerId,
      });
      setProblemImportPreview(analyzed.problems);
      setProblemImportMessage(
        analyzed.problems.length > 0
          ? `已识别 ${analyzed.problems.length} 道题，可确认后加入本组练习。`
          : analyzed.warnings[0] ?? "未识别到题目。",
      );
    } catch (importError) {
      setProblemImportMessage(importError instanceof Error ? importError.message : "题目识别失败。");
    } finally {
      setProblemImportBusy(false);
    }
  }

  function addUploadedProblems() {
    const batchId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? `uploaded-${crypto.randomUUID()}`
        : `uploaded-${Date.now()}`;
    const imported = problemImportPreview.map((problem) =>
      importedProblemToExercise(problem, batchId),
    );
    setImportedExercises((items) => [
      ...imported,
      ...items.filter((item) => !imported.some((next) => next.id === item.id)),
    ]);
    if (imported[0]) {
      setSelectedExerciseId(imported[0].id);
      setQuery("");
      setDifficulty("all");
    }
    setProblemImportMessage(`已加入 ${imported.length} 道上传题目。`);
  }

  function moveImportedProblem(index: number, direction: -1 | 1) {
    setProblemImportPreview((items) => {
      const target = index + direction;
      if (target < 0 || target >= items.length) return items;
      const next = [...items];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((problem, position) => ({
        ...problem,
        orderReason: `手动调整为第 ${position + 1} 项；${problem.orderReason}`,
      }));
    });
  }

  function updateImportedProblem(
    importId: string,
    patch: Partial<Pick<ImportedCompilerProblem, "difficulty" | "tags">>,
  ) {
    setProblemImportPreview((items) =>
      items.map((problem) => (problem.importId === importId ? { ...problem, ...patch } : problem)),
    );
  }

  function isCurrentOperation(requestKey: string, operationSequence: number): boolean {
    return (
      activePracticeKeyRef.current === requestKey &&
      operationSequenceRef.current === operationSequence
    );
  }

  async function runCode() {
    if (effectiveFreeRunLaunchState.status === "loading") return;
    const requestKey = activePracticeKey;
    const operationSequence = operationSequenceRef.current + 1;
    operationSequenceRef.current = operationSequence;
    setRunningState({ key: requestKey, sequence: operationSequence });
    setError(null);
    setAiFeedbackState(null);
    const launch =
      effectiveFreeRunLaunchState.status === "ready" ? effectiveFreeRunLaunchState.launch : null;
    const attemptId = newUuidV4();
    try {
      const executed = await executePython({
        source,
        stdin,
        learnerId,
        enableAi,
        launchId: launch?.launchId,
        attemptId,
      });
      await applyExecutionResult(executed, launch, requestKey, operationSequence);
    } catch (runError) {
      if (isCurrentOperation(requestKey, operationSequence)) {
        if (launch && isLaunchScopeError(runError)) {
          setLaunchStates((current) => ({
            ...current,
            free_run: unavailableLaunchState(
              freeRunLaunchKey,
              "free_run",
              new Error("Workspace 时间线接入已失效，请重试。"),
            ),
          }));
          setTimelineNotice({
            key: requestKey,
            message: "Workspace 时间线接入已失效；请重试，重试将保留旧 Practice 执行能力且不会进入时间线。",
          });
        }
        setError(runError instanceof Error ? runError.message : "代码运行失败。");
      }
    } finally {
      if (isCurrentOperation(requestKey, operationSequence)) {
        setRunningState(null);
      }
    }
  }

  async function applyExecutionResult(
    executed: CompilerExecutionResult,
    launch: CompilerPracticeLaunch | null,
    requestKey: string,
    operationSequence: number,
  ) {
    if (!isCurrentOperation(requestKey, operationSequence)) return;
    setResultState({ key: requestKey, value: executed });
    setTimelineNotice({ key: requestKey, message: timelineMessage(executed.practiceOutcome, launch) });
    setAiFeedbackState({ key: requestKey, value: executed.ai });
    void refreshRecords();
    if (executed.ai.evaluationId) {
      const evaluated = await evaluatePythonRun({
        evaluationId: executed.ai.evaluationId,
        learnerId,
      });
      if (!isCurrentOperation(requestKey, operationSequence)) return;
      setAiFeedbackState({ key: requestKey, value: evaluated.ai });
      void refreshRecords();
    }
  }

  async function submitCode() {
    if (effectiveProblemSubmitLaunchState.status === "loading") return;
    const requestKey = activePracticeKey;
    const operationSequence = operationSequenceRef.current + 1;
    operationSequenceRef.current = operationSequence;
    setRunningState({ key: requestKey, sequence: operationSequence });
    setError(null);
    const launch =
      effectiveProblemSubmitLaunchState.status === "ready"
        ? effectiveProblemSubmitLaunchState.launch
        : null;
    const attemptId = newUuidV4();
    try {
      const judged = await submitPython({
        problemId: activeExercise.problemId ?? activeExercise.id,
        problemVersion: activeExercise.problemVersion,
        source,
        learnerId,
        launchId: launch?.launchId,
        attemptId,
      });
      if (!isCurrentOperation(requestKey, operationSequence)) return;
      setJudgeResultState({ key: requestKey, value: judged });
      setTimelineNotice({ key: requestKey, message: timelineMessage(judged.practiceOutcome, launch) });
    } catch (submitError) {
      if (isCurrentOperation(requestKey, operationSequence)) {
        if (launch && isLaunchScopeError(submitError)) {
          setLaunchStates((current) => ({
            ...current,
            problem_submit: unavailableLaunchState(
              problemSubmitLaunchKey,
              "problem_submit",
              new Error("Workspace 时间线接入已失效，请重试。"),
            ),
          }));
          setTimelineNotice({
            key: requestKey,
            message: "Workspace 时间线接入已失效；请重试，重试将保留旧 Practice 判题能力且不会进入时间线。",
          });
        }
        setError(submitError instanceof Error ? submitError.message : "提交判题失败");
      }
    } finally {
      if (isCurrentOperation(requestKey, operationSequence)) {
        setRunningState(null);
      }
    }
  }

  async function askTutor() {
    if (!judgeResult || !guidanceMessage.trim()) return;
    const message = guidanceMessage.trim();
    const requestKey = activePracticeKey;
    setGuidanceBusy(true);
    setGuidanceMessageState({ key: requestKey, value: "" });
    try {
      const response = await requestCompilerGuidance({
        submissionId: judgeResult.submissionId,
        message,
        learnerId,
        history: guidance,
      });
      if (activePracticeKeyRef.current === requestKey) {
        setGuidanceState({
          key: requestKey,
          value: [...guidance, { role: "user", content: message }, { role: "assistant", content: response.ai.reply }],
        });
      }
    } catch (tutorError) {
      if (activePracticeKeyRef.current === requestKey) {
        setError(tutorError instanceof Error ? tutorError.message : "AI 引导暂不可用");
      }
    } finally {
      setGuidanceBusy(false);
    }
  }

  async function refreshRecords() {
    try {
      setRecords(await fetchCompilerRecords(learnerId));
    } catch {
      setRecords([]);
    }
  }

  const canRunCode =
    runtime?.ready === true && effectiveFreeRunLaunchState.status !== "loading";
  const canSubmitCode =
    runtime?.ready === true &&
    activeExercise.origin === "built_in" &&
    effectiveProblemSubmitLaunchState.status !== "loading";

  function returnToPracticeStart() {
    invalidateActiveOperation();
    setDirectStructureSet(null);
    setActiveStructureExercise(null);
    setDirectEntryDismissed(true);
    setView("start");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const isDirectStructureView = shouldShowDirectStructureView({
    view,
    hasDirectContext: directPracticeContext !== null,
    directEntryDismissed,
  });

  if (isDirectStructureView) {
    if (directStructureSet) {
      return (
        <ContextStructureWorkspace
          structureSet={directStructureSet}
          profileId={learnerId}
          onBack={returnToPracticeStart}
        />
      );
    }
    if (activeStructureExercise) {
      return (
        <StructureExerciseWorkspace
          exercise={activeStructureExercise}
          onBack={returnToPracticeStart}
          notice={
            directStructureState.status === "fallback" ? directStructureState.message : undefined
          }
        />
      );
    }
    const entryState: DirectStructureState =
      directStructureState.status !== "idle"
        ? directStructureState
        : structureCatalogState.status === "loading"
          ? { status: "loading", message: structureCatalogState.message }
          : structureCatalogState.status === "error"
            ? { status: "error", message: structureCatalogState.message }
            : { status: "empty", message: structureCatalogState.message };
    return <StructurePracticeState state={entryState} onBack={returnToPracticeStart} />;
  }

  if (view === "start") {
    return (
      <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
        <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <LearningFlowStepper
            currentStep="practice"
            knowledgePoint={knowledgeName || undefined}
            sessionId={sessionId}
          />
          <PracticeTopbar runtime={runtime} error={error} />
          <TimelineBanner
            freeRunLaunchState={effectiveFreeRunLaunchState}
            problemSubmitLaunchState={effectiveProblemSubmitLaunchState}
            notice={effectiveTimelineNotice}
          />

          <section className="mx-auto w-full max-w-5xl py-10 sm:py-14">
            <div className="max-w-3xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-normal text-slate-500 dark:text-zinc-400">
                Code Practice / 软件工程实现
              </p>
              <h1 className="mt-3 text-4xl font-bold tracking-normal text-slate-950 dark:text-zinc-50 sm:text-5xl">
                今天想练什么？
              </h1>
              <div className="mt-4 flex flex-wrap items-center gap-2 text-sm leading-6 text-slate-500 dark:text-zinc-400">
                <p>{knowledgeName ? <>当前主题：<strong className="text-slate-700 dark:text-zinc-200">{knowledgeName}</strong>。选择一道题继续巩固。</> : "自由练习：选择一道题、上传自己的题目，或者带上 Python 文件开始。"}</p>
                {knowledgeName || practiceContext ? (
                  <button
                    type="button"
                    onClick={() => {
                      clearFlowPayload();
                      setPersistedPayload(null);
                      router.replace("/learning/practice");
                    }}
                    className="app-button-secondary rounded-full px-3 py-1 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
                  >
                    清除当前主题 / 自由练习
                  </button>
                ) : null}
              </div>
              {practiceContext ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                  <p className="font-semibold text-slate-800 dark:text-zinc-100">
                    已带入学习上下文（practice-context.v1）
                  </p>
                  <p className="mt-1">
                    知识点：{practiceContext.knowledge_points.map((point) => point.name).join("、")}
                  </p>
                  <p className="mt-1">学习目标：{practiceContext.objective}</p>
                  {practiceContext.notes_summary ? (
                    <p className="mt-1">笔记摘要：{practiceContext.notes_summary}</p>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="app-card mt-7 grid min-h-17 overflow-hidden rounded-2xl md:grid-cols-[minmax(0,1fr)_160px]">
              <label className="flex min-w-0 items-center gap-3 border-b border-slate-200 px-4 md:border-b-0 md:border-r dark:border-zinc-800">
                <Search className="h-4 w-4 flex-none text-slate-400" strokeWidth={1.5} />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") startSelectedPractice();
                  }}
                  placeholder="搜索题目、知识点或难度"
                  aria-label="搜索题目、知识点或难度"
                  className="h-16 min-w-0 flex-1 bg-transparent text-sm text-slate-950 outline-none placeholder:text-slate-400 dark:text-zinc-50"
                />
              </label>
              <button
                type="button"
                onClick={startSelectedPractice}
                className="app-button-primary inline-flex items-center justify-center gap-2 px-5 py-4 text-sm font-semibold transition hover:bg-slate-800 dark:hover:bg-zinc-200"
              >
                开始练习
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => pythonFileInputRef.current?.click()}
                className="app-button-secondary inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold shadow-sm hover:bg-slate-50 dark:hover:bg-zinc-800"
              >
                <FileUp className="h-3.5 w-3.5" strokeWidth={1.5} />
                导入 Python
              </button>
              <input
                ref={pythonFileInputRef}
                type="file"
                accept=".py,text/x-python,text/plain"
                className="hidden"
                onChange={(event) => void importPythonSource(event.target.files?.[0] ?? null)}
              />
              <a
                href="#problem-import"
                className="app-button-secondary inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold shadow-sm transition hover:bg-slate-50 dark:hover:bg-zinc-800"
              >
                <Import className="h-3.5 w-3.5" strokeWidth={1.5} />
                上传题目
              </a>
              <a
                href="#practice-set-generation"
                className="app-button-secondary inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold shadow-sm transition hover:bg-slate-50 dark:hover:bg-zinc-800"
              >
                <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
                生成练习集
              </a>
              <button
                type="button"
                onClick={() => router.push("/learning/projects")}
                className="app-button-secondary inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold shadow-sm transition hover:bg-slate-50 dark:hover:bg-zinc-800"
              >
                <FolderTree className="h-3.5 w-3.5" strokeWidth={1.5} />
                浏览项目代码
              </button>
              {(["all", "easy", "medium", "hard"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setDifficulty(item)}
                  className={`rounded-full border px-4 py-2 text-xs font-semibold transition ${
                    difficulty === item
                      ? "border-slate-400 bg-slate-950 text-white dark:border-zinc-500 dark:bg-zinc-100 dark:text-zinc-950"
                      : "border-slate-200 bg-white text-slate-500 hover:text-slate-950 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                  }`}
                >
                  {item === "all" ? "全部" : DIFFICULTY_LABELS[item]}
                </button>
              ))}
            </div>

            <section className="mt-8">
              <div className="mb-3 flex items-end justify-between">
                <div>
                  <p className="font-mono text-[11px] font-semibold uppercase text-slate-400 dark:text-zinc-500">
                    Practice Set
                  </p>
                  <h2 className="mt-1 text-xl font-bold">练习题</h2>
                </div>
                <span className="app-card-subtle rounded-full px-3 py-1 text-xs text-slate-500 dark:text-zinc-400">
                  {visibleExercises.length} 道
                </span>
              </div>
              <div className="app-card overflow-hidden rounded-2xl">
                {visibleExercises.length === 0 ? (
                  <p className="p-5 text-sm text-slate-500 dark:text-zinc-400">没有匹配的练习题</p>
                ) : (
                  visibleExercises.map((exercise, index) => (
                    <ExerciseRow
                      key={exercise.id}
                      exercise={exercise}
                      index={index}
                      selected={exercise.id === selectedExerciseId}
                      recommended={recommendedIds.includes(exercise.id)}
                      onSelect={() => setSelectedExerciseId(exercise.id)}
                      onOpen={() => openExercise(exercise)}
                    />
                  ))
                )}
              </div>
            </section>

            <section id="problem-import" className="app-card mt-8 rounded-2xl p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-[11px] font-semibold uppercase text-slate-400 dark:text-zinc-500">
                    Problem Import
                  </p>
                  <h2 className="mt-1 text-xl font-bold">上传题目并智能排列</h2>
                  <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500 dark:text-zinc-400">
                    上传题目文件或直接粘贴题目文本后，系统会识别题意、输入输出、难度和知识点，并按练习路径加入当前题组。上传题目默认只支持运行和 AI 评析，不使用服务端隐藏测试判题。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void analyzeUploadedProblems()}
                  disabled={problemImportBusy}
                  className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition hover:bg-slate-800 disabled:opacity-50 dark:hover:bg-zinc-200"
                >
                  {problemImportBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <BrainCircuit className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                  {problemImportBusy ? "识别中" : "识别并排列"}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => problemFileInputRef.current?.click()}
                  className="app-button-secondary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
                >
                  <FileUp className="h-3.5 w-3.5" strokeWidth={1.5} />
                  选择题目文件
                </button>
                <input
                  ref={problemFileInputRef}
                  type="file"
                  accept=".txt,.md,.markdown,.json,.csv,.docx,.pdf,text/plain,text/markdown,application/json,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
                  className="hidden"
                  onChange={(event) => void importProblemTextFile(event.target.files?.[0] ?? null)}
                />
                {problemImportFileName ? (
                  <span className="text-xs text-slate-500 dark:text-zinc-400">{problemImportFileName}</span>
                ) : (
                  <span className="text-xs text-slate-500 dark:text-zinc-400">也可以直接在下方粘贴题目内容</span>
                )}
              </div>
              <textarea
                value={problemImportText}
                onChange={(event) => {
                  setProblemImportText(event.target.value);
                  setProblemImportContentBase64(null);
                }}
                placeholder={"题目一：字符串回文判断\n描述：读取一行文本，判断是否为回文。\n输入：一行字符串\n输出：YES 或 NO"}
                aria-label="粘贴题目内容"
                className="app-input mt-4 min-h-36 w-full resize-y rounded-xl p-3 text-sm leading-6 outline-none focus:border-slate-500"
              />
              {problemImportMessage ? (
                <p className="mt-3 text-xs text-slate-500 dark:text-zinc-400">{problemImportMessage}</p>
              ) : null}
              {problemImportPreview.length > 0 ? (
                <div className="app-card-subtle mt-4 overflow-hidden rounded-xl">
                  {problemImportPreview.map((problem, index) => (
                    <ImportedProblemRow
                      key={problem.importId}
                      problem={problem}
                      index={index}
                      total={problemImportPreview.length}
                      onMove={moveImportedProblem}
                      onChange={updateImportedProblem}
                    />
                  ))}
                  <div className="border-t border-slate-200 bg-slate-50 p-3 text-right dark:border-zinc-800 dark:bg-zinc-900">
                    <button
                      type="button"
                      onClick={addUploadedProblems}
                      className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition hover:bg-slate-800 dark:hover:bg-zinc-200"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                      加入本组练习
                    </button>
                  </div>
                </div>
              ) : null}
            </section>

            <section id="practice-set-generation" className="app-card mt-8 rounded-2xl p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-[11px] font-semibold uppercase text-slate-400 dark:text-zinc-500">
                    Practice Set Generator
                  </p>
                  <h2 className="mt-1 text-xl font-bold">生成练习集</h2>
                  <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500 dark:text-zinc-400">
                    根据学习目标从内置题库和本次上传题中生成递进练习顺序。内置题可提交判题，上传题和生成题只支持运行与 AI 评析。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void generatePracticeSet()}
                  disabled={setBusy}
                  className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition hover:bg-slate-800 disabled:opacity-50 dark:hover:bg-zinc-200"
                >
                  {setBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                  {setBusy ? "生成中" : "生成并排列"}
                </button>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_160px]">
                <label className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                  学习目标
                  <textarea
                    value={setPrompt}
                    onChange={(event) => setSetPrompt(event.target.value)}
                    className="app-input mt-1 min-h-24 w-full resize-y rounded-xl p-3 text-sm font-normal leading-6"
                  />
                </label>
                <label className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                  题目数量
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={setTargetCount}
                    onChange={(event) => setSetTargetCount(Number(event.target.value))}
                    className="app-input mt-1 h-11 w-full rounded-xl px-3 text-sm font-normal"
                  />
                </label>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <label className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                  最低难度
                  <select
                    value={setDifficultyLow}
                    onChange={(event) =>
                      setSetDifficultyLow(event.target.value as "easy" | "medium" | "hard")
                    }
                    className="app-input mt-1 h-10 w-full rounded-xl px-3 text-sm font-normal"
                  >
                    <option value="easy">入门</option>
                    <option value="medium">进阶</option>
                    <option value="hard">挑战</option>
                  </select>
                </label>
                <label className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                  最高难度
                  <select
                    value={setDifficultyHigh}
                    onChange={(event) =>
                      setSetDifficultyHigh(event.target.value as "easy" | "medium" | "hard")
                    }
                    className="app-input mt-1 h-10 w-full rounded-xl px-3 text-sm font-normal"
                  >
                    <option value="easy">入门</option>
                    <option value="medium">进阶</option>
                    <option value="hard">挑战</option>
                  </select>
                </label>
                <label className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                  知识点
                  <input
                    value={setKnowledgeTags}
                    onChange={(event) => setSetKnowledgeTags(event.target.value)}
                    placeholder="循环, 列表, 字符串"
                    className="app-input mt-1 h-10 w-full rounded-xl px-3 text-sm font-normal"
                  />
                </label>
              </div>
              <label className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-zinc-200">
                <input
                  type="checkbox"
                  checked={setIncludeUploaded}
                  onChange={(event) => setSetIncludeUploaded(event.target.checked)}
                  className="h-4 w-4 accent-slate-900 dark:accent-zinc-100"
                />
                纳入本次上传题目
              </label>
              {setMessage ? (
                <p className="mt-3 text-xs text-slate-500 dark:text-zinc-400">{setMessage}</p>
              ) : null}
            </section>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
      <header className="sticky top-16 z-30 flex min-h-16 flex-wrap items-center gap-2 border-b border-slate-200 bg-[var(--app-card)]/95 px-3 py-2 shadow-[var(--app-shadow)] backdrop-blur md:px-5 dark:border-zinc-800">
        <button
          type="button"
          onClick={() => {
            returnToPracticeStart();
          }}
          className="app-button-secondary inline-flex h-10 w-10 items-center justify-center rounded-xl transition hover:bg-slate-50 dark:hover:bg-zinc-800"
          aria-label="返回练习选择"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
        </button>
        <button
          type="button"
          onClick={() => void submitCode()}
          disabled={running || !canSubmitCode}
          className="app-button-secondary inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
        >
          <CheckCircle2 className="h-4 w-4" strokeWidth={1.5} />
          提交判题
        </button>
        <div className="order-4 min-w-0 basis-full sm:order-none sm:basis-auto sm:flex-1">
          <span className="font-mono text-[10px] text-slate-400 dark:text-zinc-500">
          {activeExercise.origin === "python_file"
            ? "自定义练习"
            : activeExercise.origin === "uploaded_problem"
              ? "上传题目"
              : activeExercise.origin === "generated_problem"
                ? "生成题目"
              : `练习 ${String(exercises.findIndex((item) => item.id === activeExercise.id) + 1).padStart(2, "0")}`}
          </span>
          <strong className="block truncate text-sm text-slate-950 dark:text-zinc-50">{activeExercise.title}</strong>
        </div>
        <button
          type="button"
          onClick={() => void runCode()}
          disabled={running || !canRunCode}
          className="app-button-primary inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 dark:hover:bg-zinc-200"
        >
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
          ) : (
            <Play className="h-4 w-4" strokeWidth={1.5} />
          )}
          {running ? "运行中" : "运行并评析"}
        </button>
      </header>

      <div className="grid min-h-[calc(100vh-64px)] lg:grid-cols-[236px_minmax(0,1fr)]">
        <aside className="border-b border-slate-200 bg-[var(--app-card-subtle)] p-3 lg:border-b-0 lg:border-r dark:border-zinc-800">
          <div className="mb-3 flex items-center gap-2 px-2">
            <List className="h-4 w-4 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
            <strong className="text-xs">本组练习</strong>
          </div>
          <div className="space-y-1">
            {exercises.map((exercise, index) => (
              <button
                key={exercise.id}
                type="button"
                onClick={() => openExercise(exercise)}
                className={`grid w-full grid-cols-[28px_minmax(0,1fr)] gap-2 rounded-xl px-2 py-2.5 text-left transition ${
                  exercise.id === activeExercise.id
                    ? "bg-slate-200 text-slate-950 dark:bg-zinc-800 dark:text-zinc-50"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-50"
                }`}
              >
                <span className="font-mono text-[11px]">{String(index + 1).padStart(2, "0")}</span>
                <span className="min-w-0">
                  <strong className="block truncate text-xs">{exercise.title}</strong>
                  <small className="block text-[10px]">{DIFFICULTY_LABELS[exercise.difficulty]}</small>
                </span>
              </button>
            ))}
          </div>
          <HistoryPanel records={records} compact />
        </aside>

        <section className="min-w-0 p-4 md:p-5">
          <div className="mx-auto max-w-7xl">
            <TimelineBanner
              freeRunLaunchState={effectiveFreeRunLaunchState}
              problemSubmitLaunchState={effectiveProblemSubmitLaunchState}
              notice={effectiveTimelineNotice}
            />
            <section className="app-card mb-4 grid gap-4 rounded-2xl p-4 md:grid-cols-[minmax(0,1fr)_320px]">
              <div>
                <span
                  className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${DIFFICULTY_BADGES[activeExercise.difficulty]}`}
                >
                  {DIFFICULTY_LABELS[activeExercise.difficulty]}
                </span>
                <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-zinc-200">{activeExercise.description}</p>
                {activeExercise.orderReason ? (
                  <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">{activeExercise.orderReason}</p>
                ) : null}
                {activeExercise.warnings?.length ? (
                  <ul className="mt-2 space-y-1 text-xs text-amber-700">
                    {activeExercise.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
              <dl className="grid gap-2 text-xs text-slate-500 dark:text-zinc-400">
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
                  <dt className="font-semibold text-slate-950 dark:text-zinc-50">输入</dt>
                  <dd className="mt-1">{activeExercise.inputHint}</dd>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
                  <dt className="font-semibold text-slate-950 dark:text-zinc-50">输出</dt>
                  <dd className="mt-1">{activeExercise.outputHint}</dd>
                </div>
              </dl>
            </section>

            <div className="overflow-hidden rounded-2xl border border-[#252d29] bg-[#111814] shadow-[0_16px_36px_rgba(17,24,20,0.12)]">
              <div className="flex items-center justify-between border-b border-[#252d29] bg-[#17201b] px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-[#f6fbf4]">main.py</p>
                  <p className="text-[11px] text-[#9ba8a0]">
                    Python 单文件运行，资源限制由服务端控制
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSource(activeExercise.source);
                    setStdin(activeExercise.stdin);
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-[#435047] px-3 py-2 text-xs text-[#dbe7df] transition-colors hover:border-[#758278] hover:text-white"
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.5} />
                  重置
                </button>
              </div>
              <textarea
                value={source}
                onChange={(event) => setSource(event.target.value)}
                spellCheck={false}
                aria-label="Python 源码编辑器"
                className="min-h-[420px] w-full resize-y bg-[#111814] p-5 font-mono text-sm leading-6 text-[#f6fbf4] outline-none"
              />
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
              <div className="app-card rounded-2xl p-4">
                <label htmlFor="practice-standard-input" className="text-xs font-semibold text-slate-700 dark:text-zinc-200">标准输入</label>
                <textarea
                  id="practice-standard-input"
                  value={stdin}
                  onChange={(event) => setStdin(event.target.value)}
                  spellCheck={false}
                  className="app-input mt-3 min-h-32 w-full resize-y rounded-xl p-3 font-mono text-xs"
                />
                <label className="mt-3 flex items-center gap-2 text-xs text-slate-700 dark:text-zinc-200">
                  <input
                    type="checkbox"
                    checked={enableAi}
                    disabled={runtime?.ai.status !== "ready"}
                    onChange={(event) => setEnableAi(event.target.checked)}
                    className="h-4 w-4 accent-slate-900 dark:accent-zinc-100"
                  />
                  AI 评析
                </label>
                <p className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-zinc-400">
                  开启后，本次运行的源码和执行输出会发送给已配置的外部模型，可能产生费用。
                </p>
              </div>
              <ResultPanel result={result} error={error} />
            </div>

            {judgeResult ? <JudgePanel result={judgeResult} /> : null}
            {judgeResult ? (
              <TutorPanel
                messages={guidance}
                value={guidanceMessage}
                busy={guidanceBusy}
                onChange={(value) => setGuidanceMessageState({ key: activePracticeKey, value })}
                onSubmit={() => void askTutor()}
              />
            ) : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <AssessmentPanel result={result} aiFeedback={aiFeedback} />
              <HistoryPanel records={records} />
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function StructurePracticeState({
  state,
  onBack,
}: {
  state: DirectStructureState;
  onBack: () => void;
}) {
  const isError = state.status === "error";
  const isLoading = state.status === "loading";
  return (
    <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onBack}
          className="app-button-secondary inline-flex w-fit items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
          返回练习选择
        </button>
        <section className="app-card mt-10 rounded-2xl p-6 sm:p-8">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-normal text-slate-400 dark:text-zinc-500">
            Core Structure Practice
          </p>
          <h1 className="mt-2 text-3xl font-bold">核心结构练习</h1>
          <p
            role={isError ? "alert" : "status"}
            aria-live="polite"
            className="mt-4 max-w-2xl text-sm leading-6 text-slate-600 dark:text-zinc-300"
          >
            {isLoading ? "正在准备练习，请稍候。" : state.message}
          </p>
          {state.status === "empty" ? (
            <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-zinc-400">
              当前没有可用的核心结构题目；返回后可以继续使用普通练习入口。
            </p>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function StructureExerciseWorkspace({
  exercise,
  onBack,
  notice,
}: {
  exercise: CompilerStructureExercise;
  onBack: () => void;
  notice?: string;
}) {
  const levels = exercise.levels ?? [];
  const [levelIndex, setLevelIndex] = useState(0);
  const [sequenceAnswer, setSequenceAnswer] = useState<string[]>([]);
  const [levelAnswers, setLevelAnswers] = useState<string[][]>(() => levels.map(() => []));
  const [source, setSource] = useState(exercise.starterCode ?? "");
  const [result, setResult] = useState<CompilerStructureSubmissionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiFeedback, setAiFeedback] = useState<CompilerAiFeedback | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [chat, setChat] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const currentLevel = levels[levelIndex] ?? null;
  const options = currentLevel?.options ?? exercise.options;
  const currentAnswer = currentLevel ? levelAnswers[levelIndex] ?? [] : sequenceAnswer;
  const isSequence = exercise.kind === "structure_sequence";

  function updateCurrentAnswer(next: string[]) {
    if (!currentLevel) {
      setSequenceAnswer(next);
      return;
    }
    setLevelAnswers((answers) =>
      answers.map((answer, index) => (index === levelIndex ? next : answer)),
    );
  }

  function selectOption(option: string) {
    if (!isSequence || currentAnswer.includes(option)) return;
    updateCurrentAnswer([...currentAnswer, option]);
    setResult(null);
    setError(null);
  }

  function removeOption(option: string) {
    updateCurrentAnswer(currentAnswer.filter((item) => item !== option));
    setResult(null);
    setError(null);
  }

  async function submit() {
    if (isSequence && currentAnswer.length !== options.length) {
      setError("请先把所有步骤排列完成，再检查答案。");
      return;
    }
    if (!isSequence && !source.trim()) {
      setError("请先补全代码，再检查答案。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await submitStructureExercise({
        exerciseId: exercise.id,
        answer: isSequence ? currentAnswer : source,
        level: currentLevel?.level,
      });
      setResult(response);
      setAiFeedback(null);
      setEvaluating(true);
      try {
        const evaluated = await evaluateStructureExercise({
          exerciseId: exercise.id,
          answer: isSequence ? currentAnswer : source,
          level: currentLevel?.level,
        });
        setAiFeedback(evaluated.ai);
      } catch (evaluateError) {
        setAiFeedback({
          status: "unavailable",
          message:
            evaluateError instanceof Error ? evaluateError.message : "AI 评析暂不可用。",
        } as CompilerAiFeedback);
      } finally {
        setEvaluating(false);
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "结构练习提交失败。");
    } finally {
      setBusy(false);
    }
  }

  async function askStructureQuestion() {
    const question = chatQuestion.trim();
    if (!question) return;
    setChat((items) => [...items, { role: "user", content: question }]);
    setChatQuestion("");
    setChatBusy(true);
    try {
      const response = await askStructureTutor({
        exerciseId: exercise.id,
        question,
        history: chat,
      });
      setChat((items) => [
        ...items,
        { role: "assistant", content: response.ai.reply },
      ]);
    } catch (chatError) {
      setChat((items) => [
        ...items,
        {
          role: "assistant",
          content:
            chatError instanceof Error ? chatError.message : "AI 引导暂不可用。",
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  const hasNextLevel = isSequence && levelIndex < levels.length - 1;

  return (
    <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
      <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-zinc-800">
          <button
            type="button"
            onClick={onBack}
            className="app-button-secondary inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
            返回练习选择
          </button>
          <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-500 dark:border-zinc-700 dark:text-zinc-400">
            {STRUCTURE_KIND_LABELS[exercise.kind]}
          </span>
        </div>

        <section className="app-card mt-6 rounded-2xl p-5 sm:p-7">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-normal text-slate-400 dark:text-zinc-500">
            {exercise.domain}
          </p>
          <h1 className="mt-2 text-2xl font-bold sm:text-3xl">{exercise.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-300">
            {exercise.objective}
          </p>
          {notice ? (
            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              {notice}
            </p>
          ) : null}
        </section>

        <section className="app-card mt-4 rounded-2xl p-5 sm:p-7">
          <p className="text-sm font-semibold text-slate-950 dark:text-zinc-50">{exercise.prompt}</p>
          <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
            {currentLevel?.instruction ?? exercise.instruction}
          </p>
          {currentLevel ? (
            <p className="mt-3 text-xs font-semibold text-slate-700 dark:text-zinc-200">
              第 {currentLevel.level} 级：{currentLevel.title}
            </p>
          ) : null}

          {isSequence ? (
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              <div>
                <p className="text-xs font-semibold text-slate-700 dark:text-zinc-200">可选步骤</p>
                <div className="mt-2 space-y-2">
                  {options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => selectOption(option)}
                      disabled={currentAnswer.includes(option)}
                      className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 transition hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:border-zinc-500"
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-700 dark:text-zinc-200">你的排列</p>
                <div className="mt-2 min-h-32 space-y-2 rounded-xl border border-dashed border-slate-300 p-3 dark:border-zinc-700">
                  {currentAnswer.length === 0 ? (
                    <p className="text-xs leading-5 text-slate-400 dark:text-zinc-500">
                      点击左侧步骤加入排列。
                    </p>
                  ) : (
                    currentAnswer.map((option, index) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => removeOption(option)}
                        className="flex w-full items-start gap-2 rounded-lg bg-slate-100 px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-200 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
                      >
                        <span className="font-mono text-xs text-slate-400 dark:text-zinc-500">
                          {index + 1}.
                        </span>
                        <span>{option}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-5">
              <label
                htmlFor="structure-framework-answer"
                className="text-xs font-semibold text-slate-700 dark:text-zinc-200"
              >
                补全代码
              </label>
              <textarea
                id="structure-framework-answer"
                value={source}
                onChange={(event) => {
                  setSource(event.target.value);
                  setResult(null);
                  setError(null);
                }}
                spellCheck={false}
                className="app-input mt-2 min-h-72 w-full resize-y rounded-xl p-4 font-mono text-xs leading-5"
              />
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
                这是静态结构练习，不会执行代码；提交时只检查结构关键字。
              </p>
            </div>
          )}

          {exercise.hints.length > 0 ? (
            <details className="mt-5 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-zinc-900">
              <summary className="cursor-pointer text-xs font-semibold text-slate-700 dark:text-zinc-200">
                查看提示
              </summary>
              <div className="mt-2 space-y-1 text-xs leading-5 text-slate-500 dark:text-zinc-400">
                {exercise.hints.map((hint) => (
                  <p key={hint}>{hint}</p>
                ))}
              </div>
            </details>
          ) : null}

          {error ? (
            <p role="alert" className="mt-4 text-xs leading-5 text-rose-700 dark:text-rose-300">
              {error}
            </p>
          ) : null}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy}
              className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-200"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} /> : <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />}
              {busy ? "检查中" : "检查答案"}
            </button>
            {result?.verdict === "accepted" && hasNextLevel ? (
              <button
                type="button"
                onClick={() => {
                  setLevelIndex((index) => index + 1);
                  setResult(null);
                  setError(null);
                }}
                className="app-button-secondary rounded-xl px-4 py-2.5 text-xs font-semibold"
              >
                进入下一级
              </button>
            ) : null}
          </div>

          {result ? (
            <div
              role="status"
              aria-live="polite"
              className={`mt-5 rounded-xl border px-4 py-3 ${
                result.verdict === "accepted"
                  ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/30"
                  : "border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30"
              }`}
            >
              <p className="text-sm font-semibold">
                {result.verdict === "accepted" ? "答案正确" : "再检查一下步骤"} · {result.score} 分
              </p>
              <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600 dark:text-zinc-300">
                {result.feedback.map((item, index) => (
                  <p key={`${item.token ?? item.index ?? item.level ?? "feedback"}-${index}`}>
                    {item.status === "passed" ? "✓" : "!"} {item.message}
                  </p>
                ))}
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-zinc-300">
                {result.explanation}
              </p>
              {result.verdict === "accepted" && !hasNextLevel ? (
                <p className="mt-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                  本题结构练习已完成。
                </p>
              ) : null}
            </div>
          ) : null}

          {evaluating ? (
            <p className="mt-4 text-xs leading-5 text-slate-500 dark:text-zinc-400">
              正在生成结构评析…
            </p>
          ) : aiFeedback ? (
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900">
              <p className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
                AI 结构评析
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-zinc-300">
                {aiFeedback.explanation ?? aiFeedback.message ?? "暂无 AI 反馈。"}
              </p>
            </div>
          ) : null}

          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-zinc-700 dark:bg-zinc-900">
            <p className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
              AI 追问
            </p>
            {chat.length > 0 ? (
              <div className="mt-2 space-y-2">
                {chat.map((message, index) => (
                  <p
                    key={`${message.role}-${index}`}
                    className="rounded-lg px-3 py-2 text-xs leading-5 text-slate-600 dark:text-zinc-300"
                  >
                    <strong>{message.role === "user" ? "你" : "AI"}：</strong>
                    {message.content}
                  </p>
                ))}
              </div>
            ) : null}
            <form
              className="mt-3 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void askStructureQuestion();
              }}
            >
              <input
                value={chatQuestion}
                onChange={(event) => setChatQuestion(event.target.value)}
                placeholder="对这个结构题还有什么疑问？"
                className="app-input min-w-0 flex-1 rounded-xl px-3 py-2 text-xs"
              />
              <button
                type="submit"
                disabled={chatBusy || !chatQuestion.trim()}
                className="app-button-secondary rounded-xl px-3 py-2 text-xs font-semibold disabled:opacity-40"
              >
                {chatBusy ? "思考中" : "提问"}
              </button>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}

function ContextStructureWorkspace({
  structureSet,
  profileId,
  onBack,
}: {
  structureSet: ContextStructureSet;
  profileId: string;
  onBack: () => void;
}) {
  const [itemIndex, setItemIndex] = useState(0);
  const current = structureSet.items[itemIndex];

  if (!current) {
    return (
      <StructurePracticeState
        state={{ status: "empty", message: "上下文练习集没有可用的核心结构题目。" }}
        onBack={onBack}
      />
    );
  }

  return (
    <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
      <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-zinc-800">
          <button
            type="button"
            onClick={onBack}
            className="app-button-secondary inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
            返回练习选择
          </button>
          <span className="font-mono text-[11px] text-slate-400 dark:text-zinc-500">
            Core Structure Practice · {itemIndex + 1}/{structureSet.items.length}
          </span>
        </div>
        <section className="app-card mt-6 rounded-2xl p-5 sm:p-7">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-normal text-slate-400 dark:text-zinc-500">
            Learning Context → Practice
          </p>
          <h1 className="mt-2 text-2xl font-bold sm:text-3xl">核心结构练习</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-300">
            已跳过基础引导和语法测试，练习集直接来自学习上下文。
          </p>
          <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600 dark:bg-zinc-900 dark:text-zinc-300">
            题目绑定知识点：{current.item.knowledge_points.join("、") || "当前知识点"}
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
            本组覆盖：{structureSet.response.coverage.join("、") || "当前知识点"}
          </p>
        </section>
        <ContextStructureItem
          key={current.item.item_id}
          item={current}
          setId={structureSet.response.set_id}
          profileId={profileId}
          onNext={() => setItemIndex((index) => Math.min(index + 1, structureSet.items.length - 1))}
          hasNext={itemIndex < structureSet.items.length - 1}
        />
      </div>
    </main>
  );
}

function ContextStructureItem({
  item,
  setId,
  profileId,
  hasNext,
  onNext,
}: {
  item: ContextStructureItem;
  setId: string;
  profileId: string;
  hasNext: boolean;
  onNext: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PracticeCodeFillGradeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const explainOnly = item.payload.judge_mode === "explain_only";
  const canAdvance = canAdvanceContextStructureItem({
    hasNext,
    explainOnly,
    graded: result?.graded === true,
  });
  const isComplete = !hasNext && (explainOnly || result?.graded === true);

  async function submit() {
    if (explainOnly) return;
    if (item.payload.blanks.some((blank) => !answers[blank.blank_id]?.trim())) {
      setError("请先完成所有代码挖空，再提交检查。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await gradePracticeCodeFill({
        setId,
        itemId: item.item.item_id,
        attemptId: newUuidV4(),
        blankAnswers: item.payload.blanks.map((blank) => ({
          blankId: blank.blank_id,
          value: answers[blank.blank_id] ?? "",
        })),
        profileId,
      });
      setResult(response);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "代码挖空提交失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="app-card mt-4 rounded-2xl p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-slate-500 dark:text-zinc-400">代码挖空</p>
          <h2 className="mt-1 text-xl font-bold">{item.payload.title}</h2>
        </div>
        <span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500 dark:border-zinc-700 dark:text-zinc-400">
          {item.payload.complexity === "heavy" ? "讲解型" : "静态检查"}
        </span>
      </div>
      <pre className="mt-5 overflow-x-auto rounded-xl bg-[#111814] p-4 font-mono text-xs leading-6 text-[#f6fbf4]">
        {item.payload.code_masked}
      </pre>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {item.payload.blanks.map((blank) => (
          <label key={blank.blank_id} className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
            {blank.blank_id}
            <input
              value={answers[blank.blank_id] ?? ""}
              onChange={(event) => {
                setAnswers((current) => ({ ...current, [blank.blank_id]: event.target.value }));
                setResult(null);
                setError(null);
              }}
              placeholder={blank.hint}
              className="app-input mt-1 h-11 w-full rounded-xl px-3 font-mono text-xs font-normal"
              aria-label={`${blank.blank_id} 答案`}
            />
          </label>
        ))}
      </div>
      <div className="mt-5 rounded-xl bg-slate-50 px-4 py-3 dark:bg-zinc-900">
        <p className="text-xs font-semibold text-slate-700 dark:text-zinc-200">实现步骤</p>
        <div className="mt-2 space-y-3">
          {item.payload.steps.map((step) => (
            <div key={step.step_no} className="text-xs leading-5 text-slate-600 dark:text-zinc-300">
              <p className="font-semibold">步骤 {step.step_no}：{step.title}</p>
              <p className="mt-1">{step.reason}</p>
              {step.sub_steps.length > 0 ? (
                <p className="mt-1 text-slate-500 dark:text-zinc-400">{step.sub_steps.join(" · ")}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-500 dark:text-zinc-400">
        {explainOnly
          ? "该题只提供结构讲解，当前不会发送判题请求。"
          : "提交只进行静态代码挖空检查，不执行模型代码。"}
      </p>
      {error ? (
        <p role="alert" className="mt-3 text-xs leading-5 text-rose-700 dark:text-rose-300">
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || explainOnly}
          className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-200"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} /> : <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />}
          {busy ? "检查中" : "提交检查"}
        </button>
        {canAdvance ? (
          <button
            type="button"
            onClick={onNext}
            className="app-button-secondary rounded-xl px-4 py-2.5 text-xs font-semibold"
          >
            {explainOnly ? "继续下一道核心结构题" : "下一道核心结构题"}
          </button>
        ) : null}
        {isComplete ? (
          <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            本组核心结构练习已完成。
          </span>
        ) : null}
      </div>
      {result ? (
        <div role="status" aria-live="polite" className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900">
          <p className="text-sm font-semibold">得分：{result.total_score}/{result.total_max_score}</p>
          <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600 dark:text-zinc-300">
            {result.results.map((grade) => (
              <p key={grade.blank_id}>
                {grade.correct ? "✓" : "!"} {grade.blank_id}：{grade.comment ?? (grade.correct ? "正确" : "需要调整")}
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PracticeTopbar({
  runtime,
  error,
}: {
  runtime: CompilerRuntimeStatus | null;
  error: string | null;
}) {
  return (
    <header className="flex items-center justify-end border-b border-slate-200 pb-4 dark:border-zinc-800">
      <RuntimeBadge runtime={runtime} error={error} />
    </header>
  );
}

function ExerciseRow({
  exercise,
  index,
  selected,
  recommended,
  onSelect,
  onOpen,
}: {
  exercise: PracticeExercise;
  index: number;
  selected: boolean;
  recommended: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  return (
    <div
      className={`grid min-h-19 grid-cols-[minmax(0,1fr)_56px] border-t border-slate-200 first:border-t-0 transition dark:border-zinc-800 ${
        selected ? "bg-slate-100 shadow-[inset_2px_0_0_#0f172a] dark:bg-zinc-800 dark:shadow-[inset_2px_0_0_#fafafa]" : "hover:bg-slate-50 dark:hover:bg-zinc-900/70"
      }`}
    >
      <button type="button" onClick={onSelect} className="grid grid-cols-[44px_minmax(0,1fr)] gap-3 p-4 text-left">
        <span className="font-mono text-xs text-slate-400 dark:text-zinc-500">{String(index + 1).padStart(2, "0")}</span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <strong className="truncate text-sm text-slate-950 dark:text-zinc-50">{exercise.title}</strong>
            {recommended ? (
              <span className="rounded-full bg-slate-950 px-2 py-0.5 text-[10px] text-white dark:bg-zinc-100 dark:text-zinc-950">
                推荐
              </span>
            ) : null}
          </span>
          <small className="mt-1 block text-xs text-slate-500 dark:text-zinc-400">{exercise.summary}</small>
        </span>
      </button>
      <button
        type="button"
        onClick={onOpen}
        className="flex items-center justify-center border-l border-slate-200 text-slate-500 transition hover:bg-slate-950 hover:text-white dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-100 dark:hover:text-zinc-950"
        aria-label={`进入${exercise.title}`}
      >
        <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  );
}

function ImportedProblemRow({
  problem,
  index,
  total,
  onMove,
  onChange,
}: {
  problem: ImportedCompilerProblem;
  index: number;
  total: number;
  onMove: (index: number, direction: -1 | 1) => void;
  onChange: (
    importId: string,
    patch: Partial<Pick<ImportedCompilerProblem, "difficulty" | "tags">>,
  ) => void;
}) {
  return (
    <article className="grid gap-3 border-t border-slate-200 p-4 first:border-t-0 dark:border-zinc-800 md:grid-cols-[40px_minmax(0,1fr)_220px]">
      <span className="font-mono text-xs text-slate-400 dark:text-zinc-500">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <strong className="text-sm text-slate-950 dark:text-zinc-50">{problem.title}</strong>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${DIFFICULTY_BADGES[problem.difficulty]}`}>
            {DIFFICULTY_LABELS[problem.difficulty]}
          </span>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">{problem.description}</p>
        <p className="mt-2 text-[11px] text-slate-500 dark:text-zinc-400">{problem.orderReason}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-[11px] text-slate-500 dark:text-zinc-400">
            难度
            <select
              value={problem.difficulty}
              onChange={(event) =>
                onChange(problem.importId, {
                  difficulty: event.target.value as ImportedCompilerProblem["difficulty"],
                })
              }
              className="app-input ml-1 rounded-md px-1.5 py-1 text-[11px]"
            >
              <option value="easy">入门</option>
              <option value="medium">进阶</option>
              <option value="hard">挑战</option>
            </select>
          </label>
          <label className="min-w-0 flex-1 text-[11px] text-slate-500 dark:text-zinc-400">
            标签
            <input
              value={problem.tags.join(", ")}
              onChange={(event) =>
                onChange(problem.importId, {
                  tags: event.target.value
                    .split(",")
                    .map((tag) => tag.trim())
                    .filter(Boolean)
                    .slice(0, 6),
                })
              }
              className="app-input ml-1 w-full min-w-28 rounded-md px-1.5 py-1 text-[11px]"
            />
          </label>
        </div>
        {problem.warnings.length ? (
          <p className="mt-2 text-[11px] text-amber-700">{problem.warnings.join(" ")}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-start justify-between gap-2 text-left text-[11px] text-slate-500 dark:text-zinc-400 md:block md:text-right">
        <p>置信度 {Math.round(problem.confidence * 100)}%</p>
        <p className="mt-1">{problem.sampleTests.length ? `样例 ${problem.sampleTests.length} 组` : "无样例"}</p>
        <div className="mt-2 flex gap-1 md:justify-end">
          <button
            type="button"
            aria-label="上移题目"
            disabled={index === 0}
            onClick={() => onMove(index, -1)}
            className="app-button-secondary rounded-md px-2 py-1 disabled:opacity-40"
          >
            ↑
          </button>
          <button
            type="button"
            aria-label="下移题目"
            disabled={index === total - 1}
            onClick={() => onMove(index, 1)}
            className="app-button-secondary rounded-md px-2 py-1 disabled:opacity-40"
          >
            ↓
          </button>
        </div>
      </div>
    </article>
  );
}

function RuntimeBadge({
  runtime,
  error,
}: {
  runtime: CompilerRuntimeStatus | null;
  error: string | null;
}) {
  const ready = runtime?.ready === true;
  const label = ready
    ? `${runtime.language} ${runtime.version}`
    : runtime?.message ?? error ?? "连接运行环境";
  return (
    <div role={error ? "alert" : "status"} aria-live={error ? "assertive" : "polite"} className="app-card rounded-2xl px-4 py-3 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            ready ? "bg-[#77b255]" : error ? "bg-red-500" : "bg-amber-400"
          }`}
        />
        <span className="font-semibold text-slate-700 dark:text-zinc-200">
          {label}
        </span>
      </div>
      {runtime ? (
        <p className="mt-1 text-slate-500 dark:text-zinc-400">
          {formatDuration(runtime.limits.wallTimeMs)} /{" "}
          {formatBytes(runtime.limits.memoryBytes)}
        </p>
      ) : null}
    </div>
  );
}

function TimelineBanner({
  freeRunLaunchState,
  problemSubmitLaunchState,
  notice,
}: {
  freeRunLaunchState: PracticeLaunchState;
  problemSubmitLaunchState: PracticeLaunchState;
  notice: string | null;
}) {
  const hasUnavailable =
    freeRunLaunchState.status === "unavailable" ||
    problemSubmitLaunchState.status === "unavailable";
  const hasLoading =
    freeRunLaunchState.status === "loading" ||
    problemSubmitLaunchState.status === "loading";
  const tone = hasUnavailable
    ? "border-[#e7aaa0] bg-[#ffe3dd] text-[#80342b]"
    : hasLoading
      ? "border-[#d8c48a] bg-[#fff3c9] text-[#725414]"
      : "border-[#9eb3a6] bg-[#e8f3df] text-[#365f2f]";
  const title = hasUnavailable
    ? "部分 Practice 结果不会进入 Workspace 时间线。"
    : hasLoading
      ? "正在接入 Workspace 时间线。"
      : freeRunLaunchState.launch?.taskId || problemSubmitLaunchState.launch?.taskId
        ? "已接入当前 Task 时间线。"
        : "已接入个人 Workspace 时间线。";
  return (
    <div className={`mt-4 rounded-xl border px-4 py-3 text-xs leading-5 ${tone}`}>
      <p className="font-semibold">{title}</p>
      <p className="mt-1">
        {notice ??
          (hasUnavailable
            ? "已失效的入口会保留旧 Practice 能力；对应结果不会进入 Workspace 时间线。"
            : hasLoading
              ? "运行和提交会等待各自的 launch 签发完成。"
              : "运行和提交会分别使用对应的 launch 写入安全结果。")}
      </p>
      <p className="mt-1">
        运行：{launchStatusLabel(freeRunLaunchState)}；提交：
        {launchStatusLabel(problemSubmitLaunchState)}
      </p>
    </div>
  );
}

function launchStatusLabel(launchState: PracticeLaunchState): string {
  if (launchState.status === "ready") {
    return launchState.launch?.taskId ? "当前 Task" : "个人 Workspace";
  }
  if (launchState.status === "unavailable") return "旧 API，不进时间线";
  return "签发中";
}

function loadingLaunchState(key: string, mode: PracticeLaunchMode): PracticeLaunchState {
  return {
    key,
    mode,
    status: "loading",
    launch: null,
    message: "正在接入 Workspace 时间线。",
  };
}

function readyLaunchState(
  key: string,
  mode: PracticeLaunchMode,
  launch: CompilerPracticeLaunch,
): PracticeLaunchState {
  return {
    key,
    mode,
    status: "ready",
    launch,
    message: launch.taskId ? "已接入当前 Task 时间线。" : "已接入个人 Workspace 时间线。",
  };
}

function unavailableLaunchState(
  key: string,
  mode: PracticeLaunchMode,
  launchError: unknown,
): PracticeLaunchState {
  return {
    key,
    mode,
    status: "unavailable",
    launch: null,
    message: launchError instanceof Error
      ? `Workspace 时间线接入失败：${launchError.message}`
      : "Workspace 时间线接入失败。",
  };
}

function ResultPanel({
  result,
  error,
}: {
  result: CompilerExecutionResult | null;
  error: string | null;
}) {
  const output = error ?? result?.stderr ?? result?.stdout ?? "等待运行结果";
  return (
    <div className="app-card rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-700 dark:text-zinc-200">控制台输出</h2>
        <span className="app-card-subtle rounded-full px-2 py-1 text-[11px] text-slate-500 dark:text-zinc-400">
          {result?.outcome ?? "idle"}
        </span>
      </div>
      <pre
        role={error || result?.stderr ? "alert" : undefined}
        aria-live={error || result?.stderr ? "assertive" : undefined}
        className={`min-h-32 overflow-auto whitespace-pre-wrap rounded-xl border p-3 font-mono text-xs ${
          error || result?.stderr
            ? "border-red-200 bg-red-50 text-red-900"
            : "border-[#252d29] bg-[#111814] text-[#f6fbf4]"
        }`}
      >
        {output}
      </pre>
      {result ? (
        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-500 dark:text-zinc-400">
          <span>耗时 {formatDuration(result.metrics.wallTimeMs)}</span>
          <span>内存 {formatBytes(result.metrics.memoryBytes)}</span>
          <span>退出码 {result.exitCode ?? "-"}</span>
        </div>
      ) : null}
    </div>
  );
}

function JudgePanel({ result }: { result: CompilerJudgeResult }) {
  return (
    <section className="app-card mt-4 rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-950 dark:text-zinc-50">判题结果</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
            已通过 {result.passed}/{result.total} 个测试点，隐藏测试仅返回通过状态。
          </p>
        </div>
        <strong className={`text-2xl ${result.verdict === "accepted" ? "text-[#47723e]" : "text-[#a44b38]"}`}>
          {result.score.toFixed(0)} 分
        </strong>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {result.testResults.map((test) => (
            <div key={`${test.index}-${test.hidden}`} className="app-card-subtle rounded-xl p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-slate-500 dark:text-zinc-400">测试点 {test.index + 1}</span>
              <span className={test.status === "passed" ? "text-[#47723e]" : "text-[#a44b38]"}>
                {test.status === "passed" ? "通过" : test.status}
              </span>
            </div>
            <p className="mt-2 text-slate-500 dark:text-zinc-400">{test.hidden ? "隐藏测试" : "公开测试"}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function TutorPanel({
  messages,
  value,
  busy,
  onChange,
  onSubmit,
}: {
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <section className="app-card mt-4 rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <BrainCircuit className="h-4 w-4 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
        <h2 className="text-sm font-semibold text-slate-950 dark:text-zinc-50">AI 引导</h2>
      </div>
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">AI 只根据公开结果提问和提示，不直接提供完整答案。</p>
      <div className="mt-3 max-h-56 space-y-2 overflow-auto">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`rounded-xl p-3 text-xs leading-5 ${message.role === "assistant" ? "bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200" : "ml-6 bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950"}`}>
            {message.content}
          </div>
        ))}
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="描述你卡住的地方"
          aria-label="向 AI 引导描述卡住的问题"
          className="app-input min-w-0 flex-1 rounded-xl px-3 py-2 text-xs outline-none focus:border-slate-500"
        />
        <button type="submit" disabled={busy || !value.trim()} className="app-button-primary rounded-xl px-4 py-2 text-xs font-semibold disabled:opacity-50">
          {busy ? "思考中" : "提问"}
        </button>
      </form>
    </section>
  );
}

function AssessmentPanel({
  result,
  aiFeedback,
}: {
  result: CompilerExecutionResult | null;
  aiFeedback: CompilerAiFeedback | null;
}) {
  const assessment = result?.assessment;
  return (
    <div className="app-card rounded-2xl p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-zinc-50">
        <CheckCircle2 className="h-4 w-4 text-[#77a65b]" strokeWidth={1.5} />
        规则结论
      </h2>
      <p className="mt-3 text-sm font-semibold text-slate-700 dark:text-zinc-200">
        {assessment?.title ?? "尚未运行"}
      </p>
      <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
        {assessment?.summary ?? "运行后会展示确定性规则结论。"}
      </p>
      {assessment?.errorType ? (
        <p className="mt-2 font-mono text-[11px] text-amber-700">
          {assessment.errorType}
          {assessment.line ? ` / 第 ${assessment.line} 行` : ""}
        </p>
      ) : null}

      <div className="mt-5 border-t border-slate-200 pt-4 dark:border-zinc-800">
        <h3 className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-zinc-200">
          <BrainCircuit className="h-4 w-4 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
          AI 评析
        </h3>
        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
          {aiFeedback?.explanation ?? aiFeedback?.message ?? "未启用或暂无 AI 反馈。"}
        </p>
        {aiFeedback?.quality ? (
          <div className="app-card-subtle mt-3 rounded-xl p-3">
            <p className="text-[11px] text-slate-500 dark:text-zinc-400">代码质量参考分</p>
            <p className="mt-1 text-2xl font-bold text-[#47723e]">
              {aiFeedback.quality.overall}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HistoryPanel({
  records,
  compact = false,
}: {
  records: CompilerRecord[];
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact
          ? "mt-6 border-t border-slate-200 pt-4 dark:border-zinc-800"
          : "app-card rounded-2xl p-4"
      }
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-zinc-50">
        <Save className="h-4 w-4 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
        最近记录
      </h2>
      <div className="mt-3 space-y-2">
        {records.length === 0 ? (
          <p className="text-xs text-slate-500 dark:text-zinc-400">暂无练习记录</p>
        ) : (
          records.slice(0, compact ? 4 : 5).map((record) => (
            <article
              key={record.id}
              className={
                compact
                  ? "border-t border-slate-200 py-3 first:border-t-0 dark:border-zinc-800"
                  : "app-card-subtle rounded-xl p-3"
              }
            >
              <div className="flex items-center justify-between gap-2">
                <strong className="truncate text-xs text-slate-950 dark:text-zinc-50">{record.title}</strong>
                <span className="flex flex-none items-center gap-1 text-[11px] text-slate-500 dark:text-zinc-400">
                  <Clock3 className="h-3 w-3" strokeWidth={1.5} />
                  {formatRecordTime(record.createdAt)}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500 dark:text-zinc-400">
                {record.aiExplanation ?? record.summary}
              </p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function getLearnerId(): string {
  // Single source of truth for the unified profile key (shared with the
  // learning module) lives in ``lib/learner.ts``.
  return getOrCreateLearnerId();
}

function buildPracticeFocus(
  knowledgeId: string | undefined,
  knowledgeName: string | undefined,
): CompilerPracticeFocus | undefined {
  if (!knowledgeId && !knowledgeName) return undefined;
  return {
    type: "knowledge_point",
    id: knowledgeId,
    label: knowledgeName,
  };
}

function timelineMessage(
  outcome: CompilerExecutionResult["practiceOutcome"] | CompilerJudgeResult["practiceOutcome"],
  launch: CompilerPracticeLaunch | null,
): string {
  if (outcome) {
    return launch?.taskId
      ? "本次结果已纳入当前 Task 时间线。"
      : "本次结果已纳入个人 Workspace 时间线。";
  }
  if (launch) {
    return "本次结果未写入 Workspace 时间线；执行服务故障不会归入练习结果。";
  }
  return "本次结果不会进入 Workspace 时间线；旧 Practice 执行能力保持可用。";
}

function isLaunchScopeError(error: unknown): boolean {
  return (
    error instanceof CompilerApiError &&
    (error.status === 400 || error.status === 404) &&
    error.message.toLowerCase().includes("launch")
  );
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}

function formatRecordTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function PracticePage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] text-slate-500 dark:text-zinc-400" role="status" aria-live="polite">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.5} />
          页面加载中...
        </main>
      }
    >
      <PracticeContent />
    </Suspense>
  );
}
