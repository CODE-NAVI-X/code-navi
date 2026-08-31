"use client";

import {
  CheckCircle2,
  ClipboardCheck,
  Copy,
  ExternalLink,
  Loader2,
  Quote,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  createCitationQualityCheck,
  createSelectedCitation,
  getReferenceDraftPackage,
  listCitationCandidates,
  listCitationQualityChecks,
  listSelectedCitations,
  updateSelectedCitation,
  type CitationCandidate,
  type CitationQualityCheck,
  type CitationQualityIssue,
  type CitationTargetDocument,
  type ReferenceDraftPackage,
  type SelectedCitation,
} from "@/lib/api/research";

const sectionOptions = ["引言", "相关工作", "方法", "实验", "讨论", "结论"];

export function CitationScaffoldPanel({ conversationId }: { conversationId: string }) {
  const [candidates, setCandidates] = useState<CitationCandidate[]>([]);
  const [selected, setSelected] = useState<SelectedCitation[]>([]);
  const [referencePackage, setReferencePackage] = useState<ReferenceDraftPackage | null>(null);
  const [qualityChecks, setQualityChecks] = useState<CitationQualityCheck[]>([]);
  const [qualityStale, setQualityStale] = useState(false);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [targetDocument, setTargetDocument] =
    useState<CitationTargetDocument>("paper_blueprint");
  const [targetSection, setTargetSection] = useState("相关工作");
  const [anchor, setAnchor] = useState("相关工作-1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function restore() {
    const restored = await restoreCitationWorkspace(conversationId);
    setCandidates(restored.candidates);
    setSelected(restored.selected);
    setReferencePackage(restored.referencePackage);
    setQualityChecks(restored.qualityChecks);
    setQualityStale(citationCheckIsStale(restored.qualityChecks[0], restored.selected));
  }

  useEffect(() => {
    let active = true;
    void restoreCitationWorkspace(conversationId)
      .then((restored) => {
        if (!active) return;
        setCandidates(restored.candidates);
        setSelected(restored.selected);
        setReferencePackage(restored.referencePackage);
        setQualityChecks(restored.qualityChecks);
        setQualityStale(citationCheckIsStale(restored.qualityChecks[0], restored.selected));
      })
      .catch((value: unknown) => {
        if (active) {
          setError(value instanceof Error ? value.message : "无法恢复已保存证据来源。");
        }
      });
    return () => {
      active = false;
    };
  }, [conversationId]);

  async function addCitation() {
    const candidate = candidates.find((item) => item.citation_id === chosenId);
    if (!candidate) {
      setError("请先主动选择一篇已保存的证据来源。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createSelectedCitation(conversationId, {
        evidence_bundle_id: candidate.evidence_bundle_id,
        paper_url: candidate.url,
        target_document: targetDocument,
        target_section: targetSection,
        paragraph_anchor: anchor || targetSection + "-1",
        user_note: note || null,
      });
      await restore();
      setChosenId(null);
      setNote("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "创建引用占位失败。请重试。");
    } finally {
      setBusy(false);
    }
  }

  async function setCitationStatus(
    selectedCitationId: string,
    status: "inserted" | "skipped",
  ) {
    setBusy(true);
    setError(null);
    try {
      await updateSelectedCitation(selectedCitationId, status);
      await restore();
    } catch (value) {
      setError(value instanceof Error ? value.message : "更新引用状态失败。请重试。");
    } finally {
      setBusy(false);
    }
  }

  async function runQualityCheck() {
    setChecking(true);
    setError(null);
    try {
      const created = await createCitationQualityCheck(conversationId);
      setQualityChecks((current) => [created, ...current]);
      setQualityStale(false);
    } catch (value) {
      setError(value instanceof Error ? value.message : "引用完整性检查失败。请重试。");
    } finally {
      setChecking(false);
    }
  }

  async function copyReferenceDraft() {
    if (!referencePackage?.copy_text) {
      setError("当前没有可复制的参考文献草案。请先主动选择来源。");
      return;
    }
    setError(null);
    try {
      if (!navigator.clipboard) {
        throw new Error("当前浏览器不支持剪贴板 API，请手动选择草案文本复制。");
      }
      await navigator.clipboard.writeText(referencePackage.copy_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (value) {
      setError(value instanceof Error ? value.message : "复制参考文献草案失败。");
    }
  }

  const activeSelected = selected.filter((item) => item.status !== "skipped");
  const latestCheck = qualityChecks[0] ?? null;

  return (
    <section className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50/40 p-3 text-xs dark:border-cyan-900/70 dark:bg-cyan-950/10">
      <PanelIntroduction />
      {error && (
        <p role="alert" className="mt-2 text-rose-600">
          {error}
        </p>
      )}

      <CandidateSelector
        conversationId={conversationId}
        candidates={candidates}
        chosenId={chosenId}
        targetDocument={targetDocument}
        targetSection={targetSection}
        anchor={anchor}
        note={note}
        busy={busy}
        onChoose={setChosenId}
        onTargetDocument={setTargetDocument}
        onTargetSection={(section) => {
          setTargetSection(section);
          setAnchor(section + "-1");
        }}
        onAnchor={setAnchor}
        onNote={setNote}
        onAdd={() => void addCitation()}
      />

      {activeSelected.length > 0 && (
        <SelectedCitationList
          selected={activeSelected}
          busy={busy}
          onStatus={(selectedCitationId, status) =>
            void setCitationStatus(selectedCitationId, status)
          }
        />
      )}

      <CitationQualityPanel
        check={latestCheck}
        stale={qualityStale}
        checking={checking}
        busy={busy}
        onRun={() => void runQualityCheck()}
      />

      {referencePackage && (
        <ReferenceDraftList
          referencePackage={referencePackage}
          copied={copied}
          onCopy={() => void copyReferenceDraft()}
        />
      )}
    </section>
  );
}

async function restoreCitationWorkspace(conversationId: string) {
  const [candidates, selected, referencePackage, qualityChecks] = await Promise.all([
    listCitationCandidates(conversationId),
    listSelectedCitations(conversationId),
    getReferenceDraftPackage(conversationId),
    listCitationQualityChecks(conversationId),
  ]);
  return { candidates, selected, referencePackage, qualityChecks };
}

function PanelIntroduction() {
  return (
    <>
      <div className="flex items-center gap-2">
        <Quote className="h-4 w-4 text-cyan-700 dark:text-cyan-300" />
        <div>
          <p className="font-semibold">受限证据引用与完整性检查</p>
          <p className="mt-0.5 text-[10px] text-slate-500">
            仅使用当前会话已保存且由你明确选择的来源；章节映射与参考文献草案需要作者或导师核对。
          </p>
        </div>
      </div>
      <p className="mt-2 text-[10px] leading-5 text-slate-600 dark:text-zinc-400">
        不会自动联网、补造元数据、选择文献、插入或改写原稿。检查结果也不代表引用正确或论文可以投稿。
      </p>
    </>
  );
}

interface CandidateSelectorProps {
  conversationId: string;
  candidates: CitationCandidate[];
  chosenId: string | null;
  targetDocument: CitationTargetDocument;
  targetSection: string;
  anchor: string;
  note: string;
  busy: boolean;
  onChoose: (citationId: string) => void;
  onTargetDocument: (target: CitationTargetDocument) => void;
  onTargetSection: (section: string) => void;
  onAnchor: (anchor: string) => void;
  onNote: (note: string) => void;
  onAdd: () => void;
}

function CandidateSelector(props: CandidateSelectorProps) {
  if (props.candidates.length === 0) {
    return (
      <p className="mt-2 rounded bg-white/70 p-2 text-slate-500 dark:bg-zinc-950/70">
        当前没有可引用的已保存证据来源。请先由你主动完成受限检索。
      </p>
    );
  }
  return (
    <>
      <div className="mt-3 space-y-2">
        {props.candidates.map((candidate) => (
          <label
            key={candidate.citation_id}
            className="flex cursor-pointer gap-2 rounded-lg border border-cyan-100 bg-white/80 p-2 dark:border-cyan-950 dark:bg-zinc-950/70"
          >
            <input
              type="radio"
              name={"citation-" + props.conversationId}
              checked={props.chosenId === candidate.citation_id}
              onChange={() => props.onChoose(candidate.citation_id)}
              className="mt-1 accent-cyan-700"
            />
            <CandidateSummary candidate={candidate} />
          </label>
        ))}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <select
          value={props.targetDocument}
          onChange={(event) =>
            props.onTargetDocument(event.target.value as CitationTargetDocument)
          }
          className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950"
        >
          <option value="paper_blueprint">论文蓝图</option>
          <option value="paper_draft">论文初稿</option>
          <option value="paper_revision">修订稿预览</option>
        </select>
        <select
          value={props.targetSection}
          onChange={(event) => props.onTargetSection(event.target.value)}
          className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950"
        >
          {sectionOptions.map((section) => (
            <option key={section}>{section}</option>
          ))}
        </select>
        <input
          value={props.anchor}
          onChange={(event) => props.onAnchor(event.target.value)}
          maxLength={300}
          placeholder="建议插入位置，例如 相关工作-1"
          className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950"
        />
        <input
          value={props.note}
          onChange={(event) => props.onNote(event.target.value)}
          maxLength={1000}
          placeholder="可选：给自己或导师的核对说明"
          className="rounded border border-cyan-200 bg-white p-2 text-xs dark:border-cyan-900 dark:bg-zinc-950"
        />
      </div>
      <button
        type="button"
        onClick={props.onAdd}
        disabled={props.busy || !props.chosenId}
        className="mt-2 inline-flex items-center gap-1 rounded-lg border border-cyan-300 px-2.5 py-1.5 text-[11px] font-semibold text-cyan-800 disabled:opacity-50 dark:border-cyan-800 dark:text-cyan-300"
      >
        {props.busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Quote className="h-3.5 w-3.5" />
        )}
        生成引用占位与参考文献雏形
      </button>
    </>
  );
}

function CandidateSummary({ candidate }: { candidate: CitationCandidate }) {
  const metadata = [
    candidate.authors.join("、") || "作者待核对",
    candidate.year ?? "年份待核对",
    candidate.source_name || "来源待核对",
  ].join(" · ");
  const scope =
    candidate.abstract_scope === "metadata_and_abstract" ? "元数据与摘要" : "仅元数据";
  return (
    <span className="min-w-0 flex-1">
      <span className="font-semibold">{candidate.paper_title}</span>
      <span className="mt-1 block text-[10px] text-slate-500">
        {metadata} · {scope}
      </span>
      <a
        href={candidate.url}
        target="_blank"
        rel="noreferrer"
        onClick={(event) => event.stopPropagation()}
        className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-sky-700 underline dark:text-sky-300"
      >
        查看已保存来源 <ExternalLink className="h-3 w-3" />
      </a>
    </span>
  );
}

function SelectedCitationList({
  selected,
  busy,
  onStatus,
}: {
  selected: SelectedCitation[];
  busy: boolean;
  onStatus: (selectedCitationId: string, status: "inserted" | "skipped") => void;
}) {
  return (
    <div className="mt-3 space-y-2">
      <p className="font-semibold">已选择的引用占位</p>
      {selected.map((item) => (
        <div
          key={item.selected_citation_id}
          className="rounded border border-cyan-100 bg-white/80 p-2 dark:border-cyan-950 dark:bg-zinc-950/70"
        >
          <p>
            <code>{item.citation_placeholder}</code> → {item.target_document} /{" "}
            {item.target_section} / {item.paragraph_anchor}
          </p>
          <p className="mt-1 text-[10px] text-slate-500">
            {item.citation.paper_title} · {item.citation.abstract_scope}
          </p>
          {item.reference_entry.to_verify_items.length > 0 && (
            <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
              待核对：{item.reference_entry.to_verify_items.join("；")}
            </p>
          )}
          <div className="mt-1 flex flex-wrap gap-3 text-[10px]">
            {item.status === "inserted" ? (
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> 已由用户标记为人工插入
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onStatus(item.selected_citation_id, "inserted")}
                disabled={busy}
                className="inline-flex items-center gap-1 font-semibold text-cyan-700 dark:text-cyan-300"
              >
                <CheckCircle2 className="h-3 w-3" /> 标记为已人工插入
              </button>
            )}
            <button
              type="button"
              onClick={() => onStatus(item.selected_citation_id, "skipped")}
              disabled={busy}
              className="inline-flex items-center gap-1 text-slate-500"
            >
              <X className="h-3 w-3" /> 取消选择（不影响原稿）
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function CitationQualityPanel({
  check,
  stale,
  checking,
  busy,
  onRun,
}: {
  check: CitationQualityCheck | null;
  stale: boolean;
  checking: boolean;
  busy: boolean;
  onRun: () => void;
}) {
  return (
    <div className="mt-3 rounded-lg border border-sky-200 bg-white/80 p-2 dark:border-sky-950 dark:bg-zinc-950/70">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold">引用完整性与来源—章节映射</p>
          <p className="mt-0.5 text-[10px] text-slate-500">
            仅在你点击后检查当前选择；刷新只恢复历史结果，不会自动重跑。
          </p>
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={checking || busy}
          className="inline-flex items-center gap-1 rounded-lg bg-sky-700 px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50"
        >
          {checking ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ClipboardCheck className="h-3.5 w-3.5" />
          )}
          运行引用完整性检查
        </button>
      </div>
      {check && stale && (
        <p className="mt-2 text-[10px] text-amber-700 dark:text-amber-300">
          引用选择或人工插入状态已变化；下方是历史结果，请重新运行检查。
        </p>
      )}
      {check && <CitationQualityResult check={check} />}
    </div>
  );
}

function CitationQualityResult({ check }: { check: CitationQualityCheck }) {
  const statusText = {
    empty: "尚无已选来源",
    needs_review: "存在待核对项",
    review_ready: "可进入人工核验",
  }[check.quality_status];
  return (
    <div className="mt-3 space-y-2">
      <div className="grid gap-2 sm:grid-cols-3">
        <Metric label="检查状态" value={statusText} />
        <Metric
          label="已选 / 唯一来源"
          value={String(check.selected_source_count) + " / " + String(check.unique_source_count)}
        />
        <Metric
          label="核心章节映射可见度"
          value={String(check.core_section_coverage_percent) + "%"}
        />
      </div>
      {check.empty_state_message ? (
        <p className="rounded bg-slate-50 p-2 text-slate-600 dark:bg-zinc-900 dark:text-zinc-300">
          {check.empty_state_message}
        </p>
      ) : (
        <CoverageDetails check={check} />
      )}
      <IssueList title="未确认插入的占位" issues={check.uninserted_placeholders} />
      <IssueList title="重复选择" issues={check.duplicate_selections} />
      <IssueList title="元数据与信息范围缺口" issues={check.metadata_gaps} />
      <IssueList title="作者/导师核验清单" issues={check.author_verification_items} />
      <p className="rounded bg-amber-50 p-2 text-[10px] leading-5 text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
        {check.boundary_note}
      </p>
    </div>
  );
}

function CoverageDetails({ check }: { check: CitationQualityCheck }) {
  return (
    <>
      <p className="text-[10px] text-slate-500">
        该百分比只表示六个核心章节中已有多少章节建立来源映射，不代表这些章节必须引用，也不代表证据充分。
      </p>
      <div className="space-y-2">
        {check.coverage_items.map((item) => (
          <div
            key={item.target_document + "-" + item.target_section}
            className="rounded border border-sky-100 p-2 dark:border-sky-950"
          >
            <p className="font-semibold">
              {item.target_section} · {item.source_titles.length} 个来源
            </p>
            <p className="mt-1 text-[10px] text-slate-500">
              {item.source_titles.join("；")} · 信息范围：
              {item.information_scopes.join(" / ")}
            </p>
            <p className="mt-1 text-[10px] text-slate-500">依据：{item.basis}</p>
            {item.to_verify_items.length > 0 && (
              <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
                待核对：{item.to_verify_items.join("；")}
              </p>
            )}
          </div>
        ))}
      </div>
      {check.unmapped_core_sections.length > 0 && (
        <p className="text-[10px] text-slate-500">
          尚无来源映射（不等于必须补引用）：
          {check.unmapped_core_sections.join("、")}
        </p>
      )}
    </>
  );
}

function IssueList({ title, issues }: { title: string; issues: CitationQualityIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <details open className="rounded border border-amber-100 p-2 dark:border-amber-950">
      <summary className="cursor-pointer font-semibold">
        {title}（{issues.length}）
      </summary>
      <ul className="mt-2 space-y-1 text-[10px] leading-5">
        {issues.map((issue, index) => (
          <li
            key={
              issue.issue_code +
              "-" +
              issue.selected_citation_ids.join("-") +
              "-" +
              String(index)
            }
          >
            {issue.message}
            <span className="block text-slate-500">依据：{issue.basis}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function ReferenceDraftList({
  referencePackage,
  copied,
  onCopy,
}: {
  referencePackage: ReferenceDraftPackage;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <details className="mt-3" open>
      <summary className="cursor-pointer font-semibold">可核验参考文献草案（{referencePackage.entries.length}）</summary>
      <p className="mt-2 text-[10px] leading-5 text-amber-700 dark:text-amber-300">
        {referencePackage.boundary_note}
      </p>
      {referencePackage.empty_state_message && (
        <p className="mt-2 rounded bg-white/80 p-2 text-slate-600 dark:bg-zinc-950/70 dark:text-zinc-300">
          {referencePackage.empty_state_message}
        </p>
      )}
      {referencePackage.entries.length > 0 && (
        <button
          type="button"
          onClick={onCopy}
          className="mt-2 inline-flex items-center gap-1 rounded border border-cyan-300 bg-white px-2 py-1 font-medium text-cyan-800 hover:bg-cyan-50 dark:border-cyan-800 dark:bg-zinc-950 dark:text-cyan-200"
        >
          {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "已复制" : "复制文本草案"}
        </button>
      )}
      <ul className="mt-2 space-y-2">
        {referencePackage.entries.map((reference) => (
          <li
            key={reference.selected_citation_id}
            className="rounded bg-white/80 p-2 text-[11px] leading-5 dark:bg-zinc-950/70"
          >
            <p className="text-[10px] text-amber-700 dark:text-amber-300">
              {reference.format_notice}
            </p>
            <p>{reference.display_text}</p>
            <a
              href={reference.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-cyan-700 underline dark:text-cyan-300"
            >
              查看原始来源 <ExternalLink className="h-3 w-3" />
            </a>
            <p className="mt-1 text-[10px] text-slate-500">
              {reference.to_verify_items.length
                ? "待核对：" + reference.to_verify_items.join("；")
                : ""}
            </p>
          </li>
        ))}
      </ul>
      {referencePackage.verification_items.length > 0 && (
        <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 dark:border-amber-900 dark:bg-amber-950/20">
          <p className="font-semibold text-amber-800 dark:text-amber-200">作者 / 导师集中核验清单</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-amber-800 dark:text-amber-200">
            {referencePackage.verification_items.map((item) => (
              <li key={item.selected_citation_id}>
                {item.missing_fields.join("；")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-slate-50 p-2 dark:bg-zinc-900">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className="mt-0.5 font-semibold">{value}</p>
    </div>
  );
}

function citationCheckIsStale(
  check: CitationQualityCheck | undefined,
  selected: SelectedCitation[],
) {
  if (!check) return false;
  const active = selected.filter((item) => item.status !== "skipped");
  const checkedIds = new Set(
    check.coverage_items.flatMap((item) => item.selected_citation_ids),
  );
  const activeIds = new Set(active.map((item) => item.selected_citation_id));
  if (
    checkedIds.size !== activeIds.size ||
    [...activeIds].some((selectedId) => !checkedIds.has(selectedId))
  ) {
    return true;
  }
  const pendingIds = new Set(
    check.uninserted_placeholders.flatMap((item) => item.selected_citation_ids),
  );
  return active.some(
    (item) => (item.status !== "inserted") !== pendingIds.has(item.selected_citation_id),
  );
}
