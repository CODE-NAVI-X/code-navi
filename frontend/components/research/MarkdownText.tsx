import { Fragment, type ReactNode } from "react";

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;

function renderInline(text: string): ReactNode[] {
  return text.split(INLINE_PATTERN).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[0.88em] text-slate-800 dark:bg-zinc-800 dark:text-zinc-200"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = /^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/.exec(part);
    if (link) {
      return (
        <a
          key={index}
          href={link[2]}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-sky-700 underline decoration-sky-300 underline-offset-2 hover:text-sky-600 dark:text-sky-300 dark:decoration-sky-800"
        >
          {link[1]}
        </a>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

const DIRECTION_CARD_LINE = /^(\d+)[.、)]\s*【(.+?)】[：:]?\s*(.*)$/;

interface DirectionCardItem {
  index: string;
  title: string;
  description: string;
}

function parseDirectionCardLine(line: string): DirectionCardItem | null {
  const match = DIRECTION_CARD_LINE.exec(line);
  if (!match) return null;
  return { index: match[1], title: match[2], description: match[3] };
}

interface NumberedItem {
  marker: string;
  text: string;
}

// 连续编号行（1. 2. 3.）是姜姜的分点提问/清单；限定一位数序号并要求
// 后接内容，避免把 "2026年…" 这类普通句子误判成清单项。
const NUMBERED_LINE = /^([1-9])[.、)）]\s*(.+)$/;

function parseNumberedLine(line: string): NumberedItem | null {
  const match = NUMBERED_LINE.exec(line);
  if (!match) return null;
  return { marker: match[1], text: match[2] };
}

function NumberedListPanel({ items }: { items: NumberedItem[] }) {
  return (
    <div className="rounded-xl border border-violet-200/80 bg-violet-50/70 px-3.5 py-2.5 dark:border-violet-900/60 dark:bg-violet-950/20">
      {items.map((item, index) => (
        <div
          key={index}
          className={`flex items-start gap-2.5 py-1.5 ${
            index > 0 ? "border-t border-violet-200/60 dark:border-violet-900/40" : ""
          }`}
        >
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-600/90 text-xs font-bold text-white dark:bg-violet-500">
            {item.marker}
          </span>
          <p className="text-[15px] leading-7 text-slate-800 dark:text-zinc-200">
            {renderInline(item.text)}
          </p>
        </div>
      ))}
    </div>
  );
}

function renderDefaultLine(line: string, lineIndex: number): ReactNode {
  if (!line) return <div key={lineIndex} className="h-1" aria-hidden="true" />;
  if (line.startsWith("### ")) {
    return (
      <h4 key={lineIndex} className="pt-1 font-semibold">
        {renderInline(line.slice(4))}
      </h4>
    );
  }
  if (line.startsWith("## ")) {
    return (
      <h3 key={lineIndex} className="pt-1 text-base font-semibold">
        {renderInline(line.slice(3))}
      </h3>
    );
  }
  if (/^[-*]\s+/.test(line)) {
    return (
      <div key={lineIndex} className="flex gap-2 pl-1">
        <span className="mt-[0.72em] h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
        <p>{renderInline(line.replace(/^[-*]\s+/, ""))}</p>
      </div>
    );
  }
  if (/^\d+[.)]\s+/.test(line)) {
    const marker = /^\d+[.)]/.exec(line)?.[0] ?? "";
    return (
      <div key={lineIndex} className="flex gap-2 pl-1">
        <span className="min-w-5 font-medium opacity-60">{marker}</span>
        <p>{renderInline(line.replace(/^\d+[.)]\s+/, ""))}</p>
      </div>
    );
  }
  return <p key={lineIndex}>{renderInline(line)}</p>;
}

