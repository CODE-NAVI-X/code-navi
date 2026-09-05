"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  Clock3,
  Loader2,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";

import {
  createResearchConversation,
  getOrchestratorDirectionCards,
  getOrchestratorPapers,
  getOrchestratorState,
  getResearchConversation,
  type DirectionCard,
  type OrchestratorMessageResponse,
  type OrchestratorPapersResponse,
  type OrchestratorStateResponse,
  type PaperUsage,
  RESEARCH_CONVERSATION_STORAGE_KEY,
  ResearchApiError,
  type ResearchConversationMessage,
  type ResearchConversationResponse,
  listResearchEvidence,
  type AcademicPaperResult,
  retryLastOrchestratorMessage,
  selectOrchestratorPaper,
  streamOrchestratorMessage,
} from "@/lib/api/research";

import { MarkdownText } from "./MarkdownText";
import { ProviderStatusCard } from "./ProviderStatusCard";
import { ResearchStageProgress } from "./ResearchStageProgress";
import { JiangJiangAvatar, UserAvatar } from "./JiangJiangAvatar";
import { DirectionCardsBox } from "./DirectionCardsBox";
import { CandidatePaperCard } from "./CandidatePaperCard";
import { SearchCandidateCards } from "./SearchCandidateCards";

type Phase = "initializing" | "idle" | "thinking";

const PASSIVE_TOOL_NAMES: Record<string, string> = {
  "stage-briefing": "阶段进展总结",
  "study-recommendations": "补学建议",
  "topic-difficulty-analysis": "难点分析",
  "experiment-design": "实验方案设计",
  "paper-blueprint": "论文大纲蓝图",
  "reproduction-evaluations": "复现准备度评估",
};

function friendlyError(error: unknown): string {
  if (error instanceof ResearchApiError) {
    if (error.status === 0) return error.message;
    if (error.status === 404) return "这段科研会话已不存在，可以新建会话后继续。";
    if (error.status === 409) return error.message || "当前状态无法执行此操作。";
    if (error.status === 422) return `发送内容未通过校验：${error.message}`;
    return `科研服务返回 HTTP ${error.status}：${error.message}`;
  }
  return error instanceof Error ? error.message : "发生了未知错误，请重试。";
}

