"use client";

import {
  Bot,
  BrainCircuit,
  ChevronDown,
  CircleAlert,
  Clock3,
  Loader2,
  MessageSquareText,
  Plus,
  RotateCcw,
  Route,
  SearchCheck,
  Send,
  Sparkles,
  UserRound,
} from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  analyzeResearchPaper,
  analyzeResearchPaperUpload,
  createResearchConversation,
  generateResearchPlan,
  getResearchConversation,
  type ResearchMindMap,
  RESEARCH_CONVERSATION_STORAGE_KEY,
  ResearchApiError,
  type ResearchConversationMessage,
  type ResearchConversationResponse,
  type PaperAnalysis,
  type SelectedResearchPaper as PersistedSelectedResearchPaper,
  sendResearchMessage,
} from "@/lib/api/research";

import { MarkdownText } from "./MarkdownText";
import { AcademicSearchPanel } from "./AcademicSearchPanel";
import { ProviderStatusCard } from "./ProviderStatusCard";
import { ResearchProfilePanel } from "./ResearchProfilePanel";
import { ResearchPlanPanel } from "./ResearchPlanPanel";
import { ResearchMindMapPanel } from "./ResearchMindMapPanel";
import { ResearchDifficultyPanel } from "./ResearchDifficultyPanel";
import { ExperimentDesignPanel } from "./ExperimentDesignPanel";
import { ExperimentEvidencePanel } from "./ExperimentEvidencePanel";
import { ReproductionPipelinePanel } from "./ReproductionPipelinePanel";
import { PaperDraftReviewPanel } from "./PaperDraftReviewPanel";
import { ReproductionEvaluationPanel } from "./ReproductionEvaluationPanel";
import { ResearchWorkflowNav } from "./ResearchWorkflowNav";
import { PaperDeepAnalysisPanel, type SelectedResearchPaper } from "./PaperDeepAnalysisPanel";

const LEGACY_STORAGE_KEY = "code-navi.research.session-id";

type RequestPhase = "initializing" | "idle" | "thinking";

const GENERATION_LABELS = {
  agent: "Agent 个性化分析",
  rules: "基础规则（非模型）",
  rules_fallback: "模型未生成（需重试）",
};

function messageContent(message: ResearchConversationMessage): string {
  if (message.role === "assistant" && message.generation_mode === "rules_fallback") {
    return "本次模型未生成科研回复，系统未展示规则替代内容。请重试。";
  }
  return message.content;
}

function restoreSelectedPaper(paper: PersistedSelectedResearchPaper): SelectedResearchPaper {
  return {
    bundleId: paper.bundle_id,
    title: paper.title,
    url: paper.url,
    authors: paper.authors,
    year: paper.year,
    sourceName: paper.source_name,
    doi: paper.doi,
    arxivId: paper.arxiv_id,
    abstractExcerpt: paper.abstract_excerpt,
    paperKind: paper.paper_kind,
    abstractAvailable: paper.abstract_available,
  };
}

function friendlyError(error: unknown): string {
  if (error instanceof ResearchApiError) {
    if (error.status === 0) return error.message;
    if (error.status === 404) return "这段科研会话已不存在，可以新建会话后继续。";
    if (error.status === 422) return `发送内容未通过校验：${error.message}`;
    return `科研服务返回 HTTP ${error.status}：${error.message}`;
  }
  return error instanceof Error ? error.message : "发生了未知错误，请重试。";
}

