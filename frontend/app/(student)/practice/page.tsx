"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  FileUp,
  Import,
  List,
  Loader2,
  Play,
  RotateCcw,
  Save,
  Search,
  Sparkles,
} from "lucide-react";
import {
  CompilerAiFeedback,
  CompilerExecutionResult,
  ImportedCompilerProblem,
  CompilerRecord,
  CompilerRuntimeStatus,
  CompilerJudgeResult,
  GeneratedPracticeProblem,
  analyzeProblemImport,
  evaluatePythonRun,
  executePython,
  fetchCompilerRecords,
  fetchCompilerRuntime,
  generateProblemSet,
  requestCompilerGuidance,
  submitPython,
} from "@/lib/api/compiler";
import { clearFlowPayload, getPersistedFlowPayload, useFlowStore } from "@/lib/store/flow-store";
import { getOrCreateLearnerId } from "@/lib/learner";

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

function PracticeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const payload = useFlowStore((s) => s.payload);
  const [persistedPayload, setPersistedPayload] = useState<ReturnType<typeof getPersistedFlowPayload>>(null);
  const urlKnowledgeName = searchParams.get("knowledge_name");
  const knowledgeName =
    urlKnowledgeName ?? payload?.masteredKnowledgePoint.name ?? persistedPayload?.masteredKnowledgePoint.name;
  const recommendedIds = payload?.payloadData.exerciseIds ?? persistedPayload?.payloadData.exerciseIds ?? [];

  const [view, setView] = useState<"start" | "workspace">("start");
  const [query, setQuery] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "all">("all");
  const [selectedExerciseId, setSelectedExerciseId] = useState(EXERCISES[0].id);
  const [activeExercise, setActiveExercise] = useState<PracticeExercise>(EXERCISES[0]);
  const [importedExercises, setImportedExercises] = useState<PracticeExercise[]>([]);
  const [problemImportText, setProblemImportText] = useState("");
  const [problemImportContentBase64, setProblemImportContentBase64] = useState<string | null>(null);
  const [problemImportFileName, setProblemImportFileName] = useState<string | null>(null);
  const [problemImportPreview, setProblemImportPreview] = useState<ImportedCompilerProblem[]>([]);
  const [problemImportBusy, setProblemImportBusy] = useState(false);
  const [problemImportMessage, setProblemImportMessage] = useState<string | null>(null);
  const [setPrompt, setSetPrompt] = useState("围绕当前知识点生成 5 道递进练习");
  const [setTargetCount, setSetTargetCount] = useState(5);
  const [setDifficultyLow, setSetDifficultyLow] = useState<"easy" | "medium" | "hard">("easy");
  const [setDifficultyHigh, setSetDifficultyHigh] = useState<"easy" | "medium" | "hard">("hard");
  const [setKnowledgeTags, setSetKnowledgeTags] = useState("");
  const [setIncludeUploaded, setSetIncludeUploaded] = useState(true);
  const [setBusy, setSetBusy] = useState(false);
  const [setMessage, setSetMessage] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<CompilerRuntimeStatus | null>(null);
  const [source, setSource] = useState(EXERCISES[0].source);
  const [stdin, setStdin] = useState(EXERCISES[0].stdin);
  const [enableAi, setEnableAi] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CompilerExecutionResult | null>(null);
  const [aiFeedback, setAiFeedback] = useState<CompilerAiFeedback | null>(null);
  const [judgeResult, setJudgeResult] = useState<CompilerJudgeResult | null>(null);
  const [guidanceMessage, setGuidanceMessage] = useState("");
  const [guidance, setGuidance] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [guidanceBusy, setGuidanceBusy] = useState(false);
  const [records, setRecords] = useState<CompilerRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [learnerId] = useState(() => getLearnerId());
  const pythonFileInputRef = useRef<HTMLInputElement>(null);
  const problemFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    queueMicrotask(() => setPersistedPayload(getPersistedFlowPayload()));
  }, []);

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
    void fetchCompilerRuntime()
      .then((status) => {
        if (!active) return;
        setRuntime(status);
        if (status.ai.status !== "ready") setEnableAi(false);
      })
      .catch((runtimeError: Error) => {
        if (active) setError(runtimeError.message);
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
  }, [learnerId]);

  function openExercise(exercise: PracticeExercise) {
    setSelectedExerciseId(exercise.id);
    setActiveExercise(exercise);
    setSource(exercise.source);
    setStdin(exercise.stdin);
    setResult(null);
    setAiFeedback(null);
    setJudgeResult(null);
    setGuidance([]);
    setGuidanceMessage("");
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

  async function runCode() {
    setRunning(true);
    setError(null);
    setAiFeedback(null);
    try {
      const executed = await executePython({ source, stdin, learnerId, enableAi });
      setResult(executed);
      setAiFeedback(executed.ai);
      void refreshRecords();
      if (executed.ai.evaluationId) {
        const evaluated = await evaluatePythonRun({
          evaluationId: executed.ai.evaluationId,
          learnerId,
        });
        setAiFeedback(evaluated.ai);
        void refreshRecords();
      }
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "代码运行失败。");
    } finally {
      setRunning(false);
    }
  }

  async function submitCode() {
    setRunning(true);
    setError(null);
    try {
      const judged = await submitPython({
        problemId: activeExercise.problemId ?? activeExercise.id,
        problemVersion: activeExercise.problemVersion,
        source,
        learnerId,
      });
      setJudgeResult(judged);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "提交判题失败");
    } finally {
      setRunning(false);
    }
  }

  async function askTutor() {
    if (!judgeResult || !guidanceMessage.trim()) return;
    const message = guidanceMessage.trim();
    setGuidanceBusy(true);
    setGuidanceMessage("");
    try {
      const response = await requestCompilerGuidance({
        submissionId: judgeResult.submissionId,
        message,
        learnerId,
        history: guidance,
      });
      setGuidance((items) => [...items, { role: "user", content: message }, { role: "assistant", content: response.ai.reply }]);
    } catch (tutorError) {
      setError(tutorError instanceof Error ? tutorError.message : "AI 引导暂不可用");
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

  if (view === "start") {
    return (
      <main className="min-h-screen bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
        <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <PracticeTopbar runtime={runtime} error={error} />

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
                {knowledgeName ? (
                  <button
                    type="button"
                    onClick={() => {
                      clearFlowPayload();
                      setPersistedPayload(null);
                      router.replace("/practice");
                    }}
                    className="app-button-secondary rounded-full px-3 py-1 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
                  >
                    清除当前主题 / 自由练习
                  </button>
                ) : null}
              </div>
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
          onClick={() => setView("start")}
          className="app-button-secondary inline-flex h-10 w-10 items-center justify-center rounded-xl transition hover:bg-slate-50 dark:hover:bg-zinc-800"
          aria-label="返回练习选择"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
        </button>
        <button
          type="button"
          onClick={() => void submitCode()}
          disabled={running || !runtime?.ready || activeExercise.origin !== "built_in"}
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
          disabled={running || !runtime?.ready}
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
                onChange={setGuidanceMessage}
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
  return (
    <div role={error ? "alert" : "status"} aria-live={error ? "assertive" : "polite"} className="app-card rounded-2xl px-4 py-3 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            ready ? "bg-[#77b255]" : error ? "bg-red-500" : "bg-amber-400"
          }`}
        />
        <span className="font-semibold text-slate-700 dark:text-zinc-200">
          {ready ? `${runtime.language} ${runtime.version}` : error ?? "连接运行环境"}
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
