import type { AnalysisClassification } from "@/lib/api/research";

const BADGE_META: Record<AnalysisClassification, { label: string; className: string }> = {
  fact: {
    label: "已保存事实",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  inference: {
    label: "建议·推断",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
  },
  to_verify: {
    label: "待核对",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  },
};

/** Read-only badge for the shared fact / inference / to_verify boundary. */
export function ClassificationBadge({ classification }: { classification: AnalysisClassification }) {
  const meta = BADGE_META[classification];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.className}`}>
      {meta.label}
    </span>
  );
}