function DirectionCardStack({
  cards,
  onSelectDirection,
}: {
  cards: DirectionCardItem[];
  onSelectDirection?: (title: string) => void;
}) {
  return (
    <div className="space-y-2">
      {cards.map((card) => {
        const content = (
          <>
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600/90 text-xs font-bold text-white dark:bg-indigo-500">
              {card.index}
            </span>
            <span>
              <span className="block text-[15px] font-semibold text-slate-900 group-hover:text-indigo-700 dark:text-zinc-100 dark:group-hover:text-indigo-300">
                {renderInline(card.title)}
              </span>
              {card.description && (
                <span className="mt-0.5 block text-sm leading-6 text-slate-600 dark:text-zinc-400">
                  {renderInline(card.description)}
                </span>
              )}
            </span>
          </>
        );
        const base =
          "group flex w-full items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition";
        if (onSelectDirection) {
          return (
            <button
              key={card.index}
              type="button"
              onClick={() => onSelectDirection(card.title)}
              title={`选择方向：${card.title}`}
              className={`${base} cursor-pointer border-indigo-200/80 bg-gradient-to-r from-indigo-50/90 to-sky-50/60 shadow-xs hover:-translate-y-px hover:border-indigo-400 hover:shadow-md dark:border-indigo-900/60 dark:from-indigo-950/30 dark:to-sky-950/20 dark:hover:border-indigo-600`}
            >
              {content}
            </button>
          );
        }
        return (
          <div
            key={card.index}
            className={`${base} border-indigo-200/70 bg-indigo-50/60 dark:border-indigo-900/50 dark:bg-indigo-950/20`}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
}

/** Render a deliberately small, HTML-free Markdown subset for model replies. */
export function MarkdownText({
  content,
  onSelectDirection,
}: {
  content: string;
  onSelectDirection?: (title: string) => void;
}) {
  const blocks = content
    .split(/\r?\n\s*\r?\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="space-y-3 text-base leading-7">
      {blocks.map((block, blockIndex) => {
        const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        const firstLine = lines[0] ?? "";

        // 来源范围说明：独立的信息横幅，提示内容边界。
        if (firstLine.startsWith("说明：")) {
          return (
            <p
              key={blockIndex}
              className="rounded-xl border border-amber-200/70 bg-amber-50/70 px-3 py-2 text-sm leading-6 text-amber-900/90 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200/90"
            >
              {lines.map((line, lineIndex) => (
                <Fragment key={lineIndex}>
                  {lineIndex > 0 && <br />}
                  {renderInline(line)}
                </Fragment>
              ))}
            </p>
          );
        }

        // 学习端记录：客观引用面板（记录 ≠ 掌握度，需要用户确认）。
        if (firstLine.startsWith("学习端记录显示")) {
          return (
            <div
              key={blockIndex}
              className="rounded-xl border border-sky-200/70 border-l-4 border-l-sky-400 bg-sky-50/70 px-3.5 py-2.5 text-[15px] leading-7 text-sky-950/90 dark:border-sky-900/60 dark:border-l-sky-500 dark:bg-sky-950/20 dark:text-sky-100/90"
            >
              {lines.map((line, lineIndex) => (
                <p key={lineIndex}>{renderInline(line)}</p>
              ))}
            </div>
          );
        }

        // 新版开场白：独立的问候面板，与后续内容区分。
        if (block.includes("欢迎来到科研工作台")) {
          return (
            <div
              key={blockIndex}
              className="rounded-2xl border border-indigo-200/80 bg-gradient-to-br from-indigo-50/90 via-violet-50/60 to-slate-50/50 px-4 py-3 shadow-xs dark:border-indigo-900/60 dark:from-indigo-950/30 dark:via-violet-950/20 dark:to-zinc-900/30"
            >
              {lines.map((line, lineIndex) => (
                <p key={lineIndex} className="[&:not(:first-child)]:mt-2">
                  {renderInline(line)}
                </p>
              ))}
            </div>
          );
        }

        // 方向卡列表：块内连续的 “1. 【标题】：描述” 行（≥2 行）归组为高亮
        // 方向卡栈；连续的普通编号行（≥2 行）归组为提问/清单面板；其余行
        // 保持常规渲染。
        type Segment =
          | { kind: "cards"; cards: DirectionCardItem[] }
          | { kind: "numbered"; items: NumberedItem[] }
          | { kind: "line"; line: string };
        const segments: Segment[] = [];
        let pendingCards: DirectionCardItem[] = [];
        let pendingNumbered: NumberedItem[] = [];
        const flushCards = () => {
          if (pendingCards.length > 0) {
            segments.push({ kind: "cards", cards: pendingCards });
            pendingCards = [];
          }
        };
        const flushNumbered = () => {
          if (pendingNumbered.length > 0) {
            segments.push({ kind: "numbered", items: pendingNumbered });
            pendingNumbered = [];
          }
        };
        for (const line of lines) {
          const card = parseDirectionCardLine(line);
          if (card) {
            flushNumbered();
            pendingCards.push(card);
            continue;
          }
          const numbered = parseNumberedLine(line);
          if (numbered) {
            flushCards();
            pendingNumbered.push(numbered);
            continue;
          }
          flushCards();
          flushNumbered();
          segments.push({ kind: "line", line });
        }
        flushCards();
        flushNumbered();
        const hasCardRun = segments.some(
          (segment) => segment.kind === "cards" && segment.cards.length >= 2,
        );
        const hasNumberedRun = segments.some(
          (segment) => segment.kind === "numbered" && segment.items.length >= 2,
        );
        if (hasCardRun || hasNumberedRun) {
          return (
            <div key={blockIndex} className="space-y-3">
              {segments.map((segment, segmentIndex) => {
                if (segment.kind === "cards") {
                  return (
                    <DirectionCardStack
                      key={segmentIndex}
                      cards={segment.cards}
                      onSelectDirection={onSelectDirection}
                    />
                  );
                }
                if (segment.kind === "numbered" && segment.items.length >= 2) {
                  return <NumberedListPanel key={segmentIndex} items={segment.items} />;
                }
                const lineSegment = segment as { kind: "line"; line: string };
                return (
                  <Fragment key={segmentIndex}>
                    {renderDefaultLine(lineSegment.line, segmentIndex)}
                  </Fragment>
                );
              })}
            </div>
          );
        }

        return <div key={blockIndex} className="space-y-3">{lines.map(renderDefaultLine)}</div>;
      })}
    </div>
  );
}
