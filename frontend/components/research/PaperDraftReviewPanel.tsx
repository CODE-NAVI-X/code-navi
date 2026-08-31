"use client";

import { Check, Clipboard, Download, FileCheck2, FilePenLine, Loader2, Pencil, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  applyRevisionSuggestion, createPaperDraft, createPaperExportPackage, createPaperReview, createRevisionSuggestion, createSubmissionReadiness,
  getSubmissionProfile, listPaperDrafts, listPaperReviews, listPaperRevisions, listRevisionSuggestions, listSubmissionReadiness, saveSubmissionProfile,
  updatePaperRevisionTask, type PaperDraft, type PaperReview, type PaperRevision, type RevisionSuggestion,
  type ReviewSeverity, type SubmissionProfile, type SubmissionReadinessCheck, type SubmissionReadinessItem,
} from "@/lib/api/research";
import { CitationScaffoldPanel } from "./CitationScaffoldPanel";
import { GenerationFailure, isGenerationFailure } from "./generationUi";

const severityLabel: Record<ReviewSeverity, string> = { blocker: "阻塞", major: "重要", minor: "一般", suggestion: "建议" };
const severityClass: Record<ReviewSeverity, string> = { blocker: "text-rose-700 dark:text-rose-300", major: "text-orange-700 dark:text-orange-300", minor: "text-amber-700 dark:text-amber-300", suggestion: "text-sky-700 dark:text-sky-300" };
const readinessLabel = { not_ready: "尚未就绪", needs_review: "需要人工复核", checklist_complete: "检查清单已完成" } as const;
const readinessClass = { not_ready: "text-rose-700 dark:text-rose-300", needs_review: "text-amber-700 dark:text-amber-300", checklist_complete: "text-emerald-700 dark:text-emerald-300" } as const;

function ReadinessItems({ items }: { items: SubmissionReadinessItem[] }) {
  return <ul className="mt-1 space-y-1">{items.map((item) => <li key={item.id} className="rounded bg-slate-50 p-2 dark:bg-zinc-950"><p>{item.message}</p><p className="mt-1 text-[10px] text-slate-500">依据：{item.basis}</p></li>)}</ul>;
}

