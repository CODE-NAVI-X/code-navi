"use client";

import {
  type ExplainResponse,
  explainKnowledgePoint,
  getRecentLearning,
  LearningApiError,
  listRecentLearning,
  MAX_LEARNING_INPUT_CHARS,
  type RecentLearningItem,
  type SceneOutline,
  type Slide,
  type PresentationGenerationMode,
  setLearningSessionId,
  streamPresentation,
} from "@/lib/api/learning";
import TextSelectionPopover from "@/components/learning/TextSelectionPopover";
import { StructuredNotebook } from "@/components/learning/StructuredNotebook";
import { DownstreamGoCard } from "@/components/learning/DownstreamGoCard";
import { SlideViewer } from "@/components/learning/presentation/SlideViewer";
import { QuizView } from "@/components/learning/QuizView";
import {
  DEFAULT_QUIZ_PARAMS,
  exportQuizDocx,
  generateQuiz,
  type QuizGenerateParams,
  type QuizGenerateResponse,
} from "@/lib/api/quiz";
import { exportSlidesToPptx } from "@/lib/export/export-pptx";
import { type JSX, useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { buildKnowledgeId } from "@/lib/learning-context";
import { getLocalProfileId } from "@/lib/api/workspaces";
import {
  setLearningSnapshot,
  useLearningSessionId,
  useLearningStore,
} from "@/lib/store/learning-store";
import {
  BookOpen,
  Sparkles,
  ExternalLink,
  GraduationCap,
  Search,
  Loader2,
  AlertCircle,
  Presentation,
  FileQuestion,
  Wrench,
  Calculator,
  Sigma,
  Code2,
  CircuitBoard,
  GitBranch,
  Cpu,
  Layers,
  Server,
  Network,
  ShieldCheck,
  Database,
  Braces,
  Palette,
  Globe2,
  Brain,
  Boxes,
  Bot,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

// ── UI helpers ─────────────────────────────────────────────────────────────────

/** Trivial skeleton shimmer while a request is in-flight. */
function SkeletonLine({ width = "w-full" }: { width?: string }) {
  return (
    <div className={`h-4 ${width} animate-pulse rounded-md bg-slate-100 dark:bg-zinc-800`} />
  );
}

type SubjectDirection = {
  id: string;
  label: string;
  summary: string;
  sampleTopics: string[];
  icon: LucideIcon;
  domainIds: string[];
};

type ComputerDomain = {
  id: string;
  label: string;
};

const COMPUTER_DOMAINS: ComputerDomain[] = [
  { id: "ai-data", label: "AI 与数据" },
  { id: "computer-systems", label: "计算机系统" },
  { id: "software-programming", label: "软件与编程" },
  { id: "theory-mathematics", label: "理论与数学" },
  { id: "network-security", label: "网络与安全" },
  { id: "hardware-architecture", label: "硬件与体系结构" },
];

const SUBJECT_DIRECTIONS: SubjectDirection[] = [
  {
    id: "essential-tools",
    label: "必学工具",
    summary: "Git、Linux、编辑器、构建工具与日常学习工作流。",
    sampleTopics: ["Git 分支模型", "Docker 基础", "GNU Make"],
    icon: Wrench,
    domainIds: ["software-programming", "computer-systems"],
  },
  {
    id: "math-foundation",
    label: "数学基础",
    summary: "微积分、线性代数、信息论与熵等计算机数学底座。",
    sampleTopics: ["线性代数特征值", "信息熵", "多元微积分"],
    icon: Calculator,
    domainIds: ["theory-mathematics", "ai-data"],
  },
  {
    id: "advanced-math",
    label: "数学进阶",
    summary: "离散数学、概率论、数值分析、凸优化与模式识别。",
    sampleTopics: ["离散数学归纳法", "凸优化 KKT 条件", "数值分析误差"],
    icon: Sigma,
    domainIds: ["theory-mathematics", "ai-data"],
  },
  {
    id: "programming-intro",
    label: "编程入门",
    summary: "Python、C、C++、Java、Rust 与函数式语言入门。",
    sampleTopics: ["Python 作用域", "C 指针", "Rust 所有权"],
    icon: Code2,
    domainIds: ["software-programming"],
  },
  {
    id: "electronics",
    label: "电子基础",
    summary: "电路、信号系统与信息设备设计的基础课程。",
    sampleTopics: ["信号与系统卷积", "RC 电路", "频域分析"],
    icon: CircuitBoard,
    domainIds: ["hardware-architecture", "theory-mathematics"],
  },
  {
    id: "data-structures-algorithms",
    label: "数据结构与算法",
    summary: "数据结构、算法设计、复杂度与困难问题。",
    sampleTopics: ["红黑树", "动态规划", "NP 完全性"],
    icon: GitBranch,
    domainIds: ["software-programming", "theory-mathematics"],
  },
  {
    id: "software-engineering",
    label: "软件工程",
    summary: "软件构造、工程实践、团队协作与经验方法。",
    sampleTopics: ["单元测试", "重构", "软件需求分析"],
    icon: Layers,
    domainIds: ["software-programming"],
  },
  {
    id: "computer-systems",
    label: "计算机系统基础",
    summary: "程序表示、内存、链接、进程与系统级编程。",
    sampleTopics: ["虚拟内存", "链接器", "进程地址空间"],
    icon: Cpu,
    domainIds: ["computer-systems", "software-programming"],
  },
  {
    id: "architecture",
    label: "体系结构",
    summary: "数字设计、处理器、流水线、缓存与体系结构。",
    sampleTopics: ["CPU 流水线", "Cache 一致性", "RISC-V 指令集"],
    icon: Server,
    domainIds: ["hardware-architecture", "computer-systems"],
  },
  {
    id: "operating-systems",
    label: "操作系统",
    summary: "进程、线程、文件系统、虚拟化与内核实现。",
    sampleTopics: ["进程调度", "文件系统 inode", "虚拟内存分页"],
    icon: Cpu,
    domainIds: ["computer-systems"],
  },
  {
    id: "parallel-distributed-systems",
    label: "并行与分布式系统",
    summary: "并行计算、分布式系统、共识与容错。",
    sampleTopics: ["Raft 共识", "MapReduce", "并行加速比"],
    icon: Boxes,
    domainIds: ["computer-systems", "ai-data"],
  },
  {
    id: "computer-security",
    label: "计算机系统安全",
    summary: "系统安全、漏洞利用、防护机制与网络安全基础。",
    sampleTopics: ["缓冲区溢出", "SQL 注入", "访问控制"],
    icon: ShieldCheck,
    domainIds: ["network-security", "computer-systems"],
  },
  {
    id: "computer-networking",
    label: "计算机网络",
    summary: "互联网协议、传输层、路由、拥塞控制与应用协议。",
    sampleTopics: ["TCP 拥塞控制", "DNS 解析", "BGP 路由"],
    icon: Network,
    domainIds: ["network-security", "computer-systems"],
  },
  {
    id: "database-systems",
    label: "数据库系统",
    summary: "关系模型、查询优化、事务、存储与数据库实现。",
    sampleTopics: ["事务隔离级别", "B+ 树索引", "查询优化"],
    icon: Database,
    domainIds: ["ai-data", "computer-systems"],
  },
  {
    id: "compilers",
    label: "编译原理",
    summary: "词法语法分析、中间表示、优化与代码生成。",
    sampleTopics: ["LR 语法分析", "SSA 形式", "寄存器分配"],
    icon: Braces,
    domainIds: ["software-programming", "computer-systems"],
  },
  {
    id: "programming-languages",
    label: "编程语言设计与分析",
    summary: "语义、类型系统、程序分析与语言实现。",
    sampleTopics: ["类型推导", "Lambda 演算", "静态程序分析"],
    icon: Braces,
    domainIds: ["software-programming", "theory-mathematics"],
  },
  {
    id: "computer-graphics",
    label: "计算机图形学",
    summary: "渲染管线、几何、光照、动画与实时图形。",
    sampleTopics: ["光线追踪", "着色器", "Bezier 曲线"],
    icon: Palette,
    domainIds: ["software-programming", "hardware-architecture"],
  },
  {
    id: "web-development",
    label: "Web开发",
    summary: "Web 应用、前端框架、后端服务与全栈开发。",
    sampleTopics: ["React 状态管理", "HTTP 缓存", "REST API"],
    icon: Globe2,
    domainIds: ["software-programming", "network-security"],
  },
  {
    id: "data-science",
    label: "数据科学",
    summary: "数据处理、统计建模、可视化与数据分析流程。",
    sampleTopics: ["特征工程", "假设检验", "数据可视化"],
    icon: Database,
    domainIds: ["ai-data", "theory-mathematics"],
  },
  {
    id: "artificial-intelligence",
    label: "人工智能",
    summary: "搜索、规划、知识表示、强化学习与智能体基础。",
    sampleTopics: ["A* 搜索", "马尔可夫决策过程", "约束满足问题"],
    icon: Brain,
    domainIds: ["ai-data", "theory-mathematics"],
  },
  {
    id: "machine-learning",
    label: "机器学习",
    summary: "监督学习、无监督学习、泛化、优化与模型评估。",
    sampleTopics: ["梯度下降", "支持向量机", "交叉验证"],
    icon: Brain,
    domainIds: ["ai-data", "theory-mathematics"],
  },
  {
    id: "machine-learning-systems",
    label: "机器学习系统",
    summary: "训练系统、推理部署、ML 编译与数据系统。",
    sampleTopics: ["模型并行", "MLIR", "推理延迟优化"],
    icon: Boxes,
    domainIds: ["ai-data", "computer-systems"],
  },
  {
    id: "deep-learning",
    label: "深度学习",
    summary: "神经网络、视觉、NLP、图学习与深度强化学习。",
    sampleTopics: ["反向传播", "Transformer", "卷积神经网络"],
    icon: Brain,
    domainIds: ["ai-data"],
  },
  {
    id: "deep-generative-models",
    label: "深度生成模型",
    summary: "扩散模型、大语言模型、生成式 AI 与高级 NLP。",
    sampleTopics: ["扩散模型", "大语言模型注意力机制", "RLHF"],
    icon: Bot,
    domainIds: ["ai-data"],
  },
];

function DirectionPill({
  direction,
  selected,
  onToggle,
}: {
  direction: SubjectDirection;
  selected: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onToggle(direction.id)}
      className={`cursor-pointer rounded-full border px-3 py-1.5 text-xs font-medium transition focus:ring-2 focus:ring-slate-900/20 focus:outline-none ${
        selected
          ? "border-slate-900 bg-slate-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-500"
      }`}
    >
      {direction.label}
    </button>
  );
}

function SelectedDirectionPills({
  selectedDirectionIds,
  onRemove,
}: {
  selectedDirectionIds: Set<string>;
  onRemove: (id: string) => void;
}) {
  const selectedDirections = SUBJECT_DIRECTIONS.filter((direction) =>
    selectedDirectionIds.has(direction.id),
  );

  if (selectedDirections.length === 0) return null;

  return (
    <div className="mt-3" aria-label="已选探索方向">
      <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">
        已选方向
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {selectedDirections.map((direction) => (
          <button
            key={direction.id}
            type="button"
            onClick={() => onRemove(direction.id)}
            aria-label={`取消方向：${direction.label}`}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-800 transition hover:border-slate-500 hover:bg-slate-200 focus:ring-2 focus:ring-slate-900/20 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:border-zinc-500 dark:hover:bg-zinc-700"
          >
            <span>{direction.label}</span>
            <X className="h-3.5 w-3.5" aria-hidden="true" strokeWidth={1.9} />
          </button>
        ))}
      </div>
    </div>
  );
}

function DirectionExplorer({
  activeDomainId,
  selectedDirectionIds,
  onDomainChange,
  onToggleDirection,
  onPickTopic,
}: {
  activeDomainId: string;
  selectedDirectionIds: Set<string>;
  onDomainChange: (id: string) => void;
  onToggleDirection: (id: string) => void;
  onPickTopic: (topic: string) => void;
}) {
  const visibleDirections = SUBJECT_DIRECTIONS.filter((direction) =>
    direction.domainIds.includes(activeDomainId),
  );
  const topicDirections = selectedDirectionIds.size > 0
    ? SUBJECT_DIRECTIONS.filter((direction) => selectedDirectionIds.has(direction.id))
    : visibleDirections;
  const suggestions = [...new Set(topicDirections.flatMap((direction) => direction.sampleTopics))].slice(0, 6);

  return (
    <section aria-labelledby="direction-explorer-title" className="app-card rounded-2xl p-5 sm:p-6">
      <div>
        <h2 id="direction-explorer-title" className="text-lg font-bold text-slate-950 dark:text-zinc-50">
          探索计算机方向
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">
          选择领域和方向来筛选建议；已选方向会显示在上方输入框下方。
        </p>
      </div>

      <div aria-label="计算机领域" className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {COMPUTER_DOMAINS.map((domain) => {
          const active = domain.id === activeDomainId;
          return (
            <button
              key={domain.id}
              type="button"
              aria-pressed={active}
              onClick={() => onDomainChange(domain.id)}
              className={`cursor-pointer rounded-lg border px-3 py-2.5 text-left text-sm font-semibold transition focus:ring-2 focus:ring-slate-900/20 focus:outline-none ${
                active
                  ? "border-slate-900 bg-slate-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                  : "border-slate-200 bg-white text-slate-700 hover:border-slate-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-500"
              }`}
            >
              {domain.label}
            </button>
          );
        })}
      </div>

      <div className="mt-4">
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">
          可多选方向
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {visibleDirections.map((direction) => (
            <DirectionPill
              key={direction.id}
              direction={direction}
              selected={selectedDirectionIds.has(direction.id)}
              onToggle={onToggleDirection}
            />
          ))}
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-4 dark:border-zinc-800">
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">
            主题建议
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {suggestions.map((topic) => (
              <button
                key={topic}
                type="button"
                onClick={() => onPickTopic(topic)}
                className="cursor-pointer rounded-md bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-200 focus:ring-2 focus:ring-slate-900/20 focus:outline-none dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
              >
                {topic}
              </button>
            ))}
          </div>
        </div>
      )}

    </section>
  );
}

