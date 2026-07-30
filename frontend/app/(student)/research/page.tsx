"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  CircleAlert,
  ClipboardList,
  FlaskConical,
  GraduationCap,
  Loader2,
  RotateCcw,
  Send,
} from "lucide-react";

import {
  createResearchSession,
  getResearchSession,
  ResearchApiError,
  ResearchPlanEntry,
  ResearchSessionResponse,
  ResearchState,
  submitResearchTurn,
} from "@/lib/api/research";

const STORAGE_KEY = "code-navi.research.session-id";

const FIELD_LABELS: { key: keyof ResearchState; label: string }[] = [
  { key: "research_domain", label: "研究领域" },
  { key: "core_question", label: "核心问题" },
  { key: "data_and_method", label: "数据与方法" },
  { key: "constraints", label: "约束条件" },
  { key: "expected_deliverable", label: "预期交付物" },
];

function PlanEntry({ entry }: { entry: ResearchPlanEntry }) {
  const isToVerify = entry.classification === "to_verify";
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3 text-xs leading-relaxed text-zinc-300">
      <span
        className={`mr-2 inline-flex rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
          isToVerify
            ? "bg-amber-950/60 text-amber-300"
            : "bg-sky-950/60 text-sky-300"
        }`}
      >
        {isToVerify ? "待验证" : "推断建议"}
      </span>
      {entry.content}
      <p className="mt-1.5 text-[10px] text-zinc-500">依据：{entry.basis}</p>
    </div>
  );
}

