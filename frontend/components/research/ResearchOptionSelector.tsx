"use client";

import { useState } from "react";

import {
  BRANCH_LINE,
  buildAnswerMessage,
  buildOptionFillText,
  parseOptionGroups,
  toggleOptionKey,
  type ParsedOption,
  type ParsedOptionGroup,
} from "@/lib/research-options";

// 解析 API 的既有导出位置保持不变：外部与本模块相关测试仍从组件模块引用。
export { parseOptionGroups, BRANCH_LINE };
export type { ParsedOption, ParsedOptionGroup };

interface ResearchOptionSelectorProps {
  /** 已经由 `splitMessageSegments` 定位好的选项组；组件只负责渲染，不再解析正文。 */
  group: ParsedOptionGroup;
  disabled?: boolean;
  /** 唯一的作答出口：把回答填入页面底部输入框，由用户确认后手动发送。 */
  onFillInput?: (text: string) => void;
}

/**
 * 姜姜提出选择题或拍板/确认事项时，把该选项组就地渲染在对应题干下方：
 *
 *   一个问题 -> 2~4 个可点击选项 -> 点击只填入底部输入框
 *   -> 用户可编辑或补充 -> 只有底部全局“发送”按钮负责提交。
 *
 * 因此组件**刻意不持有任何发送能力**：属性里没有发送回调、界面上没有发送按钮，
 * 点击选项与编辑补充说明都只调用 `onFillInput`。这样“点选项即发送”在结构上
 * 就不可能发生，而不是靠运行时判断去避免。
 *
 * 组件只渲染**一个**已经定位好的选项组，因此不会出现独立标题卡片，
 * 也不会和正文里的静态 A/B/C/D 重复：被接管的静态行由
 * `splitMessageSegments` 从 markdown 片段里摘除。
 */
export function ResearchOptionSelector({
  group,
  disabled = false,
  onFillInput,
}: ResearchOptionSelectorProps) {
  const [selected, setSelected] = useState<string>("");
  const [supplement, setSupplement] = useState<string>("");

  const selectedOption = group.options.find((option) => option.key === selected);
  const hasContent = Boolean(selected) || supplement.trim().length > 0;

  const handleSelectOption = (option: ParsedOption) => {
    const nextKey = toggleOptionKey(selected, option.key);
    setSelected(nextKey);
    if (!onFillInput) return;
    // 只写入草稿：取消选中时清空对应填充，选中时填入回答。
    onFillInput(nextKey ? buildOptionFillText(option, supplement) : "");
  };

  /**
   * “填入输入框”只在用户已经写了内容时才出现，用于把整组作答同步到输入框。
   * 它同样只填充、不发送。
   */
  const fillDraft = () => {
    if (!onFillInput) return;
    onFillInput(buildAnswerMessage([group], { 0: selected }, { 0: supplement }));
  };

  return (
    <div
      className="mt-2 space-y-3"
      data-testid="research-inline-options"
      role="group"
      aria-label={group.title || "请选择"}
    >
      <div className="flex flex-col gap-1.5">
        {group.options.map((option) => {
          const active = selected === option.key;
          return (
            <button
              key={option.key}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => handleSelectOption(option)}
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
              <span className="leading-6 text-slate-700 dark:text-zinc-200">{option.text}</span>
            </button>
          );
        })}
      </div>

      <input
        type="text"
        disabled={disabled}
        value={supplement}
        onChange={(event) => {
          const val = event.target.value;
          setSupplement(val);
          // 补充说明同样只写入输入框草稿，不发送。
          if (onFillInput && selectedOption) {
            onFillInput(buildOptionFillText(selectedOption, val));
          }
        }}
        placeholder="补充说明（可选）：其他想法、资源条件或约束……"
        className="mt-2 w-full rounded-xl border border-slate-200/80 bg-white/90 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-violet-400 focus:outline-none disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900/80 dark:text-zinc-200 dark:placeholder:text-zinc-500"
      />

      {onFillInput && hasContent && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={fillDraft}
            className="inline-flex items-center gap-1 rounded-xl border border-violet-300 bg-white px-3 py-1.5 text-xs font-semibold text-violet-700 shadow-sm transition hover:bg-violet-50 dark:border-violet-700 dark:bg-zinc-900 dark:text-violet-300"
          >
            填入输入框
          </button>
        </div>
      )}
    </div>
  );
}
