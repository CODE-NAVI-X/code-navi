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
  createResearchConversation,
  getResearchConversation,
  RESEARCH_CONVERSATION_STORAGE_KEY,
  ResearchApiError,
  type ResearchConversationMessage,
  type ResearchConversationResponse,
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

const LEGACY_STORAGE_KEY = "code-navi.research.session-id";

type RequestPhase = "initializing" | "idle" | "thinking";

const GENERATION_LABELS = {
  agent: "Agent 个性化分析",
  rules: "基础规则（非模型）",
  rules_fallback: "Agent 失败，规则接管",
};

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
      <div className="space-y-2 border-t border-slate-200/80 px-3 py-3 text-[11px] leading-5 text-slate-600 dark:border-zinc-800 dark:text-zinc-400">
        <p>
          生成方式：
          <span className="font-semibold text-slate-800 dark:text-zinc-200">
            {GENERATION_LABELS[message.generation_mode]}
          </span>
        </p>
        {message.intent && <p>识别意图：{message.intent}</p>}
        {message.generation_mode === "agent" ? (
          <p>本轮已经过 Kernel AgentRuntime；记录了 {message.event_count} 个审计事件。</p>
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
          {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MarkdownText content={message.content} />}
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
        <p className="mt-1 text-[11px] text-slate-400 dark:text-zinc-500">分析本轮信息、更新候选问题与下一步建议…</p>
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
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <span className="min-w-0">
          <span className="block text-sm font-bold text-slate-900 dark:text-zinc-100">{title}</span>
          {state === "completed" && <span className="mt-0.5 block text-[11px] leading-5 text-emerald-700 dark:text-emerald-300">已完成阶段摘要：可展开查看已保存内容。</span>}
          {state !== "upcoming" && state !== "completed" && <span className="mt-0.5 block text-[11px] leading-5 text-slate-500 dark:text-zinc-400">{description}</span>}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-200 p-3 sm:p-4 dark:border-zinc-800">{children}</div>
    </details>
  );
}

