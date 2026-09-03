"use client";

import {
  ArrowLeft,
  CheckCircle2,
  CircleCheckBig,
  FileText,
  Loader2,
  Save,
  Trash2,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  ContextTransferApiError,
  confirmContextTransfer,
  deleteContextTransfer,
  getContextTransfer,
  type ContextTransfer,
  type SelectedContextContent,
  updateContextTransfer,
} from "@/lib/api/context-transfers";
import { getLearningSessionId } from "@/lib/api/learning";
import {
  RESEARCH_CONVERSATION_STORAGE_KEY,
  updateOrchestratorLearningContext,
} from "@/lib/api/research";

function messageFor(error: unknown): string {
  if (error instanceof ContextTransferApiError) {
    if (error.status === 404) return "这份待传递上下文不存在，或不属于当前学习会话。";
    return error.message;
  }
  return error instanceof Error ? error.message : "上下文操作失败，请重试。";
}

export default function ResearchContextConfirmationPage() {
  const params = useParams<{ contextId: string }>();
  const router = useRouter();
  const [context, setContext] = useState<ContextTransfer | null>(null);
  const [topic, setTopic] = useState("");
  const [summary, setSummary] = useState("");
  const [selectedContent, setSelectedContent] = useState<SelectedContextContent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const sessionId = getLearningSessionId();
    void getContextTransfer(params.contextId, sessionId)
      .then(async (restored) => {
        if (!active) return;
        if (restored.status === "confirmed" && restored.confirmed_conversation_id) {
          await updateOrchestratorLearningContext(restored.confirmed_conversation_id, {
            learned_content: restored.summary,
            learning_progress: null,
          });
          if (!active) return;
          window.localStorage.setItem(
            RESEARCH_CONVERSATION_STORAGE_KEY,
            restored.confirmed_conversation_id,
          );
          router.replace("/research");
          return;
        }
        setContext(restored);
        setTopic(restored.topic);
        setSummary(restored.summary);
        setSelectedContent(restored.selected_content);
      })
      .catch((requestError) => {
        if (active) setError(messageFor(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [params.contextId, router]);

  async function saveDraft() {
    if (!context || !topic.trim() || !summary.trim()) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await updateContextTransfer(
        context.id,
        getLearningSessionId(),
        {
          topic: topic.trim(),
          summary: summary.trim(),
          selected_content: selectedContent.map((item) => ({
            ...item,
            label: item.label.trim(),
            content: item.content.trim(),
          })),
        },
      );
      setContext(updated);
      setTopic(updated.topic);
      setSummary(updated.summary);
      setSelectedContent(updated.selected_content);
      setSaved(true);
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function clearDraft() {
    if (!context) return;
    setClearing(true);
    setError(null);
    try {
      await deleteContextTransfer(context.id, getLearningSessionId());
      router.push("/learning");
    } catch (requestError) {
      setError(messageFor(requestError));
      setClearing(false);
    }
  }

  async function confirmDraft() {
    if (!context || !topic.trim() || !summary.trim()) return;
    setConfirming(true);
    setSaved(false);
    setError(null);
    try {
      const conversation = await confirmContextTransfer(
        context.id,
        getLearningSessionId(),
        {
          topic: topic.trim(),
          summary: summary.trim(),
          selected_content: selectedContent.map((item) => ({
            ...item,
            label: item.label.trim(),
            content: item.content.trim(),
          })),
        },
      );
      await updateOrchestratorLearningContext(conversation.conversation_id, {
        learned_content: summary.trim(),
        learning_progress: null,
      });
      window.localStorage.setItem(
        RESEARCH_CONVERSATION_STORAGE_KEY,
        conversation.conversation_id,
      );
      router.push("/research");
    } catch (requestError) {
      setError(messageFor(requestError));
      setConfirming(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)]">
        <div role="status" aria-live="polite" className="text-center text-sm text-slate-500 dark:text-zinc-400">
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-500 dark:text-zinc-400" />
          <p className="mt-3">正在恢复待传递上下文…</p>
        </div>
      </main>
    );
  }

  if (!context) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--app-surface)] px-4">
        <div role="alert" className="app-card w-full max-w-lg rounded-2xl p-6 text-center">
          <h1 className="text-base font-bold text-slate-900 dark:text-zinc-100">无法打开待确认上下文</h1>
          <p className="mt-2 text-sm text-rose-700 dark:text-rose-300">{error}</p>
          <button type="button" onClick={() => router.push("/learning")} className="app-button-primary mt-5 rounded-xl px-4 py-2 text-sm">
            返回知识点学习
          </button>
        </div>
      </main>
    );
  }

  const invalid =
    !topic.trim() ||
    !summary.trim() ||
    selectedContent.some((item) => !item.label.trim() || !item.content.trim());

  return (
    <main className="min-h-screen bg-[var(--app-surface)] px-4 py-8 text-slate-900 dark:text-zinc-100 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <button type="button" onClick={() => router.push("/learning")} className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 dark:text-zinc-400 dark:hover:text-zinc-100">
          <ArrowLeft className="h-4 w-4" /> 返回知识点学习
        </button>

        <section className="app-card mt-5 rounded-3xl p-6 sm:p-8">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-slate-100 p-2.5 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-zinc-400">Learning → Research</p>
              <h1 className="mt-1 text-xl font-bold">确认待传递上下文</h1>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-zinc-400">
                内容来自已保存的学习记录。你可以修改传递快照，原始笔记不会改变。
              </p>
              <p className="mt-2 break-all text-xs text-slate-400 dark:text-zinc-500">
                来源：Learning / {context.source_object.type} / {context.source_object.id}
              </p>
            </div>
          </div>

          <div className="mt-7 space-y-5">
            <label className="block text-sm font-semibold">
              研究主题
              <input value={topic} onChange={(event) => { setTopic(event.target.value); setSaved(false); }} maxLength={500} className="app-input mt-2 w-full rounded-xl px-3 py-2.5 text-sm outline-none focus:border-slate-500" />
            </label>
            <label className="block text-sm font-semibold">
              上下文摘要
              <textarea value={summary} onChange={(event) => { setSummary(event.target.value); setSaved(false); }} maxLength={12000} rows={5} className="app-input mt-2 w-full resize-y rounded-xl px-3 py-2.5 text-sm leading-6 outline-none focus:border-slate-500" />
            </label>
            {selectedContent.map((item, index) => (
              <div key={item.kind} className="app-card-subtle rounded-2xl p-4">
                <div className="flex items-center gap-3">
                  <input value={item.label} onChange={(event) => { setSelectedContent((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, label: event.target.value } : entry)); setSaved(false); }} maxLength={80} aria-label={`选择内容 ${index + 1} 标题`} className="min-w-0 flex-1 bg-transparent text-sm font-semibold outline-none" />
                  <button type="button" onClick={() => { setSelectedContent((current) => current.filter((_, entryIndex) => entryIndex !== index)); setSaved(false); }} className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/30" aria-label={`删除 ${item.label}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <textarea value={item.content} onChange={(event) => { setSelectedContent((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, content: event.target.value } : entry)); setSaved(false); }} maxLength={12000} rows={5} aria-label={`选择内容 ${index + 1}`} className="app-input mt-2 w-full resize-y rounded-xl p-3 text-sm leading-6 outline-none focus:border-slate-500" />
              </div>
            ))}
            {selectedContent.length === 0 && (
              <p className="rounded-xl border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-500 dark:border-zinc-700 dark:text-zinc-400">
                已删除全部补充内容；确认后仍会传递上方主题和摘要。
              </p>
            )}
          </div>

          {error && <p role="alert" className="app-status-error mt-5 rounded-xl px-3 py-2 text-sm">{error}</p>}
          {saved && <p role="status" className="mt-5 flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="h-4 w-4" /> 已保存；刷新页面后仍可继续确认。</p>}

          <div className="mt-7 flex flex-wrap justify-between gap-3 border-t border-slate-100 pt-5 dark:border-zinc-800">
            <button type="button" onClick={() => void clearDraft()} disabled={clearing || saving || confirming} className="inline-flex items-center gap-2 rounded-xl border border-rose-200 px-4 py-2.5 text-sm font-medium text-rose-700 disabled:opacity-50 dark:border-rose-900 dark:text-rose-300">
              {clearing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} 取消传递
            </button>
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => void saveDraft()} disabled={invalid || saving || clearing || confirming} className="app-button-secondary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} 保存草稿
              </button>
              <button type="button" onClick={() => void confirmDraft()} disabled={invalid || saving || clearing || confirming} className="app-button-primary inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50">
                {confirming ? <Loader2 className="h-4 w-4 animate-spin" /> : <CircleCheckBig className="h-4 w-4" />} 确认并进入 Research
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
