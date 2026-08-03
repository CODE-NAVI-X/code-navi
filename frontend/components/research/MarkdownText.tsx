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

/** Render a deliberately small, HTML-free Markdown subset for model replies. */
export function MarkdownText({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-sm leading-7">
      {content.split(/\r?\n/).map((rawLine, index) => {
        const line = rawLine.trim();
        if (!line) return <div key={index} className="h-1" aria-hidden="true" />;
        if (line.startsWith("### ")) {
          return <h4 key={index} className="pt-1 font-semibold">{renderInline(line.slice(4))}</h4>;
        }
        if (line.startsWith("## ")) {
          return <h3 key={index} className="pt-1 text-base font-semibold">{renderInline(line.slice(3))}</h3>;
        }
        if (/^[-*]\s+/.test(line)) {
          return (
            <div key={index} className="flex gap-2 pl-1">
              <span className="mt-[0.72em] h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
              <p>{renderInline(line.replace(/^[-*]\s+/, ""))}</p>
            </div>
          );
        }
        if (/^\d+[.)]\s+/.test(line)) {
          const marker = /^\d+[.)]/.exec(line)?.[0] ?? "";
          return (
            <div key={index} className="flex gap-2 pl-1">
              <span className="min-w-5 font-medium opacity-60">{marker}</span>
              <p>{renderInline(line.replace(/^\d+[.)]\s+/, ""))}</p>
            </div>
          );
        }
        return <p key={index}>{renderInline(line)}</p>;
      })}
    </div>
  );
}
