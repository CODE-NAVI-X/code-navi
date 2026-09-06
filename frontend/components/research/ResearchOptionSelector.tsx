"use client";

import { useMemo, useState } from "react";
import { ListChecks, Send } from "lucide-react";

/**
 * 解析姜姜回复中的选择题选项（A. / A、 / A： / A 端：），连续 ≥2 行归为一组。
 * 返回按出现顺序排列的选项组；没有选项组时返回空数组。
 */
export function parseOptionGroups(content: string): { options: { key: string; text: string }[] }[] {
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const OPTION_LINE = /^([A-Da-d])\s*(?:端)?[.、：:]\s*(.+)$/;
  const groups: { options: { key: string; text: string }[] }[] = [];
  let pending: { key: string; text: string }[] = [];
  const flush = () => {
    if (pending.length >= 2) {
      groups.push({ options: pending });
    }
    pending = [];
  };
  for (const line of lines) {
    const match = OPTION_LINE.exec(line);
    if (match) {
      pending.push({ key: match[1].toUpperCase(), text: match[2] });
      continue;
    }
    flush();
  }
  flush();
  return groups;
}

interface ResearchOptionSelectorProps {
  content: string;
  disabled?: boolean;
  onSend: (message: string) => void;
}

/**
 * 姜姜提出选择题时，把选项渲染为可点选的字母 Chip：选择后（可选）在每组
 * 下方的补充框里输入其他信息，右下角"提交选择"会把选择组合成一条明确的
 * 用户消息继续对话。交互模式与学习端组卷生成的选项选择保持一致。
 */
export function ResearchOptionSelector({
  content,
  disabled = false,
  onSend,
}: ResearchOptionSelectorProps) {
  const groups = useMemo(() => parseOptionGroups(content), [content]);
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [supplements, setSupplements] = useState<Record<number, string>>({});

  if (groups.length === 0) return null;

  const hasSelection = (index: number) => Boolean(selected[index]);
  const hasContent = groups.some(
    (_, index) => hasSelection(index) || (supplements[index] ?? "").trim(),
  );

  const submit = () => {
    const lines: string[] = [];
    groups.forEach((group, index) => {
      const chosen = group.options.find((option) => option.key === selected[index]);
      const supplement = (supplements[index] ?? "").trim();
      if (chosen) {
        lines.push(`我选 ${chosen.key}：${chosen.text}${supplement ? `（补充：${supplement}）` : ""}`);
      } else if (supplement) {
        lines.push(`第 ${index + 1} 组补充：${supplement}`);
      }
    });
    if (lines.length === 0) return;
    onSend(lines.join("\n"));
    setSelected({});
    setSupplements({});
  };

  return (
    <div
      role="region"
      aria-label="选择题快速作答"
      className="my-4 rounded-2xl border border-violet-200/80 bg-gradient-to-b from-violet-50/70 to-slate-50/50 p-4 shadow-sm backdrop-blur-sm dark:border-violet-900/60 dark:from-violet-950/20 dark:to-zinc-900/40"
    >
      <div className="mb-3 flex items-center gap-2 text-violet-950 dark:text-violet-200">
        <ListChecks className="h-4 w-4 text-violet-600 dark:text-violet-400" />
        <h3 className="text-sm font-bold">快速作答：点选选项，右下角提交</h3>
      </div>

      <div className="space-y-4">
        {groups.map((group, groupIndex) => (
          <div key={groupIndex}>
            <div className="mb-2 text-xs font-medium text-slate-500 dark:text-zinc-400">
              第 {groupIndex + 1} 组
            </div>
            <div className="flex flex-col gap-1.5">
              {group.options.map((option) => {
                const active = selected[groupIndex] === option.key;
                return (
                  <button
                    key={option.key}
                    type="button"
                    disabled={disabled}
                    onClick={() =>
                      setSelected((prev) => ({ ...prev, [groupIndex]: active ? "" : option.key }))
                    }
                    className={`flex items-start gap-2.5 rounded-xl border px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
                      active
                        ? "border-violet-500/70 bg-violet-100/70 dark:border-violet-500/70 dark:bg-violet-950/40"
                        : "border-slate-200/80 bg-white/80 hover:border-violet-400 dark:border-zinc-800 dark:bg-zinc-900/80 dark:hover:border-violet-600"
                    }`}
                  >
                    <span
                      className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${
                        active
                          ? "border-violet-500 bg-violet-500 text-white dark:border-violet-500 dark:bg-violet-500 dark:text-white"
                          : "border-slate-300 text-slate-500 dark:border-zinc-600 dark:text-zinc-400"
                      }`}
                    >
                      {option.key}
                    </span>
                    <span className="leading-6 text-slate-700 dark:text-zinc-200">
                      {option.text}
                    </span>
                  </button>
                );
              })}
            </div>
            <input
              type="text"
              disabled={disabled}
              value={supplements[groupIndex] ?? ""}
              onChange={(event) =>
                setSupplements((prev) => ({ ...prev, [groupIndex]: event.target.value }))
              }
              placeholder="补充说明（可选）：其他想法、资源条件或约束……"
              className="mt-2 w-full rounded-xl border border-slate-200/80 bg-white/90 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-violet-400 focus:outline-none disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900/80 dark:text-zinc-200 dark:placeholder:text-zinc-500"
            />
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-end gap-3">
        <span className="text-xs text-slate-400 dark:text-zinc-500">
          提交后会把选择作为你的消息发给姜姜
        </span>
        <button
          type="button"
          disabled={disabled || !hasContent}
          onClick={submit}
          className="inline-flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-violet-600 dark:hover:bg-violet-500"
        >
          提交选择
          <Send className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