export function ResearchConversation() {
  const [searchPanelMounted, setSearchPanelMounted] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(false);
  const [evidenceVersion, setEvidenceVersion] = useState(0);
  const [workflowStage, setWorkflowStage] = useState(0);
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
      setWorkflowStage(0);
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setPhase("idle");
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
      <div className="mx-auto w-full max-w-[1380px] overflow-x-hidden px-3 py-2 sm:px-5 sm:py-3">
        <header className="app-card mb-2 flex min-w-0 items-center justify-between gap-2 rounded-xl px-3 py-2 backdrop-blur">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold sm:text-base">科研方向对话助手</h1>
              <p className="truncate text-[11px] text-slate-500 dark:text-zinc-400">自由表达 · 动态追问 · 可恢复科研画像</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="app-button-secondary hidden items-center gap-1.5 rounded-xl px-2.5 py-2 text-xs font-semibold md:inline-flex">
              <Route className="h-3.5 w-3.5" /> 需求确认 Skill
            </span>
            <ProviderStatusCard />
            <span className="hidden rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-600 sm:inline-flex dark:bg-zinc-800 dark:text-zinc-300">
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

        <ResearchWorkflowNav conversation={conversation} currentStage={workflowStage} />

        <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_330px]">
          <PanelSection
            id="research-section-chat"
            title="研究需求"
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

            {(conversation.research_plan || conversation.next_skill === "academic-search") && (
              <div id="research-section-search" className="mx-4 mb-3 scroll-mt-20 sm:mx-7">
                {conversation.next_skill === "academic-search" && (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-200">
                    <p className="flex items-center gap-2 font-bold">
                      <SearchCheck className="h-4 w-4" /> 需求确认 Skill 已完成
                    </p>
                    <p className="mt-2 text-xs leading-5">
                      当前科研画像已交给“信息源检索 Skill”。系统不会自动全网搜索，请检查下方检索计划后再确认启动。
                    </p>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setSearchPanelMounted(true);
                    setSearchPanelOpen((open) => !open);
                  }}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-xl border border-emerald-300 bg-white px-3 py-2 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-50 dark:border-emerald-800 dark:bg-zinc-900 dark:text-emerald-300 dark:hover:bg-emerald-950/30"
                >
                  <SearchCheck className="h-3.5 w-3.5" />
                  {searchPanelOpen ? "收起受限检索与已保存证据" : "打开受限检索与已保存证据"}
                </button>
                {searchPanelMounted && (
                  <div className={searchPanelOpen ? undefined : "hidden"}>
                    <AcademicSearchPanel
                      key={conversation.conversation_id}
                      conversationId={conversation.conversation_id}
                      onEvidenceSaved={() => refreshDownstream(2)}
                    />
                  </div>
                )}
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
                  <p className="text-[10px] text-slate-400 dark:text-zinc-600">Enter 发送 · Shift + Enter 换行</p>
                  <button
                    type="submit"
                    disabled={disabled || !draft.trim()}
                    className="app-button-primary inline-flex h-8 items-center gap-1.5 rounded-xl px-3 text-xs font-semibold transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-35 dark:hover:bg-white"
                  >
                    {phase === "thinking" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                    发送
                  </button>
                </div>
              </div>
              <p className="mt-2 flex items-center justify-center gap-1 text-[10px] text-slate-400 dark:text-zinc-600">
                <Clock3 className="h-3 w-3" /> 对话自动保存；Agent 建议仍需你判断，不等同于论文事实。
              </p>
            </form>
          </section>
          </PanelSection>

          <aside className="min-w-0 space-y-4">
            <PanelSection
              id="research-section-profile"
              title="科研画像"
              description="当前研究需求与准备度；内容来自用户输入和规则判断。"
              state={panelState(workflowStage, 0)}
            >
              <ResearchProfilePanel profile={conversation.profile} readiness={conversation.readiness} onSend={(message) => void send(message)} disabled={disabled} />
            </PanelSection>
            {conversation.research_plan && (
              <PanelSection
                id="research-section-plan"
                title="检索计划"
                description="规则生成的研究与检索计划，仍需用户确认并主动启动检索。"
                state={panelState(workflowStage, 1)}
              >
                <ResearchPlanPanel plan={conversation.research_plan} />
              </PanelSection>
            )}
          </aside>
        </div>

        <div className="mt-4 space-y-4">
          <PanelSection
            id="research-section-difficulty"
            title="方向难点分析"
            description="基于科研画像、规则计划或已保存摘要的风险与缺口提示；每条均标注事实分类与生成方式。"
            state="supplementary"
          >
            <ResearchDifficultyPanel analysis={conversation.topic_difficulty_analysis} conversationId={conversation.conversation_id} />
          </PanelSection>
          {conversation.experiment_design && (
            <PanelSection
              id="research-section-experiment"
              title="实验方案与代码草案"
              description="建议性实验设计；代码草案需你明确确认，且只能预览、复制或下载文本，不会写入项目或执行。"
              state="supplementary"
            >
              <ExperimentDesignPanel design={conversation.experiment_design} conversationId={conversation.conversation_id} />
            </PanelSection>
          )}
          {conversation.research_plan && (
            <PanelSection
              id="research-section-evidence"
              title="实验结果证据包"
              description="只有你主动粘贴的实验记录才会成为事实来源；没有结果时仍可生成“待补充”的论文蓝图。"
              state={panelState(workflowStage, 4)}
            >
              <ExperimentEvidencePanel
                conversationId={conversation.conversation_id}
                evidenceVersion={evidenceVersion}
                onEvidenceSaved={() => refreshDownstream(4)}
              />
            </PanelSection>
          )}
          <PanelSection
            id="research-section-reproduction-evaluation"
            title="证据完整度评估"
            description="用户主动触发的五维证据完整性检查；缺少 Pipeline 或实验记录的维度保持不可评估，不代表复现成功或论文质量。"
            state={panelState(workflowStage, 4)}
          >
            <ReproductionEvaluationPanel conversationId={conversation.conversation_id} />
          </PanelSection>
          {conversation.research_plan && (
            <PanelSection
              id="research-section-reproduction"
              title="论文复现辅助"
              description="从已保存论文来源主动生成可核对的复现步骤；系统不自动执行代码或补造实验结果。"
              state={panelState(workflowStage, 3)}
            >
              <ReproductionPipelinePanel
                conversationId={conversation.conversation_id}
                evidenceVersion={evidenceVersion}
                onPipelineSaved={() => refreshDownstream(3)}
              />
            </PanelSection>
          )}
          {conversation.research_plan && (
            <PanelSection
              id="research-section-paper"
              title="论文辅助：初稿、审稿、修订与引用"
              description="初稿由你粘贴；审稿、候选修订与投稿前检查均为建议，不代表导师或同行评审结论。"
              state="supplementary"
            >
              <PaperDraftReviewPanel conversationId={conversation.conversation_id} />
            </PanelSection>
          )}
          <PanelSection
            id="research-section-mindmap"
            title="研究思维导图"
            description="只可视化已保存画像、规则计划与证据包；支持缩放、拖拽节点与 SVG 导出。"
            state="supplementary"
          >
            <ResearchMindMapPanel mindmap={conversation.research_mindmap} />
          </PanelSection>
        </div>
      </div>
    </main>
  );
}