export function ResearchConversation() {
  const [conversation, setConversation] = useState<ResearchConversationResponse | null>(null);
  const [orchestratorState, setOrchestratorState] = useState<OrchestratorStateResponse | null>(null);
  const [directionCards, setDirectionCards] = useState<DirectionCard[]>([]);
  const [searchCandidates, setSearchCandidates] = useState<AcademicPaperResult[]>([]);
  const [papers, setPapers] = useState<OrchestratorPapersResponse | null>(null);
  const [phase, setPhase] = useState<Phase>("initializing");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failedTurnError, setFailedTurnError] = useState<string | null>(null);
  const [paperActionLoading, setPaperActionLoading] = useState(false);

  const startedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  async function refreshSearchCandidates(conversationId: string) {
    try {
      const bundles = await listResearchEvidence(conversationId);
      const withPapers = bundles.filter((bundle) => bundle.papers.length > 0);
      const latest = withPapers[withPapers.length - 1];
      setSearchCandidates(latest ? latest.papers.slice(0, 5) : []);
    } catch {
      setSearchCandidates([]);
    }
  }

  const restoreOrCreate = useCallback(async () => {
    setPhase("initializing");
    setError(null);
    setFailedTurnError(null);
    try {
      let activeConversationId: string | null = null;
      const savedId = window.localStorage.getItem(RESEARCH_CONVERSATION_STORAGE_KEY);

      if (savedId) {
        try {
          const restored = await getResearchConversation(savedId);
          setConversation(restored);
          activeConversationId = restored.conversation_id;
        } catch (requestError) {
          if (!(requestError instanceof ResearchApiError) || requestError.status !== 404) {
            throw requestError;
          }
          window.localStorage.removeItem(RESEARCH_CONVERSATION_STORAGE_KEY);
        }
      }

      if (!activeConversationId) {
        const created = await createResearchConversation();
        window.localStorage.setItem(
          RESEARCH_CONVERSATION_STORAGE_KEY,
          created.conversation_id,
        );
        setConversation(created);
        activeConversationId = created.conversation_id;
      }

      // Fetch Orchestrator State, Direction Cards, and Papers
      const [stateRes, cardsRes, papersRes] = await Promise.all([
        getOrchestratorState(activeConversationId).catch(() => null),
        getOrchestratorDirectionCards(activeConversationId).catch(() => null),
        getOrchestratorPapers(activeConversationId).catch(() => null),
      ]);

      if (stateRes) {
        setOrchestratorState(stateRes);
        if (stateRes.last_status === "failed" && stateRes.last_error) {
          setFailedTurnError(stateRes.last_error);
        }
      }
      if (cardsRes?.cards) {
        setDirectionCards(cardsRes.cards);
      }
      if (papersRes) {
        setPapers(papersRes);
      }
      if (activeConversationId) {
        await refreshSearchCandidates(activeConversationId);
      }
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
    scrollToBottom();
  }, [conversation?.messages.length, phase, scrollToBottom]);

  async function handleSend(messageText: string) {
    const cleaned = messageText.trim();
    if (!conversation || !cleaned || phase !== "idle") return;

    setPhase("thinking");
    setError(null);
    setFailedTurnError(null);
    setDraft("");

    // Optimistically add the user message to UI stream
    const tempUserMsg: ResearchConversationMessage = {
      message_id: `user-${Date.now()}`,
      role: "user",
      content: cleaned,
      created_at: new Date().toISOString(),
      generation_mode: "agent",
      run_id: null,
      event_count: 0,
      intent: null,
      next_question: null,
      suggested_answers: [],
      candidate_questions: [],
      recommended_action: null,
    };

    setConversation((prev) =>
      prev ? { ...prev, messages: [...prev.messages, tempUserMsg] } : prev,
    );

    try {
      await streamOrchestratorMessage(conversation.conversation_id, cleaned, {
        onThinking: () => {
          setPhase("thinking");
        },
        onCompleted: (response: OrchestratorMessageResponse) => {
          if (response.reply_message) {
            const assistantMsg: ResearchConversationMessage = {
              message_id: response.reply_message.id,
              role: "assistant",
              content: response.reply_message.content,
              created_at: response.reply_message.created_at,
              generation_mode: "agent",
              run_id: null,
              event_count: 1,
              intent: null,
              next_question: null,
              suggested_answers: [],
              candidate_questions: [],
              recommended_action: null,
            };
            setConversation((prev) =>
              prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev,
            );
          }
          if (response.state) {
            setOrchestratorState(response.state);
          }
          setFailedTurnError(null);
          // Refresh direction cards & papers if stage progressed or papers changed
          void getOrchestratorDirectionCards(conversation.conversation_id)
            .then((res) => setDirectionCards(res.cards))
            .catch(() => {});
          void getOrchestratorPapers(conversation.conversation_id)
            .then((res) => setPapers(res))
            .catch(() => {});
          void refreshSearchCandidates(conversation.conversation_id);
        },
        onFailed: (response: OrchestratorMessageResponse) => {
          const errMsg = response.error || "思考未成功完成。请重试本轮。";
          setFailedTurnError(errMsg);
          if (response.state) {
            setOrchestratorState(response.state);
          }
        },
        onError: (streamErr: Error) => {
          setFailedTurnError(streamErr.message || "流式传输异常，请重试。");
        },
      });
    } catch (sendErr) {
      setFailedTurnError(friendlyError(sendErr));
    } finally {
      setPhase("idle");
    }
  }

  async function handleRetry() {
    if (!conversation || phase !== "idle") return;
    setPhase("thinking");
    setError(null);
    setFailedTurnError(null);

    try {
      const response = await retryLastOrchestratorMessage(conversation.conversation_id);
      if (response.status === "completed" && response.reply_message) {
        const assistantMsg: ResearchConversationMessage = {
          message_id: response.reply_message.id,
          role: "assistant",
          content: response.reply_message.content,
          created_at: response.reply_message.created_at,
          generation_mode: "agent",
          run_id: null,
          event_count: 1,
          intent: null,
          next_question: null,
          suggested_answers: [],
          candidate_questions: [],
          recommended_action: null,
        };
        setConversation((prev) =>
          prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev,
        );
        if (response.state) {
          setOrchestratorState(response.state);
        }
        setFailedTurnError(null);
      } else if (response.status === "failed") {
        setFailedTurnError(response.error || "重试失败，请再次尝试。");
        if (response.state) {
          setOrchestratorState(response.state);
        }
      }
    } catch (retryErr) {
      setFailedTurnError(friendlyError(retryErr));
    } finally {
      setPhase("idle");
    }
  }

  async function handleSelectPaper(paperUrl: string, title: string, purpose: PaperUsage) {
    if (!conversation || paperActionLoading) return;
    setPaperActionLoading(true);
    try {
      const res = await selectOrchestratorPaper(conversation.conversation_id, {
        paper_url: paperUrl,
        title,
        purpose,
      });
      setPapers(res);
      // Also update orchestrator state subtask
      const updatedState = await getOrchestratorState(conversation.conversation_id);
      setOrchestratorState(updatedState);
    } catch (paperErr) {
      setError(friendlyError(paperErr));
    } finally {
      setPaperActionLoading(false);
    }
  }

  async function handleStartNewConversation() {
    if (conversation && conversation.messages.length > 2) {
      const confirmed = window.confirm(
        "新建会话后，当前记录仍保留在服务端，但页面将开启全新对话。确定继续吗？",
      );
      if (!confirmed) return;
    }
    setPhase("initializing");
    setError(null);
    setFailedTurnError(null);
    setConversation(null);
    setOrchestratorState(null);
    setDirectionCards([]);
    setPapers(null);
    setDraft("");

    try {
      const created = await createResearchConversation();
      window.localStorage.setItem(
        RESEARCH_CONVERSATION_STORAGE_KEY,
        created.conversation_id,
      );
      setConversation(created);
      const [stateRes, cardsRes, papersRes] = await Promise.all([
        getOrchestratorState(created.conversation_id).catch(() => null),
        getOrchestratorDirectionCards(created.conversation_id).catch(() => null),
        getOrchestratorPapers(created.conversation_id).catch(() => null),
      ]);
      if (stateRes) setOrchestratorState(stateRes);
      if (cardsRes?.cards) setDirectionCards(cardsRes.cards);
      if (papersRes) setPapers(papersRes);
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setPhase("idle");
    }
  }

  function handleFormSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void handleSend(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend(draft);
    }
  }

  if (phase === "initializing" && !conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] px-4">
        <div role="status" aria-live="polite" className="text-center text-slate-500 dark:text-zinc-400">
          <JiangJiangAvatar size="lg" isThinking />
          <p className="mt-4 text-base font-semibold text-slate-900 dark:text-zinc-100">
            正在连接科研主舞台…
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
            自动恢复最近会话与四阶段状态
          </p>
        </div>
      </main>
    );
  }

  if (!conversation) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] px-4">
        <div role="alert" className="app-card w-full max-w-md rounded-3xl p-6 text-center shadow-lg border border-slate-200 dark:border-zinc-800">
          <AlertCircle className="mx-auto h-8 w-8 text-rose-500" />
          <h1 className="mt-3 text-lg font-bold text-slate-900 dark:text-zinc-100">
            无法连接科研对话服务
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">
            {error || "请确认后端服务已启动后重试。"}
          </p>
          <button
            type="button"
            onClick={() => void restoreOrCreate()}
            className="app-button-primary mt-5 inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold shadow-xs"
          >
            <RefreshCw className="h-4 w-4" /> 重新连接
          </button>
        </div>
      </main>
    );
  }

  const currentStage = orchestratorState?.current_stage || "research_need";
  const completedStages = orchestratorState?.completed_stages || [];
  const showDirectionCards =
    currentStage === "research_need" && directionCards.length > 0;
  const isThinking = phase === "thinking";
  const disabled = phase !== "idle";

  return (
    <main
      key={conversation.conversation_id}
      className="flex h-screen flex-col overflow-hidden bg-[var(--app-surface)] text-slate-900 dark:text-zinc-100"
    >
      {/* 1. Header & Stage Bar */}
      <header className="shrink-0 border-b border-slate-200/80 bg-white/80 px-4 py-3 sm:px-6 sm:py-3.5 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80 z-20">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <JiangJiangAvatar size="md" isThinking={isThinking} />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-bold tracking-tight text-slate-900 dark:text-zinc-100">
                  姜姜科研助手
                </h1>
                <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                  <Sparkles className="h-3 w-3" /> 对话主舞台
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-zinc-400 hidden sm:block">
                由科研 Agent 姜姜主导，连续四阶段自然语言递进
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <ProviderStatusCard />
            <button
              type="button"
              disabled={disabled}
              onClick={() => void handleStartNewConversation()}
              className="app-button-secondary inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold shadow-2xs hover:bg-slate-100 dark:hover:bg-zinc-800 transition disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">新建对话</span>
            </button>
          </div>
        </div>

        {/* Top 4-Stage Horizontal Progress Bar (Non-clickable, pure status indicator) */}
        <div className="mx-auto max-w-5xl mt-2.5">
          <ResearchStageProgress
            currentStage={currentStage}
            completedStages={completedStages}
          />
        </div>
      </header>

      {/* 2. Confirmed Learning Context Notice (if present) */}
      {conversation.context_provenance && (
        <aside className="shrink-0 mx-auto w-full max-w-5xl px-4 pt-3 sm:px-6">
          <div className="rounded-xl border border-indigo-200 bg-indigo-50/80 px-4 py-2.5 text-xs text-indigo-950 dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-100 flex items-start gap-2.5">
            <Zap className="h-4 w-4 shrink-0 text-indigo-600 dark:text-indigo-400 mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                已导入 Learning 学习背景：「{conversation.context_provenance.topic}」
              </p>
              <p className="mt-0.5 text-slate-600 dark:text-zinc-300 line-clamp-1">
                {conversation.context_provenance.summary}
              </p>
            </div>
          </div>
        </aside>
      )}

      {/* 3. Main Chat Stream (Single Arena) */}
      <section
        aria-label="科研对话流"
        className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6"
      >
        <div className="mx-auto max-w-4xl space-y-6">
          {conversation.messages.map((message) => {
            const isUser = message.role === "user";

            return (
              <article
                key={message.message_id}
                className={`flex gap-3 sm:gap-4 ${
                  isUser ? "justify-end" : "justify-start"
                }`}
              >
                {/* Assistant Avatar */}
                {!isUser && (
                  <div className="mt-1 shrink-0">
                    <JiangJiangAvatar size="md" />
                  </div>
                )}

                <div
                  className={`min-w-0 ${
                    isUser
                      ? "max-w-[85%] sm:max-w-[75%]"
                      : "max-w-[90%] sm:max-w-[85%] flex-1"
                  }`}
                >
                  {/* Sender Name Badge for Assistant */}
                  {!isUser && (
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-800 dark:text-zinc-200">
                        姜姜
                      </span>
                      <span className="text-xs text-slate-400 dark:text-zinc-500">
                        科研 Agent
                      </span>
                      {message.triggered_tool && PASSIVE_TOOL_NAMES[message.triggered_tool] && (
                        <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                          结合【{PASSIVE_TOOL_NAMES[message.triggered_tool]}】整理
                        </span>
                      )}
                    </div>
                  )}

                  {/* Speech Bubble */}
                  <div
                    className={
                      isUser
                        ? "rounded-2xl rounded-tr-xs bg-slate-900 px-4 py-3 text-base leading-7 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900"
                        : "rounded-2xl rounded-tl-xs border border-slate-200/80 bg-white/95 px-4 sm:px-5 py-3.5 text-base leading-7 text-slate-800 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/95 dark:text-zinc-200"
                    }
                  >
                    {isUser ? (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    ) : (
                      <MarkdownText content={message.content} />
                    )}
                  </div>
                </div>

                {/* User Avatar */}
                {isUser && (
                  <div className="mt-1 shrink-0">
                    <UserAvatar size="md" />
                  </div>
                )}
              </article>
            );
          })}

          {/* Exception 1: Dynamic Direction Cards (Shown in stage research_need) */}
          {showDirectionCards && (
            <DirectionCardsBox
              cards={directionCards}
              disabled={disabled}
              onSelectDirection={(dir) => void handleSend(dir)}
            />
          )}

          {/* P3-A: candidate paper cards from the latest real search bundle */}
          {searchCandidates.length > 0 && (
            <SearchCandidateCards
              papers={searchCandidates}
              disabled={disabled}
              onSelect={(paper) =>
                void handleSend(
                  `我想选择这篇论文作为复现候选：《${paper.title}》 ${paper.url}`,
                )
              }
            />
          )}

          {/* Exception 2: Candidate Paper Card (Shown when paper exists) */}
          {papers && (papers.current_paper || papers.paper_history.length > 0) && (
            <CandidatePaperCard
              currentPaper={papers.current_paper}
              paperHistory={papers.paper_history}
              loading={paperActionLoading}
              onSelectPurpose={handleSelectPaper}
            />
          )}

          {/* Thinking Status Indicator */}
          {isThinking && (
            <div
              role="status"
              aria-live="polite"
              className="flex items-center gap-3 text-slate-600 dark:text-zinc-300"
            >
              <JiangJiangAvatar size="md" isThinking />
              <div className="rounded-2xl rounded-tl-xs border border-indigo-200 bg-indigo-50/70 px-4 py-2.5 text-sm dark:border-indigo-900/60 dark:bg-indigo-950/40 shadow-xs flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-indigo-600 dark:text-indigo-400" />
                <span className="font-semibold text-indigo-900 dark:text-indigo-200">
                  姜姜正在思考……
                </span>
              </div>
            </div>
          )}

          {/* Failed Turn Alert & Retry Option */}
          {failedTurnError && (
            <div
              role="alert"
              className="rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-sm text-rose-900 shadow-sm dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
                <div className="min-w-0">
                  <p className="font-bold">本次思考未成功完成</p>
                  <p className="mt-0.5 text-xs text-rose-700 dark:text-rose-300">
                    {failedTurnError}（你的输入已完整保留，阶段未发生变更）
                  </p>
                </div>
              </div>
              <button
                type="button"
                disabled={disabled}
                onClick={() => void handleRetry()}
                className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-rose-700 transition disabled:opacity-50 shrink-0"
              >
                <RefreshCw className="h-3.5 w-3.5" /> 重试本轮
              </button>
            </div>
          )}

          {/* Bottom Anchor for Auto-Scroll */}
          <div ref={messagesEndRef} />
        </div>
      </section>

      {/* 4. Bottom Composer */}
      <footer className="shrink-0 border-t border-slate-200/80 bg-white/90 p-3 sm:p-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/90 z-20">
        <div className="mx-auto max-w-4xl">
          {/* Quick Action Pills for Conversation Progression */}
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {currentStage === "research_need" && (
              <>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("我已明确研究需求，就这样，可以进入下一步。")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  确认需求并进入计划
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("这个方向难吗？有什么难点？")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  询问方向难点
                </button>
              </>
            )}
            {currentStage === "research_plan" && (
              <>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("研究计划没问题，可以继续进入研究开展。")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  确认计划并开展研究
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("我该先学什么？有什么补学建议？")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  获取补学建议
                </button>
              </>
            )}
            {currentStage === "research_execution" && (
              <>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("文献精读与实验方案已完成，可以进入结果分析。")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  进入结果分析
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void handleSend("帮我评估一下我的复现准备度。")}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50"
                >
                  评估复现准备度
                </button>
              </>
            )}
            <button
              type="button"
              disabled={disabled}
              onClick={() => void handleSend("总结一下我们当前的进展到哪了。")}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 transition disabled:opacity-50 ml-auto"
            >
              总结当前进展
            </button>
          </div>

          {/* Form Composer */}
          <form onSubmit={handleFormSubmit} className="relative">
            <div className="app-card rounded-2xl p-2.5 shadow-sm transition focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-100 dark:focus-within:border-indigo-600 dark:focus-within:ring-indigo-950/50">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                disabled={disabled}
                rows={2}
                maxLength={8000}
                placeholder="和姜姜讨论研究问题、输入方向、或提出修改想法… (Enter 发送, Shift+Enter 换行)"
                aria-label="科研对话输入"
                className="max-h-36 min-h-12 w-full resize-none bg-transparent px-2 py-1 text-base leading-7 outline-none placeholder:text-slate-400 disabled:opacity-60 dark:placeholder:text-zinc-600"
              />
              <div className="flex items-center justify-between gap-3 pt-1">
                <span className="flex items-center gap-1 text-xs text-slate-400 dark:text-zinc-500">
                  <Clock3 className="h-3.5 w-3.5" /> 对话已持久化保存
                </span>
                <button
                  type="submit"
                  disabled={disabled || !draft.trim()}
                  className="app-button-primary inline-flex min-h-9 items-center gap-1.5 rounded-xl px-4 text-xs font-semibold transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-white"
                >
                  {isThinking ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                  发送
                </button>
              </div>
            </div>
          </form>
        </div>
      </footer>
    </main>
  );
}