function RecentLearningSection({
  items,
  loading,
  error,
  onRestore,
}: {
  items: RecentLearningItem[];
  loading: boolean;
  error: string | null;
  onRestore: (item: RecentLearningItem) => void;
}) {
  return (
    <section aria-labelledby="recent-learning-title" className="app-card rounded-2xl p-5 sm:p-6">
      <h2 id="recent-learning-title" className="text-lg font-bold text-slate-950 dark:text-zinc-50">
        继续最近学习
      </h2>
      {loading && (
        <div role="status" aria-live="polite" className="mt-4 space-y-2">
          <SkeletonLine width="w-3/5" />
          <SkeletonLine width="w-2/5" />
        </div>
      )}
      {!loading && error && (
        <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">
          最近学习暂时无法加载。{error}
        </p>
      )}
      {!loading && !error && items.length === 0 && (
        <p className="mt-3 text-sm text-slate-600 dark:text-zinc-400">
          还没有可恢复的学习记录。从上方输入一个问题开始吧。
        </p>
      )}
      {!loading && !error && items.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={item.status !== "available"}
              onClick={() => onRestore(item)}
              className="cursor-pointer rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-slate-400 hover:bg-slate-50 focus:ring-2 focus:ring-slate-900/20 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500 dark:hover:bg-zinc-800"
            >
              <p className="truncate text-sm font-semibold text-slate-900 dark:text-zinc-100">{item.knowledge_point}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
                {item.status === "available" ? "恢复已保存的讲解" : "原学习资料已不可访问"}
              </p>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Depth-analysis card. The top-right CTA lets the student turn the explanation
 * into a companion PPT deck without retyping the concept.
 */
function ExplanationCard({
  data,
  onGeneratePpt,
  generatingPpt,
  onGenerateQuiz,
}: {
  data: ExplainResponse;
  onGeneratePpt: () => void;
  generatingPpt?: boolean;
  onGenerateQuiz: () => void;
}) {
  return (
    <section className="app-card rounded-2xl p-7 transition-all">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <h2 className="min-w-0 flex-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-zinc-100">
          {data.knowledge_point}
        </h2>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onGeneratePpt}
            disabled={generatingPpt}
            className="app-button-primary inline-flex cursor-pointer items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition hover:bg-slate-800 active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-200"
          >
            {generatingPpt ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
            ) : (
              <Presentation className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            {generatingPpt ? "正在生成配套 PPT…" : "一键生成配套 PPT 课件"}
          </button>
          <button
            type="button"
            onClick={onGenerateQuiz}
            className="app-button-secondary inline-flex cursor-pointer items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition hover:bg-slate-50 active:scale-98 dark:hover:bg-zinc-800"
          >
            <FileQuestion className="h-3.5 w-3.5" strokeWidth={1.5} />
            生成配套练习题
          </button>
        </div>
      </div>

      {/* Summary block */}
      <div className="app-card-subtle mb-5 rounded-xl p-5">
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
            <Sparkles className="h-3 w-3" strokeWidth={1.5} />
            核心概念提炼
          </span>
        </div>
        <p className="text-sm leading-relaxed text-slate-800 dark:text-zinc-200">{data.summary}</p>
      </div>

      {/* Detail block (optional) */}
      {data.detail && (
        <div className="app-card-subtle mb-5 rounded-xl p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
              <GraduationCap className="h-3 w-3" strokeWidth={1.5} />
              原理解析与应用场景
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-slate-800 dark:text-zinc-200">
            {data.detail}
          </p>
        </div>
      )}

      {/* Citations */}
      {data.citations.length > 0 && (
        <div className="mt-7 pt-4 border-t border-slate-100 dark:border-zinc-800/60">
          <div className="mb-3.5 flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-slate-400" strokeWidth={1.5} />
            <h3 className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-zinc-400">
              权威文献与引用来源
            </h3>
          </div>
          <ul className="space-y-2.5">
            {data.citations.map((cit, i) => (
              <li
                key={`${cit.source_title}-${i}`}
                className="app-card-subtle rounded-xl p-4 text-xs"
              >
                <p className="font-semibold text-slate-900 dark:text-zinc-200">{cit.source_title}</p>
                {cit.snippet && (
                  <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 italic text-slate-600 dark:border-zinc-700 dark:text-zinc-400">
                    &ldquo;{cit.snippet}&rdquo;
                  </blockquote>
                )}
                {cit.uri && (
                  <a
                    href={cit.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 transition hover:text-slate-900 underline decoration-slate-300 hover:decoration-slate-600 dark:text-zinc-300 dark:hover:text-white dark:decoration-zinc-700"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0 text-slate-400" strokeWidth={1.5} />
                    <span className="truncate">{cit.uri}</span>
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

type ResultView = "text" | "ppt" | "quiz";

// ── Page component ─────────────────────────────────────────────────────────────

export default function LearningPage(): JSX.Element {
  const savedSnapshot = useLearningStore((s) => s);
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace_id");
  const taskId = searchParams.get("task_id");

  // Explain state (the single source of truth for the concept under study)
  const [query, setQuery] = useState(savedSnapshot?.query ?? "");
  const [activeDomainId, setActiveDomainId] = useState(COMPUTER_DOMAINS[0].id);
  const [selectedDirectionIds, setSelectedDirectionIds] = useState<Set<string>>(() => new Set());
  const [recentLearning, setRecentLearning] = useState<RecentLearningItem[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExplainResponse | null>(
    (savedSnapshot?.result as ExplainResponse) ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ResultView>(savedSnapshot?.view ?? "text");

  // PPT state — restored from the snapshot so the deck survives a route switch.
  const [outlines, setOutlines] = useState<SceneOutline[]>(
    savedSnapshot?.outlines ?? [],
  );
  const [slides, setSlides] = useState<Slide[]>(savedSnapshot?.slides ?? []);
  const [pptGenerating, setPptGenerating] = useState(false);
  const [pptError, setPptError] = useState<string | null>(null);
  const [currentIndex, setCurrentIndex] = useState(
    savedSnapshot?.currentIndex ?? 0,
  );
  const [exporting, setExporting] = useState(false);
  const [pptGenerationMode, setPptGenerationMode] = useState<PresentationGenerationMode | undefined>(
    savedSnapshot?.presentationGenerationMode,
  );
  const [pptProviderName, setPptProviderName] = useState<string | undefined>(
    savedSnapshot?.presentationProviderName,
  );

  // Quiz (配套练习题) state — restored from the snapshot so the third view and
  // any already-generated paper survive a route switch.
  const [quizParams, setQuizParams] = useState<QuizGenerateParams>(
    savedSnapshot?.quizParams ?? DEFAULT_QUIZ_PARAMS,
  );
  const [quizResponse, setQuizResponse] = useState<QuizGenerateResponse | null>(
    savedSnapshot?.quizResponse ?? null,
  );
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);
  const [quizExporting, setQuizExporting] = useState(false);

  // Track whether the user is "following" the newest generated page so new
  // pages auto-advance, while manual navigation to earlier pages is respected.
  const generatedCountRef = useRef(0);
  const currentIndexRef = useRef(0);
  useEffect(() => {
    currentIndexRef.current = currentIndex;
  }, [currentIndex]);

  // Empty during server rendering, real id after hydration.
  const sessionId = useLearningSessionId();
  const activeSessionId = result?.session_id || sessionId;

  // Persist the full learning state (explain result + PPT deck + quiz paper +
  // active view) so a route switch away and back restores everything, not just
  // the text.
  useEffect(() => {
    if (
      result ||
      query ||
      slides.length > 0 ||
      outlines.length > 0 ||
      quizResponse
    ) {
      setLearningSnapshot({
        query,
        result,
        view,
        outlines,
        slides,
        currentIndex,
        presentationGenerationMode: pptGenerationMode,
        presentationProviderName: pptProviderName,
        quizParams,
        quizResponse,
      });
    }
  }, [query, result, view, outlines, slides, currentIndex, pptGenerationMode, pptProviderName, quizParams, quizResponse]);

  const [notebookOpen, setNotebookOpen] = useState(false);
  const [notebookInitialTab, setNotebookInitialTab] = useState<"summary" | "research_note">("summary");

  useEffect(() => {
    if (window.location.hash === "#research-notes") {
      queueMicrotask(() => {
        setNotebookInitialTab("research_note");
        setNotebookOpen(true);
      });
    }
  }, []);

  useEffect(() => {
    let active = true;
    const profileId = getLocalProfileId();
    void listRecentLearning(profileId)
      .then((items) => {
        if (active) setRecentLearning(items);
      })
      .catch((reason: unknown) => {
        if (active) {
          setRecentError(reason instanceof Error ? reason.message : String(reason));
        }
      })
      .finally(() => {
        if (active) setRecentLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    if (trimmed.length > MAX_LEARNING_INPUT_CHARS) {
      setError(`材料最多支持 ${MAX_LEARNING_INPUT_CHARS.toLocaleString()} 个字符。请保留需要理解的片段后再提交。`);
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setView("text");
    // A fresh concept supersedes any previous deck.
    setOutlines([]);
    setSlides([]);
    setPptError(null);
    setPptGenerationMode(undefined);
    setPptProviderName(undefined);

    try {
      const data = await explainKnowledgePoint({
        knowledge_point: trimmed,
        local_profile_id: getLocalProfileId(),
        workspace_id: workspaceId ?? undefined,
        task_id: taskId ?? undefined,
      });
      setResult(data);
      setRecentLearning((items) => [
        {
          id: data.notebook_item_id ?? `current-${data.session_id}`,
          knowledge_point: data.knowledge_point,
          session_id: data.session_id,
          notebook_item_id: data.notebook_item_id,
          summary: data.summary,
          detail: data.detail,
          citations: data.citations,
          created_at: new Date().toISOString(),
          status: "available" as const,
        },
        ...items.filter((item) => item.notebook_item_id !== data.notebook_item_id),
      ].slice(0, 4));
    } catch (err) {
      setError(
        err instanceof LearningApiError ? err.message : String(err),
      );
    } finally {
      setLoading(false);
    }
  }

  function toggleDirection(directionId: string) {
    setSelectedDirectionIds((current) => {
      const next = new Set(current);
      if (next.has(directionId)) next.delete(directionId);
      else next.add(directionId);
      return next;
    });
  }

  async function restoreRecentLearning(item: RecentLearningItem) {
    if (item.status !== "available") return;
    try {
      const source = await getRecentLearning(item.id, getLocalProfileId());
      if (source.status !== "available" || !source.session_id || !source.summary) {
        setRecentLearning((items) => items.map((entry) => entry.id === item.id ? source : entry));
        setError("该学习资料已不可访问，请从输入框重新开始学习。");
        return;
      }
      setLearningSessionId(source.session_id);
      setQuery(source.knowledge_point);
      setResult({
        knowledge_point: source.knowledge_point,
        session_id: source.session_id,
        notebook_item_id: source.notebook_item_id,
        summary: source.summary,
        detail: source.detail,
        citations: source.citations,
      });
      setError(null);
      setView("text");
    } catch (reason) {
      setError(reason instanceof Error ? `恢复最近学习失败：${reason.message}` : "恢复最近学习失败。");
    }
  }

  async function handleGeneratePpt() {
    const trimmed = query.trim();
    if (!trimmed) return;

    setPptGenerating(true);
    setPptError(null);
    setOutlines([]);
    setSlides([]);
    setPptGenerationMode(undefined);
    setPptProviderName(undefined);
    setCurrentIndex(0);
    generatedCountRef.current = 0;
    currentIndexRef.current = 0;
    setView("ppt");

    // Carry the depth-analysis result as grounding context for the deck.
    const context = result
      ? [result.summary, result.detail ?? ""].filter(Boolean).join("\n\n")
      : null;

    try {
      for await (const event of streamPresentation({
        knowledge_point: trimmed,
        session_id: activeSessionId,
        context,
      })) {
        if (event.type === "outlines") {
          setOutlines(event.data);
          setPptGenerationMode(event.generation_mode);
          setPptProviderName(event.provider_name);
        } else if (event.type === "slide") {
          // Before this page arrived, the trailing "pending" position was
          // ``generatedCount``; if the user is parked there, follow it.
          const pending = generatedCountRef.current;
          setSlides((prev) => {
            const next = [...prev];
            next[event.index] = event.data;
            return next;
          });
          generatedCountRef.current = event.index + 1;
          if (currentIndexRef.current >= pending) {
            setCurrentIndex(event.index);
          }
          setPptGenerationMode((current) => current === event.generation_mode ? current : "mixed");
          setPptProviderName(event.provider_name);
        } else if (event.type === "done") {
          setPptGenerationMode(event.presentation.generation_mode);
          setPptProviderName(event.presentation.provider_name);
        } else if (event.type === "error") {
          setPptError(`${event.error.message}（错误编号：${event.error.error_id}）`);
        }
      }
    } catch (err) {
      setPptError(err instanceof Error ? err.message : String(err));
    } finally {
      setPptGenerating(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await exportSlidesToPptx(query.trim() || "presentation", slides);
    } catch (err) {
      setPptError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(false);
    }
  }

  /**
   * Generate a companion exercise set for the current concept and switch to the
   * 配套练习题 view. This stays on the learning page — the quiz module is a
   * third view of this page, not a route into another module.
   */
  async function handleGenerateQuiz() {
    const knowledgePoint = (result?.knowledge_point || query).trim();
    if (!knowledgePoint) return;

    setView("quiz");
    setQuizLoading(true);
    setQuizError(null);
    try {
      const data = await generateQuiz({
        knowledge_point: knowledgePoint,
        session_id: activeSessionId,
        ...quizParams,
      });
      setQuizResponse(data);
    } catch (err) {
      setQuizError(
        err instanceof Error ? err.message : String(err),
      );
    } finally {
      setQuizLoading(false);
    }
  }

  /** Download the latest generated paper as a Word exam (.docx). */
  async function handleExportQuiz(withAnswer: boolean) {
    if (!quizResponse) return;
    setQuizExporting(true);
    setQuizError(null);
    try {
      await exportQuizDocx({
        quizId: quizResponse.quiz_id,
        sessionId: quizResponse.session_id,
        withAnswer,
      });
    } catch (err) {
      setQuizError(
        err instanceof Error ? err.message : String(err),
      );
    } finally {
      setQuizExporting(false);
    }
  }

  const hasPptContent = slides.length > 0 || pptGenerating;

  return (
    <div className="mx-auto min-w-0 max-w-7xl px-4 py-5 sm:py-8">
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => setNotebookOpen(true)}
          className="app-button-secondary flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-slate-50 hover:text-slate-900 dark:hover:bg-zinc-800 dark:hover:text-white"
        >
          <BookOpen className="h-3.5 w-3.5 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
          学习笔记
        </button>
      </div>

      <main className="space-y-6">
        <section aria-labelledby="learning-start-title" className="app-card rounded-2xl p-5 sm:p-7">
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-flex rounded-full bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
              <Sparkles className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <div>
              <h1 id="learning-start-title" className="text-2xl font-bold tracking-tight text-slate-950 dark:text-zinc-50">
                今天想理解什么？
              </h1>
              <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">
                直接输入概念、问题或一段材料，方向选择不是开始学习的前置条件。
              </p>
            </div>
          </div>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5 sm:flex-row">
            <div className="relative flex-1">
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索概念、问题或粘贴一段材料……"
                aria-label="搜索概念、问题或粘贴一段材料"
                rows={3}
                disabled={loading}
                className="app-input w-full resize-y rounded-xl px-4 py-3 text-sm shadow-sm placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:placeholder:text-zinc-500 dark:focus:ring-zinc-800"
              />
              <p className="mt-1 text-right text-xs text-slate-500 dark:text-zinc-400">
                {query.length.toLocaleString()} / {MAX_LEARNING_INPUT_CHARS.toLocaleString()}
              </p>
            </div>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="app-button-primary flex cursor-pointer items-center justify-center gap-2 self-start rounded-xl px-6 py-3.5 text-sm font-medium shadow-sm transition hover:bg-slate-800 focus:ring-2 focus:ring-slate-900/20 focus:outline-none active:scale-98 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-zinc-200"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} /> : <Search className="h-4 w-4" strokeWidth={1.5} />}
              {loading ? "正在解析…" : "开始学习"}
            </button>
          </form>
          <SelectedDirectionPills
            selectedDirectionIds={selectedDirectionIds}
            onRemove={toggleDirection}
          />
        </section>

        <RecentLearningSection
          items={recentLearning}
          loading={recentLoading}
          error={recentError}
          onRestore={restoreRecentLearning}
        />

        <DirectionExplorer
          activeDomainId={activeDomainId}
          selectedDirectionIds={selectedDirectionIds}
          onDomainChange={setActiveDomainId}
          onToggleDirection={toggleDirection}
          onPickTopic={setQuery}
        />

      {/* Loading */}
      {loading && (
        <div role="status" aria-live="polite" className="app-card space-y-4 rounded-2xl p-7">
          <SkeletonLine width="w-2/5" />
          <SkeletonLine />
          <SkeletonLine width="w-4/5" />
          <SkeletonLine width="w-3/5" />
        </div>
      )}

      {/* Error */}
      {error && (
        <div role="alert" className="app-status-error flex items-start gap-3 rounded-xl p-4 text-xs">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div>
            <p className="font-semibold">请求响应异常</p>
            <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{error}</p>
          </div>
        </div>
      )}

      {/* PPT error */}
      {pptError && (
        <div role="alert" className="app-status-error mb-6 flex items-start gap-3 rounded-xl p-4 text-xs">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div>
            <p className="font-semibold">PPT 生成异常</p>
            <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{pptError}</p>
          </div>
        </div>
      )}

      {/* Result area: unified 深度解析 ↔ PPT 演示课件 */}
      {result && (
        <div>
          {/* View switcher */}
          <div className="mb-4 max-w-full overflow-x-auto rounded-xl border border-slate-200/50 bg-slate-100/90 p-1 dark:border-zinc-700/40 dark:bg-zinc-800/80">
            <div className="flex min-w-max">
            <button
              type="button"
              onClick={() => setView("text")}
              className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-all ${
                view === "text"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <BookOpen className="h-3.5 w-3.5" strokeWidth={1.5} />
              结构化文本
            </button>
            <button
              type="button"
              onClick={() => setView("ppt")}
              className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-all ${
                view === "ppt"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <Presentation className="h-3.5 w-3.5" strokeWidth={1.5} />
              PPT 演示课件
            </button>
            <button
              type="button"
              onClick={() => setView("quiz")}
              className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-all ${
                view === "quiz"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <FileQuestion className="h-3.5 w-3.5" strokeWidth={1.5} />
              配套练习题
            </button>
            </div>
          </div>

          {view === "text" ? (
            <ExplanationCard
              data={result}
              onGeneratePpt={handleGeneratePpt}
              generatingPpt={pptGenerating}
              onGenerateQuiz={() => void handleGenerateQuiz()}
            />
          ) : view === "quiz" ? (
            <QuizView
              key={quizResponse?.quiz_id ?? "empty"}
              knowledgePoint={result?.knowledge_point || query}
              sessionId={activeSessionId}
              params={quizParams}
              onParamsChange={setQuizParams}
              response={quizResponse}
              loading={quizLoading}
              error={quizError}
              onGenerate={() => void handleGenerateQuiz()}
              onExport={(withAnswer) => void handleExportQuiz(withAnswer)}
              exporting={quizExporting}
            />
          ) : (
            <div>
              {hasPptContent && outlines.length > 0 ? (
                <SlideViewer
                  knowledgePoint={query}
                  outlines={outlines}
                  slides={slides}
                  generating={pptGenerating}
                  currentIndex={currentIndex}
                  onNavigate={setCurrentIndex}
                  onExport={slides.length > 0 ? handleExport : undefined}
                  exporting={exporting}
                  generationMode={pptGenerationMode}
                  providerName={pptProviderName}
                  onGenerateQuiz={() => void handleGenerateQuiz()}
                />
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-200 py-16 text-center text-slate-400 dark:border-zinc-800 dark:text-zinc-500">
                  {pptGenerating ? (
                    <>
                      <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
                      <p className="text-xs font-medium">正在生成讲解 PPT…</p>
                    </>
                  ) : (
                    <>
                      <Presentation className="mx-auto mb-3 h-8 w-8 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
                      <p className="text-xs font-medium">
                        尚未生成 PPT。切换到「结构化文本」，点击右上角
                        「一键生成配套 PPT 课件」即可。
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
          <DownstreamGoCard
            knowledgePoint={result.knowledge_point || query || "DHCP 四阶段报文交互"}
            knowledgePointId={buildKnowledgeId(query || result.knowledge_point || "DHCP 四阶段报文交互")}
            sessionId={activeSessionId}
            notebookItemId={result.notebook_item_id ?? undefined}
            onOpenResearch={() => {
              setNotebookInitialTab("summary");
              setNotebookOpen(true);
            }}
          />
        </div>
      )}

      </main>

      {/* Floating text-selection popover — works on the whole page */}
      <TextSelectionPopover />

      {/* Side-Drawer Notebook */}
      <StructuredNotebook
        key={notebookInitialTab}
        open={notebookOpen}
        onDismiss={() => setNotebookOpen(false)}
        sessionId={activeSessionId}
        initialTab={notebookInitialTab}
      />
    </div>
  );
}