function ResearchContent() {
  const router = useRouter();
  const [session, setSession] = useState<ResearchSessionResponse | null>(null);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const restoreOrCreate = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const savedSessionId = window.localStorage.getItem(STORAGE_KEY);
      if (savedSessionId) {
        try {
          const restored = await getResearchSession(savedSessionId);
          setSession(restored);
          return;
        } catch (requestError) {
          if (!(requestError instanceof ResearchApiError) || requestError.status !== 404) {
            throw requestError;
          }
          window.localStorage.removeItem(STORAGE_KEY);
        }
      }

      const created = await createResearchSession();
      window.localStorage.setItem(STORAGE_KEY, created.session_id);
      setSession(created);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "科研会话初始化失败，请检查服务后重试。",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void restoreOrCreate();
    });
    return () => {
      cancelled = true;
    };
  }, [restoreOrCreate]);

  async function sendTurn(payload: { answer: string } | { selected_option: string }) {
    if (!session) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await submitResearchTurn(session.session_id, payload);
      setSession(updated);
      setDraft("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `本轮未提交：${requestError.message}`
          : "本轮未提交，请重试。",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function submitFreeText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const answer = draft.trim();
    if (answer) void sendTurn({ answer });
  }

  function startNewSession() {
    window.localStorage.removeItem(STORAGE_KEY);
    setSession(null);
    void restoreOrCreate();
  }

  const completed = session?.completed ?? false;
  const question = session?.next_question;
  const guidanceMessage =
    session?.generation_mode === "llm"
      ? "当前为模型个性化建议：字段顺序、状态保存与完成判定仍由规则控制。"
      : session?.generation_mode === "rules_fallback"
        ? "模型建议暂不可用，已安全降级为规则生成：不调用联网检索，也不会把建议当作论文事实。"
        : "当前为规则生成：未使用模型个性化建议，不联网检索，也不会把建议当作论文事实。";

  return (
    <div className="max-w-3xl w-full bg-zinc-900/90 border border-zinc-800 rounded-3xl p-6 sm:p-8 shadow-2xl backdrop-blur-md space-y-6">
      <button
        type="button"
        onClick={() => router.push("/student/learning")}
        className="inline-flex items-center gap-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
      >
        返回知识点学习
      </button>

      <div className="flex items-start justify-between gap-4 border-b border-zinc-800/80 pb-5">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-2xl bg-zinc-800/80 border border-zinc-700/60 flex items-center justify-center text-zinc-300">
            <GraduationCap className="h-5.5 w-5.5" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-zinc-100">规则驱动科研助手</h1>
            <p className="text-xs text-zinc-400">五字段澄清 → 研究简报 → 研究计划</p>
          </div>
        </div>
        <button
          type="button"
          onClick={startNewSession}
          disabled={isLoading || isSubmitting}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-zinc-700 px-2.5 py-1.5 text-[11px] font-medium text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RotateCcw className="h-3.5 w-3.5" /> 新建会话
        </button>
      </div>

      <div className="rounded-2xl border border-sky-900/60 bg-gradient-to-r from-sky-950/30 to-zinc-900 p-4 text-xs text-sky-200">
        <div className="flex items-center gap-2 font-semibold">
          <FlaskConical className="h-4 w-4" />
          {guidanceMessage}
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-2xl border border-rose-900/70 bg-rose-950/30 p-4 text-xs text-rose-200">
          <div className="flex items-start gap-2">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p>{error}</p>
              <button
                type="button"
                onClick={() => void restoreOrCreate()}
                className="mt-2 font-semibold text-rose-100 underline underline-offset-2"
              >
                重试连接
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading && !session ? (
        <div className="flex items-center justify-center gap-2 py-12 text-xs text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" /> 正在恢复科研会话...
        </div>
      ) : session ? (
        <>
          <section className="space-y-3" aria-label="科研澄清进度">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold text-zinc-200">研究信息收集进度</h2>
              <span className="text-[11px] text-zinc-500">
                {5 - session.missing_fields.length}/5 已完成
              </span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
              {FIELD_LABELS.map(({ key, label }) => {
                const value = session.state[key];
                return (
                  <div
                    key={key}
                    className={`rounded-xl border p-2.5 ${
                      value ? "border-emerald-900/70 bg-emerald-950/20" : "border-zinc-800 bg-zinc-950/60"
                    }`}
                  >
                    <div className="flex items-center gap-1 text-[10px] text-zinc-500">
                      {value && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                      {label}
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] text-zinc-300">{value ?? "待填写"}</p>
                  </div>
                );
              })}
            </div>
          </section>

          {!completed && question && (
            <section className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-950/50 p-5">
              <div>
                <p className="text-[11px] font-semibold text-sky-300">当前字段：{question.label}</p>
                <p className="mt-2 text-xs leading-relaxed text-zinc-300">{session.reply}</p>
                <h2 className="mt-1 text-sm font-bold text-zinc-100">{question.question}</h2>
              </div>

              <div className="grid gap-2 sm:grid-cols-3">
                {question.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => void sendTurn({ selected_option: option })}
                    className="rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-left text-xs text-zinc-200 hover:border-sky-700 hover:bg-sky-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {option}
                  </button>
                ))}
              </div>

              <form onSubmit={submitFreeText} className="flex gap-2 border-t border-zinc-800 pt-4">
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  disabled={isSubmitting}
                  maxLength={500}
                  placeholder="也可以直接输入你的具体情况"
                  className="min-w-0 flex-1 rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-xs text-zinc-100 outline-none placeholder:text-zinc-500 focus:border-sky-700 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={isSubmitting || !draft.trim()}
                  className="inline-flex items-center gap-1 rounded-xl bg-sky-600 px-3 py-2.5 text-xs font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  提交
                </button>
              </form>
            </section>
          )}

          {completed && session.research_brief && session.research_plan && (
            <section className="space-y-5" aria-label="研究简报与研究计划">
              <div className="rounded-2xl border border-emerald-900/70 bg-emerald-950/20 p-5">
                <h2 className="flex items-center gap-2 text-sm font-bold text-emerald-200">
                  <CheckCircle2 className="h-4 w-4" /> 结构化研究简报
                </h2>
                <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                  {FIELD_LABELS.map(({ key, label }) => (
                    <div key={key} className="rounded-lg bg-zinc-950/50 p-2.5">
                      <dt className="text-[10px] text-zinc-500">{label}</dt>
                      <dd className="mt-1 text-xs text-zinc-200">{session.research_brief?.[key]}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div className="rounded-2xl border border-zinc-800 bg-zinc-950/50 p-5">
                <h2 className="flex items-center gap-2 text-sm font-bold text-zinc-100">
                  <ClipboardList className="h-4 w-4 text-sky-300" /> 规则研究计划
                </h2>
                <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">{session.research_plan.provenance_note}</p>

                <div className="mt-4 space-y-4">
                  <PlanSection title="研究题目" entries={[session.research_plan.research_title]} />
                  <PlanSection title="研究目标" entries={[session.research_plan.research_goal]} />
                  <PlanSection title="候选方法或基线" entries={session.research_plan.candidate_methods_or_baselines} />
                  <PlanSection title="可选数据集或评测指标" entries={session.research_plan.suggested_datasets_or_metrics} />
                  <PlanSection title="两周最小可行验证计划" entries={session.research_plan.two_week_mvp_plan} />
                  <section>
                    <h3 className="mb-2 text-xs font-semibold text-zinc-300">主要风险与规避建议</h3>
                    <ul className="space-y-2">
                      {session.research_plan.risks_and_mitigations.map((item, index) => (
                        <li key={index} className="grid gap-2 sm:grid-cols-2">
                          <PlanEntry entry={item.risk} />
                          <PlanEntry entry={item.mitigation} />
                        </li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h3 className="mb-2 text-xs font-semibold text-zinc-300">建议检索关键词</h3>
                    <div className="flex flex-wrap gap-2">
                      {session.research_plan.suggested_search_keywords.map((keyword) => (
                        <span key={keyword} className="rounded-full bg-zinc-800 px-2.5 py-1 text-[11px] text-zinc-300">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </section>
                </div>
              </div>
            </section>
          )}
        </>
      ) : null}
    </div>
  );
}

function PlanSection({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold text-zinc-300">{title}</h3>
      <ul className="space-y-2">
        {entries.map((entry) => (
          <li key={`${entry.classification}-${entry.content}`}>
            <PlanEntry entry={entry} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ResearchPage() {
  return (
    <main className="min-h-screen bg-zinc-950 bg-grid-pattern text-zinc-100 p-6 sm:p-10 flex flex-col items-center justify-center">
      <Suspense
        fallback={(
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} /> 页面加载中...
          </div>
        )}
      >
        <ResearchContent />
      </Suspense>
    </main>
  );
}
