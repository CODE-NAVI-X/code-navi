"use client";

/**
 * Lightweight read-only renderer for a single slide.
 *
 * Mirrors the subset of OpenMAIC's PPTElement model we support in iteration
 * one: text (restricted HTML), shape (CSS), latex (KaTeX), image and line.
 * The canvas is a fixed 1280×720 design space scaled to fit the container.
 */

import { useMemo } from "react";
import katex from "katex";
import type {
  ImageElement,
  LatexElement,
  LineElement,
  ShapeElement,
  Slide,
  TextElement,
} from "@/lib/api/learning";

export const CANVAS_WIDTH = 1280;
export const CANVAS_HEIGHT = 720;

// ── Restricted-HTML sanitizer ─────────────────────────────────────────────────
// The backend prompt constrains text ``content`` to a small tag whitelist, but
// since this is model-generated markup we still strip anything outside it and
// every event handler / javascript: URL before injecting it into the DOM.

const ALLOWED_TAGS = new Set([
  "p",
  "span",
  "strong",
  "b",
  "em",
  "i",
  "u",
  "br",
]);

function sanitizeHtml(html: string): string {
  if (typeof window === "undefined") return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  const walk = (node: Node): Node => {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as HTMLElement;
        const tag = el.tagName.toLowerCase();
        if (!ALLOWED_TAGS.has(tag)) {
          // Replace disallowed elements with their text content.
          const text = doc.createTextNode(el.textContent ?? "");
          el.replaceWith(text);
          continue;
        }
        // Drop event handlers and dangerous URL schemes.
        for (const attr of Array.from(el.attributes)) {
          const name = attr.name.toLowerCase();
          if (name.startsWith("on")) {
            el.removeAttribute(attr.name);
          } else if (name === "href" || name === "src") {
            const value = attr.value.trim().toLowerCase();
            if (value.startsWith("javascript:") || value.startsWith("data:text/html")) {
              el.removeAttribute(attr.name);
            }
          }
        }
        walk(el);
      } else if (child.nodeType === Node.TEXT_NODE) {
        // keep as-is
      }
    }
    return node;
  };
  walk(doc.body);
  return doc.body.innerHTML;
}

// ── Element renderers ──────────────────────────────────────────────────────────

function TextBlock({ el }: { el: TextElement }) {
  const safeHtml = useMemo(() => sanitizeHtml(el.content), [el.content]);
  return (
    <div
      className="absolute overflow-hidden"
      style={{
        left: el.left,
        top: el.top,
        width: el.width,
        height: el.height,
        transform: el.rotate ? `rotate(${el.rotate}deg)` : undefined,
        color: el.defaultColor ?? "#333333",
        fontFamily: el.defaultFontName || undefined,
        lineHeight: el.lineHeight ?? 1.5,
        background: el.fill ?? undefined,
        textAlign: el.textAlign ?? "left",
      }}
      // html content is restricted by the backend prompt and sanitized above
      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  );
}

function ShapeBlock({ el }: { el: ShapeElement }) {
  const base: React.CSSProperties = {
    position: "absolute",
    left: el.left,
    top: el.top,
    width: el.width,
    height: el.height,
    background: el.fill,
    border: el.strokeColor
      ? `${el.strokeWidth || 1}px solid ${el.strokeColor}`
      : undefined,
    transform: el.rotate ? `rotate(${el.rotate}deg)` : undefined,
  };
  switch (el.shapeType) {
    case "circle":
      return <div style={{ ...base, borderRadius: "50%" }} />;
    case "roundRect":
      return <div style={{ ...base, borderRadius: Math.min(el.width, el.height) / 6 }} />;
    case "triangle":
      return (
        <div
          style={{
            ...base,
            background: "transparent",
            clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
          }}
        />
      );
    case "diamond":
      return (
        <div
          style={{
            ...base,
            background: "transparent",
            clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)",
          }}
        />
      );
    case "message":
      return <div style={{ ...base, borderRadius: 16 }} />;
    default:
      return <div style={base} />;
  }
}

function LatexBlock({ el }: { el: LatexElement }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(el.latex, { throwOnError: false, displayMode: true });
    } catch {
      return el.latex;
    }
  }, [el.latex]);
  return (
    <div
      className="absolute flex items-center overflow-hidden"
      style={{
        left: el.left,
        top: el.top,
        width: el.width,
        height: el.height,
        transform: el.rotate ? `rotate(${el.rotate}deg)` : undefined,
      }}
      // KaTeX output is math markup, safe for direct injection
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function ImageBlock({ el }: { el: ImageElement }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- data URLs / arbitrary hosts; next/image cannot optimize these
    <img
      className="absolute object-contain select-none"
      src={el.src}
      alt=""
      draggable={false}
      style={{
        left: el.left,
        top: el.top,
        width: el.width,
        height: el.height,
        borderRadius: el.borderRadius ?? 0,
        transform: el.rotate ? `rotate(${el.rotate}deg)` : undefined,
      }}
    />
  );
}

function LineBlock({ el }: { el: LineElement }) {
  const horizontal = el.width >= el.height;
  return (
    <div
      className="absolute"
      style={{
        left: el.left,
        top: el.top,
        width: horizontal ? el.width : el.strokeWidth || 2,
        height: horizontal ? el.strokeWidth || 2 : el.height,
        background: el.strokeColor ?? "#94a3b8",
        borderRadius: 1,
        transform: el.rotate ? `rotate(${el.rotate}deg)` : undefined,
      }}
    />
  );
}

// ── Slide renderer ─────────────────────────────────────────────────────────────

export interface SlideRendererProps {
  slide: Slide;
  /** Container CSS width; height derives from the 16:9 ratio. */
  width?: number;
  className?: string;
}

export function SlideRenderer({ slide, width = 800, className }: SlideRendererProps) {
  const scale = width / CANVAS_WIDTH;
  const height = CANVAS_HEIGHT * scale;

  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm dark:border-zinc-800 ${className ?? ""}`}
      style={{ width, height }}
    >
      <div
        className="absolute"
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
          background: slide.background.color,
        }}
      >
        {slide.elements.map((el, idx) => {
          switch (el.type) {
            case "text":
              return <TextBlock key={idx} el={el} />;
            case "shape":
              return <ShapeBlock key={idx} el={el} />;
            case "latex":
              return <LatexBlock key={idx} el={el} />;
            case "image":
              return <ImageBlock key={idx} el={el} />;
            case "line":
              return <LineBlock key={idx} el={el} />;
            default:
              return null;
          }
        })}
      </div>
    </div>
  );
}