function ProcessingDetails({ message }: { message: ResearchConversationMessage }) {
  if (message.role !== "assistant" || !message.generation_mode) return null;
  return (
    <details className="group mt-3 rounded-xl border border-slate-200/80 bg-slate-50/70 text-xs dark:border-zinc-800 dark:bg-zinc-900/60">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-slate-500 dark:text-zinc-400">
        <span className="flex items-center gap-2 font-medium">
          <BrainCircuit className="h-3.5 w-3.5" /> 本轮处理过程
        </span>
        <ChevronDown className="h-3.5 w-3.5 transition group-open:rotate-180" />
      </summary>
      <div className="space-y-2 border-t border-slate-200/80 px-3 py-3 text-sm leading-6 text-slate-600 dark:border-zinc-800 dark:text-zinc-400">
        <p>
          生成方式：
          <span className="font-semibold text-slate-800 dark:text-zinc-200">
            {GENERATION_LABELS[message.generation_mode]}
          </span>
        </p>
        {message.intent && <p>识别意图：{message.intent}</p>}
        {message.generation_mode === "agent" ? (
          <p>本轮已经过 Kernel AgentRuntime；记录了 {message.event_count} 个审计事件。</p>
        ) : message.generation_mode === "rules_fallback" ? (
          <p>模型生成失败，本轮未展示规则替代内容；可以重试本轮消息。</p>
        ) : (
          <p>本轮没有访问模型或网络，使用确定性规则整理用户明确表达的信息。</p>
        )}
        {message.run_id && <p className="break-all font-mono">Run ID：{message.run_id}</p>}
        <p>这里展示的是可审计处理摘要，不展示或伪造模型内部思维链。</p>
      </div>
    </details>
  );
}

