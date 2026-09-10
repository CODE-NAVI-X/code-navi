"use client";

import { useState } from "react";
import { Send } from "lucide-react";

import {
  BRANCH_LINE,
  buildAnswerMessage,
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
  onSend: (message: string) => void;
  onFillInput?: (text: string) => void;
}

/**
 * 姜姜提出选择题或拍板/确认事项时，把该选项组就地渲染在对应题干下方：
 * 1. 点击选项直接将回答格式化填入输入框（支持用户继续编辑或回车发送）；
 * 2. 也支持在选项组内点选并点击“提交选择”直接发送。
 *
 * 组件只渲染**一个**已经定位好的选项组，因此不会出现独立标题卡片，
 * 也不会和正文里的静态 A/B/C/D 重复：被接管的静态行由
 * `splitMessageSegments` 从 markdown 片段里摘除。
 */
export function ResearchOptionSelector({
  group,
  disabled = false,
  onSend,
  onFillInput,
}: ResearchOptionSelectorProps) {
  const [selected, setSelected] = useState<string>("");
  const [supplement, setSupplement] = useState<string>("");

  const buildFillText = (option: ParsedOption, extra: string) => {
    const baseFill = option.fillValue || `我选 ${option.key}：${option.text}`;
    return `${baseFill}${extra ? `（补充：${extra}）` : ""}`;
  };

  const hasContent = Boolean(selected) || supplement.trim().length > 0;

  const handleSelectOption = (option: ParsedOption) => {
    const nextKey = toggleOptionKey(selected, option.key);
    setSelected(nextKey);
    if (nextKey && onFillInput) {
      onFillInput(buildFillText(option, supplement.trim()));
    }
  };

  const buildMessage = () =>
    buildAnswerMessage([group], { 0: selected }, { 0: supplement });

  const submit = () => {
    const message = buildMessage();
    if (!message) return;
    onSend(message);
    setSelected("");
    setSupplement("");
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
          const option = group.options.find((item) => item.key === selected);
          if (option && onFillInput) {
            onFillInput(buildFillText(option, val.trim()));
          }
        }}
        placeholder="补充说明（可选）：其他想法、资源条件或约束……"
        className="mt-2 w-full rounded-xl border border-slate-200/80 bg-white/90 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-violet-400 focus:outline-none disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900/80 dark:text-zinc-200 dark:placeholder:text-zinc-500"
      />

      <div className="flex flex-wrap items-center gap-2">
        {onFillInput && hasContent && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              const message = buildMessage();
              if (message) onFillInput(message);
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
  );
}
