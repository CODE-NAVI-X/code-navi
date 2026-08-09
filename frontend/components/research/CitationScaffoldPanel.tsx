"use client";

import { ExternalLink, Loader2, Quote, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  createSelectedCitation,
  listCitationCandidates,
  listReferenceEntryDrafts,
  listSelectedCitations,
  updateSelectedCitation,
  type CitationCandidate,
  type CitationTargetDocument,
  type ReferenceEntryDraft,
  type SelectedCitation,
} from "@/lib/api/research";

const sectionOptions = ["引言", "相关工作", "方法", "实验", "讨论", "结论"];

export function CitationScaffoldPanel({ conversationId }: { conversationId: string }) {
  const [candidates, setCandidates] = useState<CitationCandidate[]>([]);
  const [selected, setSelected] = useState<SelectedCitation[]>([]);
  const [references, setReferences] = useState<ReferenceEntryDraft[]>([]);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [targetDocument, setTargetDocument] = useState<CitationTargetDocument>("paper_blueprint");
  const [targetSection, setTargetSection] = useState("相关工作");
  const [anchor, setAnchor] = useState("相关工作-1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function restore() {
    const [savedCandidates, savedSelected, savedReferences] = await Promise.all([
      listCitationCandidates(conversationId),
      listSelectedCitations(conversationId),
      listReferenceEntryDrafts(conversationId),
    ]);
    setCandidates(savedCandidates);
    setSelected(savedSelected);
    setReferences(savedReferences);
  }

  useEffect(() => {
    let active = true;
    void Promise.all([
      listCitationCandidates(conversationId),
      listSelectedCitations(conversationId),
      listReferenceEntryDrafts(conversationId),
    ])
      .then(([savedCandidates, savedSelected, savedReferences]) => {
        if (!active) return;
        setCandidates(savedCandidates);
        setSelected(savedSelected);
        setReferences(savedReferences);
      })
      .catch((value: unknown) => {
        if (active) setError(value instanceof Error ? value.message : "无法恢复已保存证据来源。");
      });
    return () => { active = false; };
  }, [conversationId]);

  async function addCitation() {
    const candidate = candidates.find((item) => item.citation_id === chosenId);
    if (!candidate) { setError("请先主动选择一篇已保存的证据来源。"); return; }
    setBusy(true); setError(null);
    try {
      await createSelectedCitation(conversationId, {
        evidence_bundle_id: candidate.evidence_bundle_id,
        paper_url: candidate.url,
        target_document: targetDocument,
        target_section: targetSection,
        paragraph_anchor: anchor || `${targetSection}-1`,
        user_note: note || null,
      });
      await restore(); setChosenId(null); setNote("");
    } catch (value) { setError(value instanceof Error ? value.message : "创建引用占位失败。请重试。"); }
    finally { setBusy(false); }
  }

  async function skipCitation(selectedCitationId: string) {
    setBusy(true); setError(null);
    try { await updateSelectedCitation(selectedCitationId, "skipped"); await restore(); }
    catch (value) { setError(value instanceof Error ? value.message : "取消引用选择失败。请重试。"); }
    finally { setBusy(false); }
  }

  return <section className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50/40 p-3 text-xs dark:border-cyan-900/70 dark:bg-cyan-950/10">
    <div className="flex items-center gap-2"><Quote className="h-4 w-4 text-cyan-700 dark:text-cyan-300" /><div><p className="font-semibold">受限证据引用占位</p><p className="mt-0.5 text-[10px] text-slate-500">仅使用当前会话已保存的受限来源元数据/摘要；引用占位与参考文献雏形需要作者或导师核对。</p></div></div>
    <p className="mt-2 text-[10px] leading-5 text-slate-600 dark:text-zinc-400">不会自动联网、自动选择文献、自动插入或改写原稿，也不会自动投稿。缺失元数据会明确标为待核对。</p>
    {error && <p role="alert" className="mt-2 text-rose-600">{error}</p>}
    {candidates.length === 0 ? <p className="mt-2 rounded bg-white/70 p-2 text-slate-500 dark:bg-zinc-950/70">当前没有可引用的已保存证据来源。请先由你主动完成受限检索。</p> : <>
      <div className="mt-3 space-y-2">{candidates.map((candidate) => <label key={candidate.citation_id} className="flex cursor-pointer gap-2 rounded-lg border border-cyan-100 bg-white/80 p-2 dark:border-cyan-950 dark:bg-zinc-950/70"><input type="radio" name={`citation-${conversationId}`} checked={chosenId === candidate.citation_id} onChange={() => setChosenId(candidate.citation_id)} className="mt-1 accent-cyan-700" /><span className="min-w-0 flex-1"><span className="font-semibold">{candidate.paper_title}</span><span className="mt-1 block text-[10px] text-slate-500">{[candidate.authors.join("、") || "作者待核对", candidate.year ?? "年份待核对", candidate.source_name || "来源待核对"].join(" · ")} · {candidate.abstract_scope === "metadata_and_abstract" ? "元数据与摘要" : "仅元数据"}</span><a href={candidate.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-sky-700 underline dark:text-sky-300">查看已保存来源 <ExternalLink className="h-3 w-3" /></a></span></label>)}</div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2"><select value={targetDocument} onChange={(event) => setTargetDocument(event.target.value as CitationTargetDocument)} className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950"><option value="paper_blueprint">论文蓝图</option><option value="paper_draft">论文初稿</option><option value="paper_revision">修订稿预览</option></select><select value={targetSection} onChange={(event) => { setTargetSection(event.target.value); setAnchor(`${event.target.value}-1`); }} className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950">{sectionOptions.map((section) => <option key={section}>{section}</option>)}</select><input value={anchor} onChange={(event) => setAnchor(event.target.value)} maxLength={300} placeholder="建议插入位置，例如 相关工作-1" className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950" /><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="可选：给自己或导师的核对说明" className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950" /></div>
      <button type="button" onClick={() => void addCitation()} disabled={busy || !chosenId} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-cyan-300 px-2.5 py-1.5 text-[11px] font-semibold text-cyan-800 disabled:opacity-50 dark:border-cyan-800 dark:text-cyan-300">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Quote className="h-3.5 w-3.5" />}生成引用占位与参考文献雏形</button>
    </>}
    {selected.filter((item) => item.status !== "skipped").length > 0 && <div className="mt-3 space-y-2"><p className="font-semibold">已选择的引用占位</p>{selected.filter((item) => item.status !== "skipped").map((item) => <div key={item.selected_citation_id} className="rounded border border-cyan-100 bg-white/80 p-2 dark:border-cyan-950 dark:bg-zinc-950/70"><p><code>{item.citation_placeholder}</code> → {item.target_document} / {item.target_section} / {item.paragraph_anchor}</p><p className="mt-1 text-[10px] text-slate-500">{item.citation.paper_title} · {item.reference_entry.classification} · {item.citation.abstract_scope}</p>{item.reference_entry.to_verify_items.length > 0 && <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">待核对：{item.reference_entry.to_verify_items.join("；")}</p>}<button type="button" onClick={() => void skipCitation(item.selected_citation_id)} disabled={busy} className="mt-1 inline-flex items-center gap-1 text-[10px] text-slate-500"><X className="h-3 w-3" />取消选择（不影响原稿）</button></div>)}</div>}
    {references.length > 0 && <details className="mt-3" open><summary className="cursor-pointer font-semibold">参考文献雏形（{references.length}）</summary><ul className="mt-2 space-y-2">{references.map((reference) => <li key={reference.reference_id} className="rounded bg-white/80 p-2 text-[11px] leading-5 dark:bg-zinc-950/70"><code className="text-[10px] text-slate-500">{reference.citation_key}</code><p>{reference.display_text}</p><p className="mt-1 text-[10px] text-slate-500">信息范围：{reference.source_scope} · {reference.classification}{reference.to_verify_items.length ? ` · 待核对：${reference.to_verify_items.join("；")}` : ""}</p></li>)}</ul></details>}
  </section>;
}
