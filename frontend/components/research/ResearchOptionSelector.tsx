"use client";

import { useMemo, useState } from "react";
import { ListChecks, Send } from "lucide-react";

/**
 * 解析姜姜回复中的选择题选项（如 A. / · A. / - **A.** / A、 / A： 等），
 * 连续 ≥2 个选项归为一组。
 * 返回按出现顺序排列的选项组；没有选项组时返回空数组。
 */
export interface ParsedOption {
  key: string;
  text: string;
  fillValue?: string;
}

export interface ParsedOptionGroup {
  title?: string;
  options: ParsedOption[];
}

/**
 * 解析姜姜回复中真正需要用户作答的选项：
 * 1. 明确的字母标号选项（A. / · A. / - **A.** / A、 / A： 等）；
 * 2. 决策分支（如“· 如果纳入：...” / “· 如果跳过：...”等待拍板事项）；
 * 3. 计划/执行阶段的确认提问（如“四、计划确认：如果你确认无误...对计划有任何调整需求...”）；
 * 4. 严格排除正文中的普通数字执行步骤（1. / 2. / 3.）与限制说明条目。
 */
export function parseOptionGroups(content: string): ParsedOptionGroup[] {
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const groups: ParsedOptionGroup[] = [];

  // --- 模式 1：明确字母标号选择题（严格限定为英文字母 A-G，严禁匹配普通纯数字序号） ---
  const LETTER_OPTION_LINE =
    /^(?:[-*•·+]\s*)?(?:\*\*)?([A-Ga-g])(?:\*\*)?\s*(?:端)?[.、：:\s]\s*(.+)$/;

  let pendingLetter: ParsedOption[] = [];
  let pendingLetterTitle: string | undefined = undefined;
  let lastNonOptionLine: string | undefined = undefined;

  const flushLetter = () => {
    if (pendingLetter.length >= 2) {
      groups.push({ title: pendingLetterTitle, options: pendingLetter });
    }
    pendingLetter = [];
    pendingLetterTitle = undefined;
  };

  for (const line of lines) {
    const match = LETTER_OPTION_LINE.exec(line);
    if (match) {
      const rawKey = match[1].trim().toUpperCase();
      const rawText = match[2].trim().replace(/^\*\*(.*?)\*\*/, "$1");
      if (/^[A-G]$/.test(rawKey)) {
        if (pendingLetter.length === 0 && lastNonOptionLine) {
          pendingLetterTitle = lastNonOptionLine.replace(/^[#*·•\s->]+/, "").trim();
        }
        pendingLetter.push({
          key: rawKey,
          text: rawText,
          fillValue: `我选 ${rawKey}：${rawText}`,
        });
        continue;
      }
    }
    flushLetter();
    lastNonOptionLine = line;
  }
  flushLetter();

  // --- 模式 2：决策拍板分支（图一场景：如“如果纳入：...” / “如果跳过：...”等） ---
  const BRANCH_LINE =
    /^(?:[-*•·+]\s*)?(?:\*\*)?(如果(?:纳入|跳过|保留|暂缓|增加|减少|采用|执行|同意|不同意|是|否)|(?:方案|选项|路径|分支)[一二三四1234ABC]|纳入|跳过|保留|暂缓)(?:\*\*)?[：:]\s*(.+)$/;

  let pendingBranch: ParsedOption[] = [];
  let pendingBranchTitle: string | undefined = undefined;
  let lastNonBranchLine: string | undefined = undefined;

  const flushBranch = () => {
    if (pendingBranch.length >= 2) {
      groups.push({ title: pendingBranchTitle || "拍板决策事项", options: pendingBranch });
    }
    pendingBranch = [];
    pendingBranchTitle = undefined;
  };

  for (const line of lines) {
    const branchMatch = BRANCH_LINE.exec(line);
    if (branchMatch) {
      const branchTag = branchMatch[1].trim();
      const branchDesc = branchMatch[2].trim();
      if (pendingBranch.length === 0 && lastNonBranchLine) {
        pendingBranchTitle = lastNonBranchLine.replace(/^[#*·•\s->]+/, "").trim();
      }
      const charKey = String.fromCharCode(65 + pendingBranch.length); // A, B, C...
      pendingBranch.push({
        key: charKey,
        text: `${branchTag}：${branchDesc}`,
        fillValue: `我选择【${branchTag}】：${branchDesc}`,
      });
      continue;
    }
    flushBranch();
    lastNonBranchLine = line;
  }
  flushBranch();

  // --- 模式 3：计划确认 / 阶段执行确认（图二场景：末尾提出计划确认无误后进入执行） ---
  if (groups.length === 0) {
    const tailContent = content.slice(-600);
    const isPlanConfirmation =
      /(?:计划确认|需要你确认的事项|确认计划|执行确认|方案确认)/i.test(tailContent) &&
      /(?:确认无误.*(?:进入|开始)|对计划有任何调整需求.*开始执行|如果你确认|确认后，我们开始执行)/i.test(tailContent);

    if (isPlanConfirmation) {
      groups.push({
        title: "计划执行确认",
        options: [
          {
            key: "A",
            text: "确认无误，正式开始执行",
            fillValue: "计划已经确认无误，我们可以正式进入 Day 1 的执行阶段！",
          },
          {
            key: "B",
            text: "我需要微调计划（时间/范围/环境）",
            fillValue: "我对计划有一些微调需求：",
          },
        ],
      });
    }
  }

  return groups;
}

interface ResearchOptionSelectorProps {
  content: string;
  disabled?: boolean;
  onSend: (message: string) => void;
  onFillInput?: (text: string) => void;
}

/**
 * 姜姜提出选择题或拍板/确认事项时，把选项渲染为可点选的卡片：
 * 1. 点击选项直接将回答格式化填入输入框（支持用户继续编辑或回车发送）；
 * 2. 也支持在卡片内点选并点击右下角“提交选择”直接发送。
 */
export function ResearchOptionSelector({
  content,
  disabled = false,
  onSend,
  onFillInput,
}: ResearchOptionSelectorProps) {
  const groups = useMemo(() => parseOptionGroups(content), [content]);
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [supplements, setSupplements] = useState<Record<number, string>>({});

  if (groups.length === 0) return null;

  const hasSelection = (index: number) => Boolean(selected[index]);
  const hasContent = groups.some(
    (_, index) => hasSelection(index) || (supplements[index] ?? "").trim(),
  );

  const handleSelectOption = (groupIndex: number, option: ParsedOption) => {
    const nextKey = selected[groupIndex] === option.key ? "" : option.key;
    setSelected((prev) => ({ ...prev, [groupIndex]: nextKey }));
    if (nextKey && onFillInput) {
      const supplement = (supplements[groupIndex] ?? "").trim();
      const baseFill = option.fillValue || `我选 ${option.key}：${option.text}`;
      const textToFill = `${baseFill}${supplement ? `（补充：${supplement}）` : ""}`;
      onFillInput(textToFill);
    }
  };

  const submit = () => {
    const lines: string[] = [];
    groups.forEach((group, index) => {
      const chosen = group.options.find((option) => option.key === selected[index]);
      const supplement = (supplements[index] ?? "").trim();
      if (chosen) {
        const baseFill = chosen.fillValue || `我选 ${chosen.key}：${chosen.text}`;
        lines.push(`${baseFill}${supplement ? `（补充：${supplement}）` : ""}`);
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
      <div className="mb-3 flex items-center justify-between gap-2 text-violet-950 dark:text-violet-200">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-violet-600 dark:text-violet-400" />
          <h3 className="text-sm font-bold">快速作答：点击选项自动填入输入框，或右下角直接提交</h3>
        </div>
      </div>

      <div className="space-y-4">
        {groups.map((group, groupIndex) => (
          <div key={groupIndex}>
            <div className="mb-2 text-xs font-medium text-slate-500 dark:text-zinc-400">
              {group.title ? group.title : `第 ${groupIndex + 1} 组`}
            </div>
            <div className="flex flex-col gap-1.5">
              {group.options.map((option) => {
                const active = selected[groupIndex] === option.key;
                return (
                  <button
                    key={option.key}
                    type="button"
                    disabled={disabled}
                    onClick={() => handleSelectOption(groupIndex, option)}
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
              onChange={(event) => {
                const val = event.target.value;
                setSupplements((prev) => ({ ...prev, [groupIndex]: val }));
                const currentKey = selected[groupIndex];
                if (currentKey && onFillInput) {
                  const opt = group.options.find((o) => o.key === currentKey);
                  if (opt) {
                    onFillInput(`我选 ${opt.key}：${opt.text}${val ? `（补充：${val}）` : ""}`);
                  }
                }
              }}
              placeholder="补充说明（可选）：其他想法、资源条件或约束……"
              className="mt-2 w-full rounded-xl border border-slate-200/80 bg-white/90 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-violet-400 focus:outline-none disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900/80 dark:text-zinc-200 dark:placeholder:text-zinc-500"
            />
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-violet-100/80 pt-3 dark:border-violet-900/40">
        <span className="text-xs text-slate-400 dark:text-zinc-500">
          点击选项已自动同步到输入框；也可在此补充后直接提交
        </span>
        <div className="flex items-center gap-2">
          {onFillInput && hasContent && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
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
                if (lines.length > 0) onFillInput(lines.join("\n"));
              }}
              className="inline-flex items-center gap-1 rounded-xl border border-violet-300 bg-white px-3 py-1.5 text-xs font-semibold text-violet-700 shadow-sm transition hover:bg-violet-50 dark:border-violet-700 dark:bg-zinc-900 dark:text-violet-300"
            >
              填入输入框
            </button>
          )}
          <button
            type="button"
            disabled={disabled || !hasContent}
            onClick={submit}
            className="inline-flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-violet-600 dark:hover:bg-violet-500"
          >
            提交选择
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
