"""Pydantic data-models for the presentation (knowledge PPT) feature.

The element model is a deliberately narrow port of OpenMAIC's ``PPTElement``
(``lib/types/slides.ts``): only the five element types that cover ~90% of
academic slides are carried over — text, shape, latex, image and line.
Chart / table / video / code are out of scope for the first iteration.

Canvas coordinates are normalized to a 1280×720 design space; the frontend
scales to fit its container, and the PPTX exporter maps px→pt 1:1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720

# ---------------------------------------------------------------------------
# Elements (discriminated union on ``type``)
# ---------------------------------------------------------------------------


class SlideElementBase(BaseModel):
    """Shared geometry for every element.

    ``left``/``top`` are the top-left corner in the 1280×720 canvas.
    """

    left: float = Field(..., ge=0, description="Distance from the left canvas edge (px).")
    top: float = Field(..., ge=0, description="Distance from the top canvas edge (px).")
    width: float = Field(..., gt=0, description="Element width (px).")
    height: float = Field(..., gt=0, description="Element height (px).")
    rotate: float = Field(default=0.0, ge=-360, le=360, description="Rotation in degrees.")


class TextElement(SlideElementBase):
    """Rich-text element. ``content`` is restricted HTML (p/span/strong/em/u/br)."""

    type: Literal["text"]
    content: str = Field(..., description="HTML content, styled inline (font-size, color, …).")
    defaultColor: str = Field(default="#333333", description="Fallback text color.")
    defaultFontName: str = Field(default="", description="Fallback font family.")
    lineHeight: float = Field(default=1.5, ge=0.5, le=3, description="Line-height multiplier.")
    fill: str | None = Field(default=None, description="Optional text-box background color.")
    textAlign: Literal["left", "center", "right"] = Field(
        default="left", description="Horizontal alignment inside the text box."
    )


class ShapeElement(SlideElementBase):
    """Decorative / diagram shape rendered with CSS."""

    type: Literal["shape"]
    shapeType: Literal["rect", "roundRect", "circle", "triangle", "diamond", "message"] = Field(
        default="rect"
    )
    fill: str = Field(default="#4f46e5", description="Fill color.")
    strokeColor: str | None = Field(default=None, description="Border color; None = no border.")
    strokeWidth: float = Field(default=0.0, ge=0)


class LatexElement(SlideElementBase):
    """Math expression rendered with KaTeX on the web client."""

    type: Literal["latex"]
    latex: str = Field(..., description="LaTeX source, e.g. \\sum_{i=1}^{n} i.")


class ImageElement(SlideElementBase):
    """Image. ``src`` may be a data URL or absolute URL."""

    type: Literal["image"]
    src: str = Field(..., description="Data URL or absolute URL of the image.")
    borderRadius: float = Field(default=0.0, ge=0)


class LineElement(SlideElementBase):
    """Horizontal/vertical divider line."""

    type: Literal["line"]
    strokeColor: str = Field(default="#94a3b8")
    strokeWidth: float = Field(default=2.0, gt=0)


SlideElement = Annotated[
    TextElement | ShapeElement | LatexElement | ImageElement | LineElement,
    Field(discriminator="type"),
]


class SlideBackground(BaseModel):
    """Per-slide background. Only solid is supported in iteration one."""

    type: Literal["solid"] = "solid"
    color: str = Field(default="#ffffff", description="Hex color, e.g. #f8fafc.")


class Slide(BaseModel):
    """One rendered slide — background + ordered elements."""

    background: SlideBackground = Field(default_factory=SlideBackground)
    elements: list[SlideElement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generation request / outline / persisted presentation
# ---------------------------------------------------------------------------


class SceneOutline(BaseModel):
    """One planned page produced by stage 1 (knowledge point → outlines)."""

    id: str = Field(..., description="Stable id, e.g. slide_1.")
    title: str = Field(..., min_length=1, max_length=120, description="Concise page title.")
    description: str = Field(default="", description="One-sentence teaching purpose.")
    key_points: list[str] = Field(
        default_factory=list, description="3-5 core points this page should cover."
    )
    order: int = Field(..., ge=1, description="1-based page order.")


class PresentationGenerateRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/presentations/generate``."""

    knowledge_point: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="The knowledge point the PPT should teach.",
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Learning session for notebook archival.",
    )
    style: Literal["professional", "academic", "playful"] = Field(
        default="professional", description="Visual tone applied to generated slides."
    )
    context: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional explanation context (e.g. a depth-analysis result) "
        "that grounds the slide content. Passed to the prompts as extra material.",
    )


class Presentation(BaseModel):
    """A fully generated presentation, persisted as ``item_type=presentation``."""

    id: str = Field(..., description="Stable presentation id.")
    knowledge_point: str
    session_id: str
    style: str = "professional"
    slides: list[Slide] = Field(default_factory=list)
    created_at: datetime | None = Field(default=None)


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "ImageElement",
    "LatexElement",
    "LineElement",
    "Presentation",
    "PresentationGenerateRequest",
    "SceneOutline",
    "ShapeElement",
    "Slide",
    "SlideBackground",
    "SlideElement",
    "SlideElementBase",
    "TextElement",
]
