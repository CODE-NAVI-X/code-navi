"use client";

import { Check, Clipboard, FilePenLine, Loader2, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  createPaperDraft, createPaperReview, createPaperRevision, listPaperDrafts, listPaperReviews,
  listPaperRevisions, updatePaperRevisionTask, type PaperDraft, type PaperReview, type PaperRevision,
  type ReviewSeverity,
} from "@/lib/api/research";

const severityLabel: Record<ReviewSeverity, string> = { blocker: "阻塞", major: "重要", minor: "一般", suggestion: "建议" };
const severityClass: Record<ReviewSeverity, string> = { blocker: "text-rose-700 dark:text-rose-300", major: "text-orange-700 dark:text-orange-300", minor: "text-amber-700 dark:text-amber-300", suggestion: "text-sky-700 dark:text-sky-300" };

export function PaperDraftReviewPanel({ conversationId }: { conversationId: string }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [format, setFormat] = useState<"markdown" | "plain_text">("markdown");
  const [drafts, setDrafts] = useState<PaperDraft[]>([]);
  const [draft, setDraft] = useState<PaperDraft | null>(null);
  const [review, setReview] = useState<PaperReview | null>(null);
  const [revision, setRevision] = useState<PaperRevision | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void listPaperDrafts(conversationId).then(async (saved) => {
      if (!active) return;
      setDrafts(saved);
      const latest = saved[0] ?? null;
      setDraft(latest);
      if (latest) {
        const [reviews, revisions] = await Promise.all([listPaperReviews(latest.draft_id), listPaperRevisions(latest.draft_id)]);
        if (active) { setReview(reviews[0] ?? null); setRevision(revisions[0] ?? null); }
      }
    }).catch((value: unknown) => active && setError(value instanceof Error ? value.message : "无法恢复本地初稿。"));
    return () => { active = false; };
  }, [conversationId]);

  async function submitDraft() {
    if (!title.trim() || !content.trim()) { setError("请填写标题和初稿文本后再提交。"); return; }
    setBusy(true); setError(null);
    try {
      const saved = await createPaperDraft(conversationId, { title, content, format });
      setDraft(saved); setDrafts((current) => [saved, ...current]); setReview(null); setRevision(null);
    } catch (value) { setError(value instanceof Error ? value.message : "保存初稿失败。请重试。"); } finally { setBusy(false); }
  }
  async function runReview() {
    if (!draft) return;
    setBusy(true); setError(null);
    try { setReview(await createPaperReview(draft.draft_id)); setRevision(null); }
    catch (value) { setError(value instanceof Error ? value.message : "生成审稿建议失败。请重试。"); } finally { setBusy(false); }
  }
  async function changeTask(taskId: string, status: "accepted" | "skipped") {
    if (!review) return;
    setBusy(true); setError(null);
    try { setReview(await updatePaperRevisionTask(review.review_id, taskId, status)); }
    catch (value) { setError(value instanceof Error ? value.message : "保存修订决定失败。请重试。"); } finally { setBusy(false); }
  }
  async function previewRevision() {
    if (!review) return;
    setBusy(true); setError(null);
    try { setRevision(await createPaperRevision(review.review_id)); }
    catch (value) { setError(value instanceof Error ? value.message : "无法生成修订预览。请先接受至少一项任务。"); } finally { setBusy(false); }
  }
  async function copyRevision() {
    if (!revision) return;
    try { await navigator.clipboard.writeText(revision.content); }
    catch { setError("复制失败，请手动选择文本复制。"); }
  }

  return <section className="rounded-2xl border border-violet-200 bg-white p-4 shadow-sm dark:border-violet-900/70 dark:bg-zinc-900/80">
    <div className="flex items-center gap-3"><span className="rounded-xl bg-violet-100 p-2 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300"><FilePenLine className="h-4 w-4" /></span><div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700 dark:text-violet-300">Local draft review</p><h2 className="mt-1 text-sm font-bold">论文初稿与结构化审稿</h2></div></div>
    <p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">仅接受当前本地会话主动粘贴的 Markdown/纯文本。DOCX/PDF 导入、最终格式导出留待后续；不会联网、写入项目、自动投稿，也不能替代导师或同行评审。</p>
    <div className="mt-3 grid gap-2"><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} placeholder="初稿标题" className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" /><select value={format} onChange={(event) => setFormat(event.target.value as "markdown" | "plain_text")} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950"><option value="markdown">Markdown</option><option value="plain_text">纯文本</option></select><textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={60000} rows={8} placeholder="粘贴你的初稿。只提交你愿意在当前本地会话中分析的文本。" className="resize-y rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs leading-5 dark:border-zinc-700 dark:bg-zinc-950" /></div>
    <button type="button" onClick={() => void submitDraft()} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clipboard className="h-3.5 w-3.5" />}提交本地初稿</button>
    {error && <p role="alert" className="mt-2 text-xs text-rose-600">{error}</p>}
    {draft && <div className="mt-4 rounded-xl border border-violet-100 p-3 text-xs dark:border-violet-950"><p className="font-semibold">已保存：{draft.title} · v{draft.version}</p><p className="mt-1 text-[10px] text-slate-500">{new Date(draft.created_at).toLocaleString()} · 仅限用户粘贴的本地会话文本</p><button type="button" onClick={() => void runReview()} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"><RotateCcw className="h-3.5 w-3.5" />我确认生成结构化审稿建议</button></div>}
    {review && <div className="mt-3 space-y-2"><p className="text-[11px] text-slate-500">{review.generation_mode === "llm" ? "模型个性化解释（事实边界仍由规则控制）" : review.generation_mode === "rules_fallback" ? "模型不可用，已使用基础规则降级" : "基础规则审稿"}</p>{review.revision_tasks.map((task) => <div key={task.task_id} className="rounded-lg border border-slate-200 p-2 text-[11px] dark:border-zinc-700"><p className={`font-semibold ${severityClass[task.finding.severity]}`}>{severityLabel[task.finding.severity]} · {task.finding.section}</p><p className="mt-1">{task.finding.issue}</p><p className="mt-1 text-slate-500">依据：{task.finding.basis} · {task.finding.classification}</p><p className="mt-1">建议：{task.finding.recommended_action}</p><div className="mt-2 flex gap-2"><button type="button" onClick={() => void changeTask(task.task_id, "accepted")} disabled={busy || task.status === "accepted"} className="inline-flex items-center gap-1 text-emerald-700 disabled:opacity-50 dark:text-emerald-300"><Check className="h-3.5 w-3.5" />接受</button><button type="button" onClick={() => void changeTask(task.task_id, "skipped")} disabled={busy || task.status === "skipped"} className="inline-flex items-center gap-1 text-slate-500 disabled:opacity-50"><X className="h-3.5 w-3.5" />跳过</button><span className="text-slate-500">当前：{task.status}</span></div></div>)}<button type="button" onClick={() => void previewRevision()} disabled={busy || !review.revision_tasks.some((task) => task.status === "accepted")} className="inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300">生成已接受任务的修订预览</button></div>}
    {revision && <div className="mt-3 rounded-xl border border-violet-200 p-3 text-xs dark:border-violet-900"><div className="flex items-center justify-between gap-2"><p className="font-semibold">修订预览 · v{revision.version}</p><button type="button" onClick={() => void copyRevision()} className="text-violet-700 dark:text-violet-300">复制文本</button></div><p className="mt-1 text-[10px] text-slate-500">原稿不会被覆盖；以下仅含已接受任务的建议，仍需人工核对。</p><details className="mt-2"><summary className="cursor-pointer font-semibold">查看变更摘要与差异</summary><ul className="mt-1 list-disc pl-4">{revision.change_summary.map((item) => <li key={item}>{item}</li>)}</ul><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[10px] dark:bg-zinc-950">{revision.diff_preview}</pre></details><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] leading-5 dark:bg-zinc-950">{revision.content}</pre></div>}
    {drafts.length > 1 && <p className="mt-3 text-[10px] text-slate-500">已恢复 {drafts.length} 个本地初稿版本；当前展示最近版本。</p>}
  </section>;
}
