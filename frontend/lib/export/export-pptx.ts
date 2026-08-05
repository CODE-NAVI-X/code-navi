/**
 * PPTX export for knowledge-PPT slides.
 *
 * A distilled client-side port of OpenMAIC's ``buildPptxBlob`` conversion:
 * 1280×720 canvas → 16:9 wide deck (13.33×7.5 in). Text is flattened to plain
 * text (the rich inline styling of the web renderer is not preserved in this
 * iteration); LaTeX is exported as a readable source placeholder.
 */

import pptxgen from "pptxgenjs";
import type { ImageElement, LatexElement, LineElement, ShapeElement, Slide, SlideElement, TextElement } from "@/lib/api/learning";

const PX_PER_INCH = 96;

function pxToInch(px: number): number {
  // Guard against NaN/negative values so a corrupt element can't break output.
  return (Number.isFinite(px) && px >= 0 ? px : 0) / PX_PER_INCH;
}

function hexToArgb(color: string): string {
  // pptxgenjs accepts hex without the leading '#'.
  return color.replace("#", "").trim();
}

function extractFontSize(html: string): number {
  const match = html.match(/font-size\s*:\s*(\d+)px/i);
  return match ? Number(match[1]) : 18;
}

function stripHtml(html: string): string {
  if (typeof window === "undefined") return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  return doc.body.textContent ?? "";
}

/**
 * Resolve a pptxgenjs shape enum value for a ``ShapeElement``.
 *
 * ``ShapeType`` only exists on a pptxgen *instance* (``pptx.ShapeType.rect``) —
 * reading it off the module import used to crash the export with
 * "Cannot read properties of undefined (reading 'rect')".  We defensively fall
 * back to the raw enum string (the runtime enum *values* are these lowercase
 * strings) so an unexpected shape never aborts the deck.
 */
function shapeTypeFor(pptx: pptxgen, el: ShapeElement): pptxgen.ShapeType {
  // Runtime values are plain strings (e.g. "rect"); the TS enum type exposes
  // differently-named members, so we read it as strings and cast to the enum.
  const shapes = (pptx.ShapeType ?? {}) as Record<string, string | undefined>;
  const resolve = (value: string | undefined, fallback: string): pptxgen.ShapeType =>
    (value ?? fallback) as pptxgen.ShapeType;
  switch (el.shapeType) {
    case "roundRect":
      return resolve(shapes.roundRect, "roundRect");
    case "circle":
      return resolve(shapes.ellipse, "ellipse");
    case "triangle":
      return resolve(shapes.triangle, "triangle");
    case "diamond":
      return resolve(shapes.diamond, "diamond");
    case "message":
      return resolve(shapes.roundRect, "roundRect");
    default:
      return resolve(shapes.rect, "rect");
  }
}

function addElement(pptx: pptxgen, slide: pptxgen.Slide, el: SlideElement): void {
  // Fall back to a safe value for any missing geometry so a malformed element
  // can never throw and abort the whole export.
  const x = pxToInch(el.left ?? 0);
  const y = pxToInch(el.top ?? 0);
  const w = pxToInch(el.width ?? 640);
  const h = pxToInch(el.height ?? 360);

  switch (el.type) {
    case "text": {
      const text = el as TextElement;
      slide.addText(stripHtml(text.content), {
        x,
        y,
        w,
        h,
        color: hexToArgb(text.defaultColor ?? "#333333"),
        fontSize: extractFontSize(text.content),
        align: text.textAlign ?? "left",
        isTextBox: true,
        valign: "middle",
        breakLine: true,
      });
      break;
    }
    case "shape": {
      const shape = el as ShapeElement;
      slide.addShape(shapeTypeFor(pptx, shape), {
        x,
        y,
        w,
        h,
        fill: { color: hexToArgb(shape.fill) },
        line: shape.strokeColor
          ? { color: hexToArgb(shape.strokeColor), width: shape.strokeWidth ?? 1 }
          : { color: "FFFFFF", transparency: 100 },
      });
      break;
    }
    case "line": {
      const line = el as LineElement;
      slide.addShape(pptx.ShapeType.line, {
        x,
        y,
        w,
        h,
        line: { color: hexToArgb(line.strokeColor ?? "#94a3b8"), width: line.strokeWidth ?? 2 },
      });
      break;
    }
    case "image": {
      const img = el as ImageElement;
      slide.addImage({
        x,
        y,
        w,
        h,
        data: img.src,
      });
      break;
    }
    case "latex": {
      const latex = el as LatexElement;
      // Iteration one: export the formula source as a labelled text placeholder.
      slide.addText(`[公式] ${latex.latex}`, {
        x,
        y,
        w,
        h,
        color: "334155",
        fontSize: 16,
        isTextBox: true,
        valign: "middle",
      });
      break;
    }
  }
}

/**
 * Build a .pptx Blob for the given slides.
 */
export async function buildPptxBlob(
  knowledgePoint: string,
  slides: Slide[],
): Promise<Blob> {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Code Navi";
  pptx.title = knowledgePoint;

  for (const slide of slides) {
    const deckSlide = pptx.addSlide();
    deckSlide.background = { color: hexToArgb(slide.background.color) };
    for (const el of slide.elements) {
      addElement(pptx, deckSlide, el);
    }
  }
  const out = await pptx.write({ outputType: "blob" });
  return out as Blob;
}

/**
 * Generate and download the deck in the browser.
 */
export async function exportSlidesToPptx(
  knowledgePoint: string,
  slides: Slide[],
): Promise<void> {
  const blob = await buildPptxBlob(knowledgePoint, slides);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${knowledgePoint || "presentation"}.pptx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
