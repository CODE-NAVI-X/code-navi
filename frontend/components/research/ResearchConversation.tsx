"use client";

import {
  ArrowLeft,
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
import { useRouter } from "next/navigation";
import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  createResearchConversation,
  getResearchConversation,
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
import { PaperDraftReviewPanel } from "./PaperDraftReviewPanel";

const STORAGE_KEY = "code-navi.research.conversation-id";
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
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-white shadow-sm">
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
          <div className="mt-3 break-words rounded-xl border-l-2 border-sky-500 bg-sky-50/70 px-4 py-3 text-sm font-medium leading-6 text-slate-800 dark:bg-sky-950/20 dark:text-zinc-200">
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
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
        <span className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
          正在理解并整理研究画像
        </span>
        <p className="mt-1 text-[11px] text-slate-400 dark:text-zinc-500">分析本轮信息、更新候选问题与下一步建议…</p>
      </div>
    </div>
  );
}

export function ResearchConversation() {
  const router = useRouter();
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
      const savedId = window.localStorage.getItem(STORAGE_KEY);
      if (savedId) {
        try {
          const restored = await getResearchConversation(savedId);
          setConversation(restored);
          return;
        } catch (requestError) {
          if (!(requestError instanceof ResearchApiError) || requestError.status !== 404) {
            throw requestError;
          }
          window.localStorage.removeItem(STORAGE_KEY);
        }
      }
      const created = await createResearchConversation();
      window.localStorage.setItem(STORAGE_KEY, created.conversation_id);
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
      setConversation(created);
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

  async function send(message: string) {
    const cleaned = message.trim();
    if (!conversation || !cleaned || phase !== "idle") return;
    setPhase("thinking");
    setError(null);
    setFailedMessage(null);
    try {
      const updated = await sendResearchMessage(conversation.conversation_id, cleaned);
      setConversation(updated);
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
      window.localStorage.setItem(STORAGE_KEY, created.conversation_id);
      setConversation(created);
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setPhase("idle");
    }
  }

  if (phase === "initializing" && !conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-zinc-950">
        <div className="text-center text-slate-500 dark:text-zinc-400">
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-sky-500" />
          <p className="mt-3 text-sm font-medium">正在连接并恢复科研会话…</p>
          <p className="mt-1 text-xs">只恢复已保存记录，不会重复调用 Agent。</p>
        </div>
      </main>
    );
  }

  if (!conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-zinc-950">
        <div className="w-full max-w-md rounded-2xl border border-rose-200 bg-white p-6 text-center shadow-sm dark:border-rose-900/50 dark:bg-zinc-900">
          <CircleAlert className="mx-auto h-7 w-7 text-rose-500" />
          <h1 className="mt-3 text-base font-bold text-slate-900 dark:text-zinc-100">科研会话暂时无法连接</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">{error}</p>
          <button
            type="button"
            onClick={() => void restoreOrCreate()}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
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
    <main className="min-h-screen bg-slate-50 text-slate-900 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="mx-auto w-full max-w-[1380px] overflow-x-hidden px-3 py-3 sm:px-5 sm:py-5">
        <header className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white/90 px-3 py-3 shadow-sm backdrop-blur sm:px-4 dark:border-zinc-800 dark:bg-zinc-900/90">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => router.push("/learning")}
              className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              aria-label="返回知识点学习"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-white">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold sm:text-base">科研方向对话助手</h1>
              <p className="truncate text-[11px] text-slate-500 dark:text-zinc-400">自由表达 · 动态追问 · 可恢复科研画像</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-xl border border-indigo-200 bg-indigo-50 px-2.5 py-2 text-xs font-semibold text-indigo-700 md:inline-flex dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-300">
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
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <Plus className="h-3.5 w-3.5" /> <span className="hidden sm:inline">新建会话</span>
            </button>
          </div>
        </header>

        <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_330px]">
          <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/70">
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

            {conversation.next_skill === "academic-search" && (
              <>
                <div className="mx-4 mb-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-200 sm:mx-7">
                  <p className="flex items-center gap-2 font-bold">
                    <SearchCheck className="h-4 w-4" /> 需求确认 Skill 已完成
                  </p>
                  <p className="mt-2 text-xs leading-5">
                    当前科研画像已交给“信息源检索 Skill”。系统不会自动全网搜索，请检查下方检索计划后再确认启动。
                  </p>
                </div>
                <AcademicSearchPanel
                  key={conversation.conversation_id}
                  conversationId={conversation.conversation_id}
                />
              </>
            )}

            {latestAssistant?.suggested_answers.length ? (
              <div className="flex max-w-full gap-2 overflow-x-auto px-4 pb-3 sm:flex-wrap sm:px-7">
                {latestAssistant.suggested_answers.map((answer) => (
                  <button
                    key={answer}
                    type="button"
                    disabled={disabled}
                    onClick={() => void send(answer)}
                    className="shrink-0 rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-800 transition hover:border-sky-400 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300"
                  >
                    {answer}
                  </button>
                ))}
              </div>
            ) : null}

            <form onSubmit={submit} className="min-w-0 border-t border-slate-200 bg-slate-50/70 p-3 sm:p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <div className="min-w-0 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm transition focus-within:border-sky-400 focus-within:ring-4 focus-within:ring-sky-100 dark:border-zinc-700 dark:bg-zinc-900 dark:focus-within:border-sky-700 dark:focus-within:ring-sky-950/40">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  disabled={disabled}
                  rows={2}
                  maxLength={4000}
                  placeholder="继续描述你的想法、纠正当前理解，或直接选择上方建议…"
                  className="max-h-40 min-h-14 min-w-0 w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 outline-none placeholder:text-slate-400 disabled:opacity-60 dark:placeholder:text-zinc-600"
                />
                <div className="flex items-center justify-between gap-3 px-1">
                  <p className="text-[10px] text-slate-400 dark:text-zinc-600">Enter 发送 · Shift + Enter 换行</p>
                  <button
                    type="submit"
                    disabled={disabled || !draft.trim()}
                    className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-slate-900 px-3 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-35 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
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

          <div className="hidden lg:block">
            <ResearchProfilePanel profile={conversation.profile} readiness={conversation.readiness} onSend={(message) => void send(message)} disabled={disabled} />
            {conversation.research_plan && <div className="mt-4"><ResearchPlanPanel plan={conversation.research_plan} /></div>}
            <div className="mt-4"><ResearchMindMapPanel mindmap={conversation.research_mindmap} /></div>
            <div className="mt-4"><ResearchDifficultyPanel analysis={conversation.topic_difficulty_analysis} conversationId={conversation.conversation_id} /></div>
            {conversation.experiment_design && <div className="mt-4"><ExperimentDesignPanel design={conversation.experiment_design} conversationId={conversation.conversation_id} /></div>}
            {conversation.research_plan && <div className="mt-4"><ExperimentEvidencePanel conversationId={conversation.conversation_id} /></div>}
            {conversation.research_plan && <div className="mt-4"><PaperDraftReviewPanel conversationId={conversation.conversation_id} /></div>}
          </div>

          <details className="group rounded-2xl border border-slate-200 bg-white lg:hidden dark:border-zinc-800 dark:bg-zinc-900">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold">
              查看科研画像与下一步
              <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
            </summary>
            <div className="border-t border-slate-200 p-3 dark:border-zinc-800">
              <ResearchProfilePanel profile={conversation.profile} readiness={conversation.readiness} onSend={(message) => void send(message)} disabled={disabled} />
              {conversation.research_plan && <div className="mt-3"><ResearchPlanPanel plan={conversation.research_plan} /></div>}
              <div className="mt-3"><ResearchMindMapPanel mindmap={conversation.research_mindmap} /></div>
              <div className="mt-3"><ResearchDifficultyPanel analysis={conversation.topic_difficulty_analysis} conversationId={conversation.conversation_id} /></div>
              {conversation.experiment_design && <div className="mt-3"><ExperimentDesignPanel design={conversation.experiment_design} conversationId={conversation.conversation_id} /></div>}
              {conversation.research_plan && <div className="mt-3"><ExperimentEvidencePanel conversationId={conversation.conversation_id} /></div>}
              {conversation.research_plan && <div className="mt-3"><PaperDraftReviewPanel conversationId={conversation.conversation_id} /></div>}
            </div>
          </details>
        </div>
      </div>
    </main>
  );
}