export function PaperDraftReviewPanel({ conversationId }: { conversationId: string }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [format, setFormat] = useState<"markdown" | "plain_text">("markdown");
  const [drafts, setDrafts] = useState<PaperDraft[]>([]);
  const [draft, setDraft] = useState<PaperDraft | null>(null);
  const [review, setReview] = useState<PaperReview | null>(null);
  const [revision, setRevision] = useState<PaperRevision | null>(null);
  const [revisions, setRevisions] = useState<PaperRevision[]>([]);
  const [suggestions, setSuggestions] = useState<Record<string, RevisionSuggestion>>({});
  const [editingSuggestionId, setEditingSuggestionId] = useState<string | null>(null);
  const [editedCandidate, setEditedCandidate] = useState("");
  const [readiness, setReadiness] = useState<SubmissionReadinessCheck | null>(null);
  const [submissionProfile, setSubmissionProfile] = useState<SubmissionProfile | null>(null);
  const [targetVenue, setTargetVenue] = useState("");
  const [anonymityRequired, setAnonymityRequired] = useState<"unset" | "true" | "false">("unset");
  const [lengthOrSectionRequirements, setLengthOrSectionRequirements] = useState("");
  const [ethicsAndDataRequirements, setEthicsAndDataRequirements] = useState("");
  const [submissionNotes, setSubmissionNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState(false);
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([listPaperDrafts(conversationId), getSubmissionProfile(conversationId)]).then(async ([saved, profile]) => {
      if (!active) return;
      setDrafts(saved);
      setSubmissionProfile(profile);
      setTargetVenue(profile?.target_venue ?? "");
      setAnonymityRequired(profile?.anonymity_required === true ? "true" : profile?.anonymity_required === false ? "false" : "unset");
      setLengthOrSectionRequirements(profile?.length_or_section_requirements ?? "");
      setEthicsAndDataRequirements(profile?.ethics_and_data_requirements ?? "");
      setSubmissionNotes(profile?.user_notes ?? "");
      const latest = saved[0] ?? null;
      setDraft(latest);
      if (latest) {
        const [reviews, revisions, checks] = await Promise.all([listPaperReviews(latest.draft_id), listPaperRevisions(latest.draft_id), listSubmissionReadiness(latest.draft_id)]);
        const latestReview = reviews[0];
        const savedSuggestions = latestReview ? await Promise.all(latestReview.revision_tasks.map(async (task) => [task.task_id, (await listRevisionSuggestions(latestReview.review_id, task.task_id))[0]] as const)) : [];
        const recoveredSuggestions = Object.fromEntries(savedSuggestions.filter((entry): entry is [string, RevisionSuggestion] => Boolean(entry[1])));
        if (active) { setReview(latestReview ?? null); setRevision(revisions[0] ?? null); setRevisions(revisions); setReadiness(checks[0] ?? null); setSuggestions(recoveredSuggestions); }
      }
    }).catch((value: unknown) => active && setError(value instanceof Error ? value.message : "无法恢复本地初稿。")).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [conversationId]);

  async function submitDraft() {
    if (!title.trim() || !content.trim()) { setError("请填写标题和初稿文本后再提交。"); return; }
    setBusy(true); setError(null);
    try {
      const saved = await createPaperDraft(conversationId, { title, content, format });
      setDraft(saved); setDrafts((current) => [saved, ...current]); setReview(null); setRevision(null); setRevisions([]); setSuggestions({}); setReadiness(null);
    } catch (value) { setError(value instanceof Error ? value.message : "保存初稿失败。请重试。"); } finally { setBusy(false); }
  }
  async function runReview() {
    if (!draft) return;
    setBusy(true); setError(null); setFailure(false); setRetryAction(null);
    try { setReview(await createPaperReview(draft.draft_id)); setRevision(null); }
    catch (value) {
      setFailure(isGenerationFailure(value));
      setRetryAction(() => () => void runReview());
      setError(value instanceof Error ? value.message : "生成审稿建议失败。请重试。");
    } finally { setBusy(false); }
  }
  async function changeTask(taskId: string, status: "accepted" | "skipped") {
    if (!review) return;
    setBusy(true); setError(null);
    try { setReview(await updatePaperRevisionTask(review.review_id, taskId, status)); }
    catch (value) { setError(value instanceof Error ? value.message : "保存修订决定失败。请重试。"); } finally { setBusy(false); }
  }
  function previewRevision() {
    setNotice("请使用下方的“逐段候选改写”；只有再次确认候选后才会创建新版本。");
  }
  async function generateSuggestion(taskId: string) {
    if (!review) return;
    setBusy(true); setError(null); setFailure(false); setRetryAction(null);
    try { const saved = await createRevisionSuggestion(review.review_id, taskId); setSuggestions((current) => ({ ...current, [taskId]: saved })); }
    catch (value) {
      setFailure(isGenerationFailure(value));
      setRetryAction(() => () => void generateSuggestion(taskId));
      setError(value instanceof Error ? value.message : "无法生成候选改写。请重试。");
    } finally { setBusy(false); }
  }
  async function applySuggestion(taskId: string, action: "accepted" | "skipped") {
    const suggestion = suggestions[taskId]; if (!suggestion) return;
    setBusy(true); setError(null);
    try {
      const saved = await applyRevisionSuggestion(suggestion.suggestion_id, action, action === "accepted" ? editedCandidate || undefined : undefined);
      if (saved) { setRevision(saved); setRevisions((current) => [saved, ...current]); }
      else if (action === "skipped") { setReview((current) => current ? { ...current, revision_tasks: current.revision_tasks.map((task) => task.task_id === taskId ? { ...task, status: "skipped" } : task) } : current); }
      setEditingSuggestionId(null); setEditedCandidate("");
    } catch (value) { setError(value instanceof Error ? value.message : "保存候选改写失败。请重试。"); } finally { setBusy(false); }
  }
  async function copyRevision() {
    if (!revision) return;
    try { await navigator.clipboard.writeText(revision.content); }
    catch { setError("复制失败，请手动选择文本复制。"); }
  }
  async function runSubmissionReadiness() {
    if (!draft) return;
    setBusy(true); setError(null);
    try { setReadiness(await createSubmissionReadiness(draft.draft_id)); }
    catch (value) { setError(value instanceof Error ? value.message : "投稿前检查失败。请重试。"); } finally { setBusy(false); }
  }
  async function persistSubmissionProfile() {
    setBusy(true); setError(null);
    try {
      const saved = await saveSubmissionProfile(conversationId, {
        target_venue: targetVenue.trim() || null,
        anonymity_required: anonymityRequired === "unset" ? null : anonymityRequired === "true",
        length_or_section_requirements: lengthOrSectionRequirements.trim() || null,
        ethics_and_data_requirements: ethicsAndDataRequirements.trim() || null,
        user_notes: submissionNotes.trim() || null,
      });
      setSubmissionProfile(saved);
      setNotice("投稿准备档案已保存。它只记录你已知的约束，不会联网推断会议或期刊要求。");
    } catch (value) { setError(value instanceof Error ? value.message : "保存投稿准备档案失败。请重试。"); } finally { setBusy(false); }
  }
  async function exportAssistantPackage() {
    if (!draft) return;
    setBusy(true); setError(null);
    try {
      const packageData = await createPaperExportPackage(draft.draft_id);
      for (const file of packageData.files) {
        const href = URL.createObjectURL(new Blob([file.content], { type: file.content_type }));
        const link = document.createElement("a");
        link.href = href; link.download = file.filename; link.click();
        URL.revokeObjectURL(href);
      }
      setNotice("投稿前辅助包已在浏览器中生成；仅含安全摘要与待核对清单，不含初稿或修订稿全文。");
    } catch (value) { setError(value instanceof Error ? value.message : "导出投稿前辅助包失败。请重试。"); } finally { setBusy(false); }
  }

  return <section className="rounded-2xl border border-violet-200 bg-white p-4 shadow-sm dark:border-violet-900/70 dark:bg-zinc-900/80">
    <div className="flex items-center gap-3"><span className="rounded-xl bg-violet-100 p-2 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300"><FilePenLine className="h-4 w-4" /></span><div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700 dark:text-violet-300">Local draft review</p><h2 className="mt-1 text-sm font-bold">论文初稿与结构化审稿</h2></div></div>
    <p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">仅接受当前本地会话主动粘贴的 Markdown/纯文本。DOCX/PDF 导入、最终格式导出留待后续；不会联网、写入项目、自动投稿，也不能替代导师或同行评审。</p>
    {loading && <p className="mt-3 text-[11px] text-slate-500 dark:text-zinc-400">正在恢复本地初稿与修订记录…</p>}
    <details open className="mt-3 rounded-xl border border-violet-100 dark:border-violet-950">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-800 dark:text-zinc-200">投稿准备档案（用户已知要求）</summary>
      <div className="border-t border-violet-100/70 px-2 pb-3 dark:border-violet-950/60">
        <p className="mt-2 text-[11px] leading-5 text-slate-500">本地规则辅助，不代表满足任何会议或期刊要求；只在你保存档案和确认检查后使用，不会联网抓取投稿规则。</p>
        <div className="mt-2 grid gap-2">
          <input value={targetVenue} onChange={(event) => setTargetVenue(event.target.value)} maxLength={300} placeholder="目标投稿方向、会议或期刊（可留空，系统将标为待确认）" className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" />
          <select value={anonymityRequired} onChange={(event) => setAnonymityRequired(event.target.value as "unset" | "true" | "false")} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950"><option value="unset">匿名要求：待确认</option><option value="true">匿名要求：需要匿名</option><option value="false">匿名要求：暂不要求匿名</option></select>
          <textarea value={lengthOrSectionRequirements} onChange={(event) => setLengthOrSectionRequirements(event.target.value)} maxLength={1000} rows={2} placeholder="已知篇幅或章节要求（可留空）" className="resize-y rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" />
          <textarea value={ethicsAndDataRequirements} onChange={(event) => setEthicsAndDataRequirements(event.target.value)} maxLength={1000} rows={2} placeholder="已知伦理、匿名化或数据许可要求（可留空）" className="resize-y rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" />
          <textarea value={submissionNotes} onChange={(event) => setSubmissionNotes(event.target.value)} maxLength={1500} rows={2} placeholder="作者备注（仅本地会话保存）" className="resize-y rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" />
        </div>
        <button type="button" onClick={() => void persistSubmissionProfile()} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300"><FileCheck2 className="h-3.5 w-3.5" />保存投稿准备档案</button>
        {submissionProfile && <p className="mt-1 text-[10px] text-slate-500">已恢复本地档案 · 最近更新 {new Date(submissionProfile.updated_at).toLocaleString()}</p>}
      </div>
    </details>
    <details open className="mt-3 rounded-xl border border-violet-100 dark:border-violet-950">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-800 dark:text-zinc-200">引用占位（仅本会话已保存来源，需手动选择）</summary>
      <div className="border-t border-violet-100/70 px-2 pb-2 dark:border-violet-950/60">
        <CitationScaffoldPanel conversationId={conversationId} />
      </div>
    </details>
    <details open className="mt-3 rounded-xl border border-violet-100 dark:border-violet-950">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-800 dark:text-zinc-200">初稿提交与结构化审稿</summary>
      <div className="border-t border-violet-100/70 px-2 pb-2 dark:border-violet-950/60">
    <div className="mt-3 grid gap-2"><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} placeholder="初稿标题" className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950" /><select value={format} onChange={(event) => setFormat(event.target.value as "markdown" | "plain_text")} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950"><option value="markdown">Markdown</option><option value="plain_text">纯文本</option></select><textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={60000} rows={8} placeholder="粘贴你的初稿。只提交你愿意在当前本地会话中分析的文本。" className="resize-y rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs leading-5 dark:border-zinc-700 dark:bg-zinc-950" /></div>
    <button type="button" onClick={() => void submitDraft()} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clipboard className="h-3.5 w-3.5" />}提交本地初稿</button>
    {error &&
      (failure && retryAction ? (
        <GenerationFailure error={error} busy={busy} hasLastSuccess={review !== null} onRetry={retryAction} />
      ) : (
        <p role="alert" className="mt-2 text-sm text-rose-600">{error}</p>
      ))}
    {notice && <p role="status" className="mt-2 rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-xs text-sky-800 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300">{notice}</p>}
    {draft && <div className="mt-4 rounded-xl border border-violet-100 p-3 text-xs dark:border-violet-950"><p className="font-semibold">已保存：{draft.title} · v{draft.version}</p><p className="mt-1 text-[10px] text-slate-500">{new Date(draft.created_at).toLocaleString()} · 仅限用户粘贴的本地会话文本</p><button type="button" onClick={() => void runReview()} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"><RotateCcw className="h-3.5 w-3.5" />我确认生成结构化审稿建议</button></div>}
    {review && <div className="mt-3 space-y-2"><p className="text-[11px] text-slate-500">{review.generation_mode === "llm" ? "模型个性化解释（事实边界仍由规则控制）" : "基础规则审稿"}</p>{review.revision_tasks.map((task) => <div key={task.task_id} className="rounded-lg border border-slate-200 p-2 text-[11px] dark:border-zinc-700"><p className={`font-semibold ${severityClass[task.finding.severity]}`}>{severityLabel[task.finding.severity]} · {task.finding.section}</p><p className="mt-1">{task.finding.issue}</p><p className="mt-1 text-slate-500">依据：{task.finding.basis}</p><p className="mt-1">建议：{task.finding.recommended_action}</p><div className="mt-2 flex gap-2"><button type="button" onClick={() => void changeTask(task.task_id, "accepted")} disabled={busy || task.status === "accepted"} className="inline-flex items-center gap-1 text-emerald-700 disabled:opacity-50 dark:text-emerald-300"><Check className="h-3.5 w-3.5" />接受</button><button type="button" onClick={() => void changeTask(task.task_id, "skipped")} disabled={busy || task.status === "skipped"} className="inline-flex items-center gap-1 text-slate-500 disabled:opacity-50"><X className="h-3.5 w-3.5" />跳过</button><span className="text-slate-500">当前：{task.status}</span></div></div>)}<button type="button" onClick={() => void previewRevision()} disabled={busy || !review.revision_tasks.some((task) => task.status === "accepted")} className="inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300">生成已接受任务的修订预览</button></div>}
    {review && review.revision_tasks.filter((task) => task.status === "accepted").map((task) => {
      const suggestion = suggestions[task.task_id];
      return <div key={`suggestion-${task.task_id}`} className="mt-3 rounded-xl border border-sky-200 p-3 text-xs dark:border-sky-900">
        <p className="font-semibold">逐段候选改写 · {task.finding.section}</p>
        <p className="mt-1 text-[10px] text-slate-500">候选改写是建议，不自动覆盖原稿；仅用户接受后才创建新版本。</p>
        {!suggestion && <button type="button" onClick={() => void generateSuggestion(task.task_id)} disabled={busy} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-sky-200 px-2.5 py-1.5 text-[11px] font-semibold text-sky-800 disabled:opacity-50 dark:border-sky-900 dark:text-sky-300"><Pencil className="h-3.5 w-3.5" />生成候选改写</button>}
        {suggestion && <div className="mt-2 space-y-2"><p className="text-[10px] text-slate-500">{suggestion.generation_mode === "llm" ? "模型个性化建议（规则已校验）" : "基础规则"}</p><p><strong>原文片段：</strong>{suggestion.original_excerpt}</p><p><strong>依据：</strong>{suggestion.basis}</p><p><strong>修改理由：</strong>{suggestion.rationale}</p><textarea value={editingSuggestionId === suggestion.suggestion_id ? editedCandidate : suggestion.candidate_text} onChange={(event) => { setEditingSuggestionId(suggestion.suggestion_id); setEditedCandidate(event.target.value); }} rows={6} className="w-full resize-y rounded border border-slate-200 bg-white p-2 text-[11px] dark:border-zinc-700 dark:bg-zinc-950" /><p className="text-[10px] text-slate-500">缺证据内容必须保留待验证占位；不会自动检索、写文件、安装或执行。</p><div className="flex gap-2"><button type="button" onClick={() => void applySuggestion(task.task_id, "accepted")} disabled={busy} className="text-emerald-700 dark:text-emerald-300">接受并创建版本</button><button type="button" onClick={() => void applySuggestion(task.task_id, "skipped")} disabled={busy} className="text-slate-500">跳过候选</button></div></div>}
      </div>;
    })}
      </div>
    </details>
    <details open className="mt-3 rounded-xl border border-violet-100 dark:border-violet-950">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-800 dark:text-zinc-200">修订预览与投稿前检查</summary>
      <div className="border-t border-violet-100/70 px-2 pb-2 dark:border-violet-950/60">
    {!revision && !readiness && <p className="mt-2 text-[11px] text-slate-500 dark:text-zinc-400">接受审稿任务并生成候选改写后，这里会展示修订预览；投稿前检查需你再次确认后才会执行。</p>}
    {revision && <div className="mt-3 rounded-xl border border-violet-200 p-3 text-xs dark:border-violet-900"><div className="flex items-center justify-between gap-2"><p className="font-semibold">修订预览 · v{revision.version}</p><button type="button" onClick={() => void copyRevision()} className="text-violet-700 dark:text-violet-300">复制文本</button></div><p className="mt-1 text-[10px] text-slate-500">原稿不会被覆盖；以下仅含已接受任务的建议，仍需人工核对。</p><details className="mt-2"><summary className="cursor-pointer font-semibold">查看变更摘要与差异</summary><ul className="mt-1 list-disc pl-4">{revision.change_summary.map((item) => <li key={item}>{item}</li>)}</ul><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[10px] dark:bg-zinc-950">{revision.diff_preview}</pre></details><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] leading-5 dark:bg-zinc-950">{revision.content}</pre><button type="button" onClick={() => void runSubmissionReadiness()} disabled={busy} className="mt-3 inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300"><FileCheck2 className="h-3.5 w-3.5" />我确认执行投稿前检查</button></div>}
    {revisions.length > 1 && <details className="mt-2 text-xs"><summary className="cursor-pointer font-semibold">历史修订版本（{revisions.length}）</summary><ul className="mt-1 list-disc pl-4">{revisions.map((item) => <li key={item.revision_id}>v{item.version} · {item.change_summary.join("；")}</li>)}</ul></details>}
    {readiness && <div className="mt-3 rounded-xl border border-amber-200 p-3 text-xs dark:border-amber-900"><p className={`font-semibold ${readinessClass[readiness.readiness_status]}`}>投稿前检查：{readinessLabel[readiness.readiness_status]}</p><p className="mt-1 text-[10px] text-slate-500">只检查本地已保存的草稿、修订预览和证据状态；不联网、不投稿，也不代表可被接收。</p>{readiness.blockers.length > 0 && <details className="mt-2" open><summary className="cursor-pointer font-semibold text-rose-700 dark:text-rose-300">阻塞项（{readiness.blockers.length}）</summary><ReadinessItems items={readiness.blockers} /></details>}{readiness.warnings.length > 0 && <details className="mt-2"><summary className="cursor-pointer font-semibold">警告（{readiness.warnings.length}）</summary><ReadinessItems items={readiness.warnings} /></details>}<details className="mt-2"><summary className="cursor-pointer font-semibold">人工核验项（{readiness.manual_checks.length}）</summary><ReadinessItems items={readiness.manual_checks} /></details><button type="button" onClick={() => void exportAssistantPackage()} disabled={busy} className="mt-3 inline-flex items-center gap-1 rounded-lg border border-violet-200 px-2.5 py-1.5 text-[11px] font-semibold text-violet-800 disabled:opacity-50 dark:border-violet-900 dark:text-violet-300"><Download className="h-3.5 w-3.5" />我确认导出投稿前辅助包</button><p className="mt-1 text-[10px] text-slate-500">仅导出研究与计划摘要、投稿档案、检查清单、修订依据和已选引用摘要；不含初稿/修订稿全文，均待作者或导师核对，不是最终投稿格式。</p></div>}
    {drafts.length > 1 && <p className="mt-3 text-[10px] text-slate-500">已恢复 {drafts.length} 个本地初稿版本；当前展示最近版本。</p>}
      </div>
    </details>
  </section>;
}