function MessageItem({ message }: { message: ResearchConversationMessage }) {
  const isUser = message.role === "user";
  return (
    <article className={`flex min-w-0 gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-950">
          <Sparkles className="h-4 w-4" />
        </div>
      )}
      <div className={isUser ? "min-w-0 max-w-[86%] sm:max-w-[76%]" : "min-w-0 flex-1"}>
        <div
          className={
            isUser
              ? "rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-sm leading-7 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900"
              : "px-1 py-1 text-slate-800 dark:text-zinc-200"
          }
        >
          {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MarkdownText content={messageContent(message)} />}
        </div>
        {!isUser && message.next_question && (
          <div className="app-card-subtle mt-3 break-words rounded-xl px-4 py-3 text-sm font-medium leading-6 text-slate-800 dark:text-zinc-200">
            {message.next_question}
          </div>
        )}
        <ProcessingDetails message={message} />
      </div>
      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          <UserRound className="h-4 w-4" />
        </div>
      )}
    </article>
  );
}

function ThinkingMessage() {
  return (
    <div className="flex gap-3" role="status" aria-live="polite">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
        <span className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-slate-500 dark:text-zinc-400" />
          正在理解并整理研究画像
        </span>
        <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">分析本轮信息、更新候选问题与下一步建议…</p>
      </div>
    </div>
  );
}

type WorkflowPanelState = "current" | "completed" | "upcoming" | "supplementary";

function panelState(currentStage: number, panelStage: number): WorkflowPanelState {
  if (currentStage === panelStage) return "current";
  return currentStage > panelStage ? "completed" : "upcoming";
}

function PanelSection({
  id,
  title,
  description,
  children,
  state = "supplementary",
}: {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
  state?: WorkflowPanelState;
}) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);

  useEffect(() => {
    if (detailsRef.current) detailsRef.current.open = state === "current";
  }, [state]);

  return (
    <details
      ref={detailsRef}
      id={id}
      className="app-card group scroll-mt-20 rounded-2xl"
    >
      <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <span className="min-w-0">
          <span className="block text-xl font-bold text-slate-900 dark:text-zinc-100">{title}</span>
          {state === "completed" && <span className="mt-1 block text-sm leading-6 text-emerald-700 dark:text-emerald-300">已完成阶段摘要：可展开查看已保存内容。</span>}
          {state === "upcoming" && <span className="mt-1 block text-sm leading-6 text-slate-500 dark:text-zinc-400">未开始：完成前一阶段后可用。</span>}
          {state !== "upcoming" && state !== "completed" && <span className="mt-1 block text-sm leading-6 text-slate-600 dark:text-zinc-300">{description}</span>}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-200 p-5 sm:p-6 dark:border-zinc-800">{children}</div>
    </details>
  );
}

export function ResearchConversation() {
  const [searchPanelMounted, setSearchPanelMounted] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(false);
  const [evidenceVersion, setEvidenceVersion] = useState(0);
  const [workflowStage, setWorkflowStage] = useState(0);
  const [selectedPaperTitle, setSelectedPaperTitle] = useState<string | null>(null);
  const [selectedPaper, setSelectedPaper] = useState<SelectedResearchPaper | null>(null);
  const [paperAnalysis, setPaperAnalysis] = useState<PaperAnalysis | null>(null);
  const [paperAnalysisError, setPaperAnalysisError] = useState<string | null>(null);
  const [paperAnalysisLoading, setPaperAnalysisLoading] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ResearchConversationResponse | null>(null);
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState<RequestPhase>("initializing");
  const [error, setError] = useState<string | null>(null);
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  const startedRef = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const restoreOrCreate = useCallback(async () => {
    setPhase("initializing");
    setError(null);
    setFailedMessage(null);
    try {
      const savedId = window.localStorage.getItem(RESEARCH_CONVERSATION_STORAGE_KEY);
      if (savedId) {
        try {
          const restored = await getResearchConversation(savedId);
          setConversation(restored);
          if (restored.selected_paper) {
            setSelectedPaper(restoreSelectedPaper(restored.selected_paper));
            setSelectedPaperTitle(restored.selected_paper.title);
          }
          setPaperAnalysis(restored.paper_analysis);
          setWorkflowStage(restored.recommended_action === "prepare_search" ? 1 : 0);
          return;
        } catch (requestError) {
          if (!(requestError instanceof ResearchApiError) || requestError.status !== 404) {
            throw requestError;
          }
          window.localStorage.removeItem(RESEARCH_CONVERSATION_STORAGE_KEY);
        }
      }
      const created = await createResearchConversation();
      window.localStorage.setItem(
        RESEARCH_CONVERSATION_STORAGE_KEY,
        created.conversation_id,
      );
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
      setConversation(created);
      setPaperAnalysis(created.paper_analysis);
      setWorkflowStage(created.recommended_action === "prepare_search" ? 1 : 0);
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setPhase("idle");
    }
  }, []);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void restoreOrCreate();
  }, [restoreOrCreate]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversation?.messages.length, phase]);

  const refreshDownstream = useCallback((stage: number) => {
    setEvidenceVersion((current) => current + 1);
    setWorkflowStage(stage);
  }, []);

  const analyzeSelectedPaper = useCallback(async (paper: SelectedResearchPaper, paperPdfUrl?: string) => {
    if (!conversation) return;
    setSelectedPaper(paper);
    setSelectedPaperTitle(paper.title);
    setWorkflowStage(2);
    setPaperAnalysisError(null);
    setPaperAnalysisLoading(true);
    try {
      setPaperAnalysis(await analyzeResearchPaper(conversation.conversation_id, paper.url, paperPdfUrl));
    } catch (requestError) {
      setPaperAnalysisError(friendlyError(requestError));
    } finally {
      setPaperAnalysisLoading(false);
    }
  }, [conversation]);

  const uploadSelectedPaper = useCallback(async (paper: SelectedResearchPaper, file: File) => {
    if (!conversation) return;
    setSelectedPaper(paper);
    setSelectedPaperTitle(paper.title);
    setWorkflowStage(2);
    setPaperAnalysisError(null);
    setPaperAnalysisLoading(true);
    try {
      setPaperAnalysis(await analyzeResearchPaperUpload(conversation.conversation_id, paper.url, file));
    } catch (requestError) {
      setPaperAnalysisError(friendlyError(requestError));
    } finally {
      setPaperAnalysisLoading(false);
    }
  }, [conversation]);

  async function send(message: string) {
    const cleaned = message.trim();
    if (!conversation || !cleaned || phase !== "idle") return;
    setPhase("thinking");
    setError(null);
    setFailedMessage(null);
    try {
      const updated = await sendResearchMessage(conversation.conversation_id, cleaned);
      setConversation(updated);
      setWorkflowStage(updated.recommended_action === "prepare_search" ? 1 : 0);
      setDraft("");
    } catch (requestError) {
      setError(friendlyError(requestError));
      setFailedMessage(cleaned);
      setDraft((current) => current || cleaned);
    } finally {
      setPhase("idle");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(draft);
    }
  }

  async function startNewConversation() {
    if (conversation && conversation.messages.length > 2) {
      const confirmed = window.confirm("新建会话后，当前记录仍保留在服务端，但页面会切换到新对话。继续吗？");
      if (!confirmed) return;
    }
    setPhase("initializing");
    setError(null);
    setFailedMessage(null);
    setConversation(null);
    setDraft("");
    try {
      const created = await createResearchConversation();
      window.localStorage.setItem(
        RESEARCH_CONVERSATION_STORAGE_KEY,
        created.conversation_id,
      );
      setConversation(created);
      setEvidenceVersion(0);
      setSelectedPaperTitle(null);
      setSelectedPaper(null);
      setPaperAnalysis(null);
      setPaperAnalysisError(null);
      setWorkflowStage(0);
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setPhase("idle");
    }
  }

  async function generatePlan() {
    if (!conversation || planLoading) return;
    setPlanLoading(true);
    setPlanError(null);
    try {
      const plan = await generateResearchPlan(conversation.conversation_id);
      setConversation((current) => (current ? { ...current, research_plan: plan } : current));
      setWorkflowStage(1);
    } catch (requestError) {
      setPlanError(friendlyError(requestError));
    } finally {
      setPlanLoading(false);
    }
  }

  if (phase === "initializing" && !conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] px-4">
        <div role="status" aria-live="polite" className="text-center text-slate-500 dark:text-zinc-400">
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-500 dark:text-zinc-400" />
          <p className="mt-3 text-sm font-medium">正在连接并恢复科研会话…</p>
          <p className="mt-1 text-xs">只恢复已保存记录，不会重复调用 Agent。</p>
        </div>
      </main>
    );
  }

  if (!conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] px-4">
        <div role="alert" className="app-card w-full max-w-md rounded-2xl p-6 text-center">
          <CircleAlert className="mx-auto h-7 w-7 text-rose-500" />
          <h1 className="mt-3 text-base font-bold text-slate-900 dark:text-zinc-100">科研会话暂时无法连接</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">{error}</p>
          <button
            type="button"
            onClick={() => void restoreOrCreate()}
            className="app-button-primary mt-4 inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium"
          >
            <RotateCcw className="h-4 w-4" /> 重新连接
          </button>
        </div>
      </main>
    );
  }

  const disabled = phase !== "idle";
  const latestAssistant = [...conversation.messages].reverse().find((message) => message.role === "assistant");

  return (
    <main className="min-h-screen bg-[var(--app-surface)] text-slate-900 dark:text-zinc-100">
      <div className="mx-auto w-full max-w-[1280px] overflow-x-hidden px-4 py-6 sm:px-6 sm:py-8">
        <header className="app-card mb-6 flex min-w-0 items-center justify-between gap-4 rounded-2xl px-5 py-4 backdrop-blur sm:px-7 sm:py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-bold sm:text-3xl">科研工作流</h1>
              <p className="truncate text-sm text-slate-600 dark:text-zinc-300">从研究需求到来源受限的证据与下一步</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="app-button-secondary hidden items-center gap-1.5 rounded-xl px-2.5 py-2 text-xs font-semibold md:inline-flex">
              <Route className="h-3.5 w-3.5" /> 需求确认 Skill
            </span>
            <ProviderStatusCard />
            <span className="hidden rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 sm:inline-flex dark:bg-zinc-800 dark:text-zinc-300">
              {GENERATION_LABELS[conversation.generation_mode]}
            </span>
            <button
              type="button"
              onClick={() => void startNewConversation()}
              disabled={disabled}
              className="app-button-secondary inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
            >
              <Plus className="h-3.5 w-3.5" /> <span className="hidden sm:inline">新建会话</span>
            </button>
          </div>
        </header>

        {conversation.context_provenance && (
          <aside className="mb-4 rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-950 dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-100">
            <p className="font-semibold">本会话来自已确认的 Learning 上下文</p>
            <p className="mt-1 leading-6">
              主题：{conversation.context_provenance.topic} · 来源记录：
              <span className="font-mono text-xs">
                {conversation.context_provenance.source_object.id}
              </span>
            </p>
            <p className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap rounded-xl bg-white/60 px-3 py-2 text-xs leading-5 dark:bg-zinc-950/30">
              {conversation.context_provenance.summary}
            </p>
            {conversation.context_provenance.selected_content.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer font-medium">
                  查看保留的学习内容（
                  {conversation.context_provenance.selected_content.length} 项）
                </summary>
                <div className="mt-2 space-y-2">
                  {conversation.context_provenance.selected_content.map((item) => (
                    <section
                      key={item.kind}
                      className="rounded-xl bg-white/60 px-3 py-2 dark:bg-zinc-950/30"
                    >
                      <p className="font-semibold">{item.label}</p>
                      <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap leading-5">
                        {item.content}
                      </p>
                    </section>
                  ))}
                </div>
              </details>
            )}
          </aside>
        )}

        <ResearchWorkflowNav
          conversation={conversation}
          currentStage={workflowStage}
          selectedPaperTitle={selectedPaperTitle}
        />

        <div className="min-w-0 space-y-7">
          <PanelSection
            id="research-section-start"
            title="研究起点"
            description="通过对话确认研究主题、候选问题、方法、数据与约束。"
            state={panelState(workflowStage, 0)}
          >
          <section className="min-w-0 overflow-hidden">
            <div className="max-h-[calc(100vh-13rem)] min-h-[520px] space-y-7 overflow-y-auto px-4 py-6 sm:px-7" aria-label="科研对话消息">
              {conversation.messages.map((message) => (
                <MessageItem key={message.message_id} message={message} />
              ))}
              {phase === "thinking" && <ThinkingMessage />}
              <div ref={endRef} />
            </div>

            {error && (
              <div role="alert" className="mx-4 mb-3 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300 sm:mx-7">
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="break-words">{error}</p>
                  {failedMessage && (
                    <button type="button" onClick={() => void send(failedMessage)} className="mt-1 font-semibold underline underline-offset-2">
                      重试本轮消息
                    </button>
                  )}
                </div>
              </div>
            )}

            {latestAssistant?.suggested_answers.length ? (
              <div className="flex max-w-full gap-2 overflow-x-auto px-4 pb-3 sm:flex-wrap sm:px-7">
                {latestAssistant.suggested_answers.map((answer) => (
                  <button
                    key={answer}
                    type="button"
                    disabled={disabled}
                    onClick={() => void send(answer)}
                    className="app-button-secondary shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
                  >
                    {answer}
                  </button>
                ))}
              </div>
            ) : null}

            <form onSubmit={submit} className="min-w-0 border-t border-slate-200 bg-slate-50/70 p-3 sm:p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <div className="app-card min-w-0 rounded-2xl p-2 transition focus-within:border-slate-400 focus-within:ring-4 focus-within:ring-slate-100 dark:focus-within:border-zinc-600 dark:focus-within:ring-zinc-800">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  disabled={disabled}
                  rows={2}
                  maxLength={4000}
                  placeholder="继续描述你的想法、纠正当前理解，或直接选择上方建议…"
                  aria-label="科研对话输入"
                  className="max-h-40 min-h-14 min-w-0 w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 outline-none placeholder:text-slate-400 disabled:opacity-60 dark:placeholder:text-zinc-600"
                />
                <div className="flex items-center justify-between gap-3 px-1">
                  <p className="text-xs text-slate-500 dark:text-zinc-400">Enter 发送 · Shift + Enter 换行</p>
                  <button
                    type="submit"
                    disabled={disabled || !draft.trim()}
                    className="app-button-primary inline-flex min-h-10 items-center gap-1.5 rounded-xl px-4 text-sm font-semibold transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-35 dark:hover:bg-white"
                  >
                    {phase === "thinking" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                    发送
                  </button>
                </div>
              </div>
              <p className="mt-2 flex items-center justify-center gap-1 text-xs text-slate-500 dark:text-zinc-400">
                <Clock3 className="h-3 w-3" /> 对话自动保存；Agent 建议仍需你判断，不等同于论文事实。
              </p>
            </form>
          </section>
          </PanelSection>

          <div className="min-w-0">
            <PanelSection
              id="research-section-profile"
              title="科研画像"
              description="当前研究需求与缺失信息；内容来自用户输入和规则判断。"
              state={panelState(workflowStage, 0)}
            >
              <ResearchProfilePanel profile={conversation.profile} readiness={conversation.readiness} onSend={(message) => void send(message)} disabled={disabled} />
            </PanelSection>
            {(conversation.research_plan || conversation.readiness.can_prepare_search) && (
              <PanelSection
                id="research-section-literature"
                title="方向与文献"
                description="先确认检索计划，再由你主动启动受限检索并保存来源。"
                state={panelState(workflowStage, 1)}
              >
                {conversation.research_plan ? <ResearchPlanPanel plan={conversation.research_plan} /> : (
                  <div className="app-card rounded-2xl p-5">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-zinc-100">生成模型研究计划</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">科研画像已达到准入条件。点击后由已配置的大模型生成研究计划；模型失败时不会使用规则模板替代。</p>
                    {planError && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-200">{planError}</p>}
                    <button type="button" onClick={() => void generatePlan()} disabled={planLoading} className="app-button-primary mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl px-4 text-sm font-semibold disabled:opacity-60">
                      {planLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      {planLoading ? "正在生成…" : "生成模型研究计划"}
                    </button>
                  </div>
                )}
                {conversation.research_plan && (
                  <div className="mt-6 scroll-mt-20">
                    {conversation.next_skill === "academic-search" && (
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-base leading-7 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-200">
                        <p className="flex items-center gap-2 font-bold"><SearchCheck className="h-5 w-5" /> 需求确认已完成</p>
                        <p className="mt-2">当前科研画像已交给“信息源检索 Skill”。系统不会自动全网搜索；请检查检索计划与允许来源后，再由你主动启动检索。</p>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setSearchPanelMounted(true);
                        setSearchPanelOpen((open) => !open);
                      }}
                      className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-emerald-300 bg-white px-4 text-sm font-semibold text-emerald-800 transition hover:bg-emerald-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 dark:border-emerald-800 dark:bg-zinc-900 dark:text-emerald-300 dark:hover:bg-emerald-950/30"
                    >
                      <SearchCheck className="h-4 w-4" />
                      {searchPanelOpen ? "收起受限检索与已保存证据" : "启动受限检索与查看已保存证据"}
                    </button>
                    {searchPanelMounted && (
                      <div className={searchPanelOpen ? "mt-5" : "hidden"}>
                        <AcademicSearchPanel
                          key={conversation.conversation_id}
                          conversationId={conversation.conversation_id}
                          onEvidenceSaved={() => refreshDownstream(1)}
                          onPaperSelected={(paper) => void analyzeSelectedPaper(paper)}
                        />
                      </div>
                    )}
                  </div>
                )}
              </PanelSection>
            )}
          </div>
        </div>

        <div className="mt-7 space-y-7">
          <PanelSection
            id="research-section-paper-analysis"
            title="论文深度分析"
            description="选择已保存论文后，系统会自动寻找公开正文；DeepSeek 将结合论文内容与你的研究目标生成针对性分析。"
            state={panelState(workflowStage, 2)}
          >
            <PaperDeepAnalysisPanel
              conversationId={conversation.conversation_id}
              selectedPaper={selectedPaper}
              analysis={paperAnalysis}
              loading={paperAnalysisLoading}
              error={paperAnalysisError}
              onRetry={(paperPdfUrl) => selectedPaper && void analyzeSelectedPaper(selectedPaper, paperPdfUrl)}
              onUpload={(file) => selectedPaper && void uploadSelectedPaper(selectedPaper, file)}
            />
            <details className="mt-6 rounded-2xl border border-slate-200 dark:border-zinc-800">
              <summary className="min-h-10 cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700 dark:text-zinc-200">补充能力：方向难点分析</summary>
              <div className="border-t border-slate-200 p-4 dark:border-zinc-800"><ResearchDifficultyPanel analysis={conversation.topic_difficulty_analysis} conversationId={conversation.conversation_id} /></div>
            </details>
          </PanelSection>

          <PanelSection
            id="research-section-mindmap"
            title="研究思维导图"
            description="用于在进入复现前整理当前论文分析、保存来源与待核验边界。"
            state={panelState(workflowStage, 2)}
          >
            <ResearchMindMapPanel
              conversationId={conversation.conversation_id}
              mindmap={conversation.research_mindmap}
              selectedPaperTitle={selectedPaper?.title ?? selectedPaperTitle}
              paperAnalysis={paperAnalysis}
              onGenerated={(mindmap: ResearchMindMap) => {
                setConversation((current) => (
                  current ? { ...current, research_mindmap: mindmap } : current
                ));
              }}
            />
          </PanelSection>

          {conversation.research_plan && (
            <PanelSection
              id="research-section-workbench"
              title="复现工作台"
              description="生成并核对复现方案；系统不会下载论文全文、安装依赖或执行论文代码。"
              state={panelState(workflowStage, 3)}
            >
              <ReproductionPipelinePanel
                conversationId={conversation.conversation_id}
                evidenceVersion={evidenceVersion}
                onPipelineSaved={(pipeline) => {
                  setSelectedPaperTitle(pipeline.selected_paper.title);
                  refreshDownstream(3);
                }}
              />
              <details className="mt-6 rounded-2xl border border-slate-200 dark:border-zinc-800">
                <summary className="min-h-10 cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700 dark:text-zinc-200">补充能力：实验方案与代码草案</summary>
                <div className="border-t border-slate-200 p-4 dark:border-zinc-800"><ExperimentDesignPanel design={conversation.experiment_design} conversationId={conversation.conversation_id} /></div>
              </details>
            </PanelSection>
          )}

          <PanelSection
            id="research-section-evidence"
            title="证据与成果"
            description="只有你主动提交的实验记录才是事实来源；关联记录不代表复现完成或成功。"
            state={panelState(workflowStage, 4)}
          >
            {conversation.research_plan && (
              <ExperimentEvidencePanel
                conversationId={conversation.conversation_id}
                evidenceVersion={evidenceVersion}
                onEvidenceSaved={() => refreshDownstream(4)}
              />
            )}
            <div className="mt-6">
              <h3 className="text-lg font-bold text-slate-900 dark:text-zinc-100">证据完整度评估</h3>
              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-300">它只检查已有证据边界，不代表复现成功或论文质量，也不代表实验正确或复现完成。</p>
              <div className="mt-4"><ReproductionEvaluationPanel conversationId={conversation.conversation_id} /></div>
            </div>
            {conversation.research_plan && (
              <details className="mt-6 rounded-2xl border border-slate-200 dark:border-zinc-800">
                <summary className="min-h-10 cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700 dark:text-zinc-200">补充能力：论文辅助、引用与投稿前检查</summary>
                <div className="border-t border-slate-200 p-4 dark:border-zinc-800"><PaperDraftReviewPanel conversationId={conversation.conversation_id} /></div>
              </details>
            )}
          </PanelSection>
        </div>
      </div>
    </main>
  );
}
