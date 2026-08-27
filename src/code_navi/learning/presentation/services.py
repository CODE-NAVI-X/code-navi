"""Presentation generation service.

Two-stage, backend-driven pipeline (page-level SSE):

  stage 1  knowledge point -> 3..6 :class:`SceneOutline` (one kernel run)
  stage 2  each outline   -> one  :class:`Slide`        (one kernel run per page)

Every model call goes through ``code_navi.providers.create_provider`` and the
kernel's ``AgentRuntime``, so each page produces an auditable Event log and no
vendor SDK is ever constructed in this module.  When no online provider is
configured (or the LLM output cannot be parsed), deterministic rule-based
fallbacks keep the pipeline demoable offline — mirroring the learning module's
Mock fallback contract.

The stream is *page-level* (not token-level): the backend drives the loop and
emits one SSE event per finished page, so the user can start reading page N
while page N+1 is still being generated.  This is the backend-driven design the
team's functional mailbox asked for, instead of the frontend driving repeated
requests.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from code_navi.providers import ProviderSettings, create_provider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from ..models import NotebookItemModel
from .prompts import (
    OUTLINE_SYSTEM_PROMPT,
    SLIDE_SYSTEM_PROMPT,
    outline_user_prompt,
    slide_user_prompt,
)
from .schemas import (
    LineElement,
    Presentation,
    PresentationGenerateRequest,
    SceneOutline,
    Slide,
    SlideBackground,
    TextElement,
)

load_dotenv()

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

_DEFAULT_TIMEOUT = 60.0  # seconds — slide generation can take a while
# deepseek-v4-flash is a reasoning model: it spends tokens on reasoning_content
# before emitting content.  A 2048 cap truncated every run (finish_reason=length,
# empty content), so the cap is set well above a full outline/slide deck.
_DEFAULT_MAX_TOKENS = 8192
_DEFAULT_TEMPERATURE = 0.3

_OUTLINE_COUNT_MIN = 4
_OUTLINE_COUNT_MAX = 10
# Per-page element cap: the prompt asks for ≤ 24, and this is a safety net so a
# model overshoot still produces an exportable, readable slide.
_SLIDE_MAX_ELEMENTS = 28

GenerationMode = Literal["model", "rules", "rules_fallback", "mixed"]

# ---------------------------------------------------------------------------
# Rule-based fallbacks (offline / unparseable)
# ---------------------------------------------------------------------------


def _mock_outlines(knowledge_point: str, style: str) -> list[SceneOutline]:
    """Deterministic 5-page outline when no online provider is available."""
    pages: list[tuple[str, str, list[str]]] = [
        (
            knowledge_point,
            f"认识「{knowledge_point}」：它是什么、为什么重要。",
            [f"本讲主题：{knowledge_point}", "学习目标：掌握核心概念与适用场景"],
        ),
        (
            "核心概念",
            "给出精确定义与关键术语。",
            [f"{knowledge_point} 的精确定义", "关键术语与符号约定"],
        ),
        (
            "原理解析",
            "讲解工作机制与关键步骤。",
            [f"{knowledge_point} 的工作流程或机制", "关键步骤与易错点"],
        ),
        (
            "典型例题与公式",
            "用一个例子或公式巩固理解。",
            ["核心公式或示例", "应用要点"],
        ),
        (
            "总结",
            "回顾要点并给出记忆锚点。",
            ["本讲要点回顾", "记忆锚点与下一步建议"],
        ),
    ]
    outlines: list[SceneOutline] = []
    for index, (title, desc, key_points) in enumerate(pages, start=1):
        outlines.append(
            SceneOutline(
                id=f"slide_{index}",
                title=title,
                description=desc,
                key_points=key_points,
                order=index,
            )
        )
    return outlines


def _mock_slide(knowledge_point: str, outline: SceneOutline, index: int) -> Slide:
    """Deterministic single-page layout used when offline / on parse failure."""
    elements: list = []
    y = 56
    # Title band
    elements.append(
        TextElement(
            type="text",
            left=80,
            top=y,
            width=900,
            height=76,
            content=(
                f"<p style='font-size:34px;font-weight:700;'>{outline.title}</p>"
            ),
            defaultColor="#0f172a",
        )
    )
    y += 92
    elements.append(
        LineElement(
            type="line",
            left=80,
            top=y,
            width=900,
            height=2,
            strokeColor="#cbd5e1",
            strokeWidth=2,
        )
    )
    y += 28
    # Key points as bullets
    for point in outline.key_points:
        elements.append(
            TextElement(
                type="text",
                left=80,
                top=y,
                width=880,
                height=48,
                content=(
                    f"<p style='font-size:22px;line-height:1.6;'>• {point}</p>"
                ),
                defaultColor="#374151",
            )
        )
        y += 66
    # Footer: knowledge point + page number
    elements.append(
        TextElement(
            type="text",
            left=80,
            top=652,
            width=500,
            height=36,
            content=f"<p style='font-size:16px;color:#94a3b8;'>{knowledge_point}</p>",
            defaultColor="#94a3b8",
        )
    )
    elements.append(
        TextElement(
            type="text",
            left=1080,
            top=652,
            width=120,
            height=36,
            content=f"<p style='font-size:16px;text-align:right;color:#94a3b8;'>{index}</p>",
            defaultColor="#94a3b8",
            textAlign="right",
        )
    )
    return Slide(
        background=SlideBackground(color="#ffffff"),
        elements=elements,
    )


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def _strip_code_fence(raw: str) -> str:
    """Remove a surrounding ```json ... ``` fence if present."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return cleaned


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _events_dir() -> Path:
    """Directory where per-run Event JSONL logs are written."""
    return Path(os.getenv("CODE_NAVI_EVENTS_DIR") or Path("var") / "runs")


@dataclass
class PresentationGenerator:
    """Backend-driven generator: outlines, then one kernel run per page."""

    def _provider_settings(self, offline_json: str) -> ProviderSettings:
        """Pick the provider without constructing a vendor client here.

        Falls back to the offline mock provider whenever no DeepSeek key is
        configured, so the PoC stays runnable with zero credentials.
        """
        name = (os.getenv("CODE_NAVI_PROVIDER") or "").strip().lower()
        if not name:
            name = "deepseek" if DEEPSEEK_API_KEY else "mock"
        if name == "mock":
            return ProviderSettings("mock", None, offline_json)
        return ProviderSettings(
            name,
            os.getenv("CODE_NAVI_MODEL") or (DEEPSEEK_MODEL if name == "deepseek" else None),
            None,
            max_tokens=_DEFAULT_MAX_TOKENS,
            temperature=_DEFAULT_TEMPERATURE,
            timeout=_DEFAULT_TIMEOUT,
            # deepseek-v4-flash is a reasoning model; for structured JSON the
            # chain-of-thought only adds latency and burns the token cap, so the
            # PPT pipeline opts out (see OpenAIChatCompletionsAdapter.thinking).
            thinking="disabled" if name == "deepseek" else None,
        )

    def _run(
        self,
        system_prompt: str,
        agent_name: str,
        user_input: str,
        session_id: str,
        offline_json: str,
    ) -> tuple[str, str]:
        """Run one audited kernel call and return the raw output text."""
        agent = AgentSpec(
            name=agent_name,
            description="Generates a JSON payload for the presentation pipeline.",
            system_prompt=system_prompt,
            tool_names=(),
            output_format="json",
        )
        settings = self._provider_settings(offline_json)
        provider = create_provider(settings)
        runtime = AgentRuntime(provider, session_dir=_events_dir())
        result = runtime.run(
            agent,
            RuntimeRequest(
                user_input,
                session_id=f"presentation-{session_id}",
                metadata={"interface": "api", "agent": agent_name},
            ),
        )
        return result.output_text or "", settings.name

    # -- Stage 1 ------------------------------------------------------------

    def generate_outlines(
        self,
        knowledge_point: str,
        style: str,
        session_id: str,
        context: str | None = None,
    ) -> tuple[list[SceneOutline], GenerationMode, str]:
        """One kernel run to plan the pages; rule fallback on failure."""
        offline = json.dumps([o.model_dump() for o in _mock_outlines(knowledge_point, style)])
        raw, provider_name = self._run(
            OUTLINE_SYSTEM_PROMPT,
            "presentation_outlines",
            outline_user_prompt(knowledge_point, style, context),
            session_id,
            offline,
        )
        parsed = _strip_code_fence(raw)
        try:
            data = json.loads(parsed)
        except json.JSONDecodeError:
            logger.warning("Outlines JSON unparseable; using rule fallback.")
            return _mock_outlines(knowledge_point, style), "rules_fallback", provider_name
        if not isinstance(data, list):
            logger.warning("Outlines payload is not a list; using rule fallback.")
            return _mock_outlines(knowledge_point, style), "rules_fallback", provider_name
        outlines: list[SceneOutline] = []
        for index, entry in enumerate(data[: _OUTLINE_COUNT_MAX], start=1):
            if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
                continue
            key_points = entry.get("key_points") or []
            if not isinstance(key_points, list):
                key_points = []
            outlines.append(
                SceneOutline(
                    id=f"slide_{index}",
                    title=entry["title"][:120],
                    description=str(entry.get("description") or "")[:240],
                    key_points=[str(kp)[:160] for kp in key_points][:5],
                    order=index,
                )
            )
            if len(outlines) >= _OUTLINE_COUNT_MAX:
                break
        if len(outlines) < _OUTLINE_COUNT_MIN:
            logger.warning(
                "Fewer than %d outlines parsed; using rule fallback.", _OUTLINE_COUNT_MIN
            )
            return _mock_outlines(knowledge_point, style), "rules_fallback", provider_name
        mode: GenerationMode = "rules" if provider_name == "mock" else "model"
        return outlines, mode, provider_name

    # -- Stage 2 ------------------------------------------------------------

    def generate_slide(
        self,
        knowledge_point: str,
        outline: SceneOutline,
        style: str,
        session_id: str,
        context: str | None = None,
    ) -> tuple[Slide, GenerationMode, str]:
        """One kernel run per page; rule fallback on failure."""
        offline = _mock_slide(knowledge_point, outline, outline.order)
        raw, provider_name = self._run(
            SLIDE_SYSTEM_PROMPT,
            "presentation_slide",
            slide_user_prompt(
                knowledge_point,
                outline.title,
                outline.description,
                outline.key_points,
                style,
                context,
            ),
            session_id,
            json.dumps(offline.model_dump()),
        )
        parsed = _strip_code_fence(raw)
        try:
            data = json.loads(parsed)
        except json.JSONDecodeError:
            logger.warning("Slide JSON unparseable for '%s'; using rule fallback.", outline.title)
            return offline, "rules_fallback", provider_name
        if not isinstance(data, dict):
            logger.warning(
                "Slide payload not an object for '%s'; using rule fallback.", outline.title
            )
            return offline, "rules_fallback", provider_name
        try:
            slide = Slide.model_validate(data)
        except Exception as exc:  # noqa: BLE001 — validation errors fall back gracefully
            logger.warning(
                "Slide validation failed for '%s' (%s); using rule fallback.",
                outline.title,
                exc,
            )
            return offline, "rules_fallback", provider_name
        if len(slide.elements) > _SLIDE_MAX_ELEMENTS:
            # Keep the deck exportable/readable even if the model overshoots.
            slide.elements = slide.elements[: _SLIDE_MAX_ELEMENTS]
        mode: GenerationMode = "rules" if provider_name == "mock" else "model"
        return slide, mode, provider_name

    # -- SSE event stream ---------------------------------------------------

    def stream_presentation(
        self,
        request: PresentationGenerateRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Emit one dict per SSE event; persist the finished deck at the end.

        Event shape:
          {"type": "outlines", "data": [SceneOutline, ...]}
          {"type": "slide", "index": i, "total": n, "data": Slide}
          {"type": "done", "presentation": Presentation}
          {"type": "error", "error": str}
        """
        session_id = request.session_id or f"sess-{uuid4().hex[:16]}"
        try:
            outlines, outline_mode, provider_name = self.generate_outlines(
                request.knowledge_point, request.style, session_id, request.context
            )
            yield {
                "type": "outlines",
                "data": [o.model_dump() for o in outlines],
                "generation_mode": outline_mode,
                "provider_name": provider_name,
            }

            slides: list[Slide] = []
            generation_modes: list[GenerationMode] = [outline_mode]
            for index, outline in enumerate(outlines):
                slide, slide_mode, slide_provider = self.generate_slide(
                    request.knowledge_point,
                    outline,
                    request.style,
                    session_id,
                    request.context,
                )
                slides.append(slide)
                generation_modes.append(slide_mode)
                yield {
                    "type": "slide",
                    "index": index,
                    "total": len(outlines),
                    "data": slide.model_dump(),
                    "generation_mode": slide_mode,
                    "provider_name": slide_provider,
                }

            generation_mode = self._combined_mode(generation_modes)
            presentation = self._archive(
                db,
                request.knowledge_point,
                session_id,
                request.style,
                outlines,
                slides,
                generation_mode,
                provider_name,
                owner_principal_id=owner_principal_id,
            )
            # mode="json" renders datetime/Path etc. as JSON-safe primitives.
            yield {"type": "done", "presentation": presentation.model_dump(mode="json")}
        except Exception:  # noqa: BLE001 — convert internal details to a safe SSE event
            error_id = f"err-{uuid4().hex[:16]}"
            logger.exception("Presentation stream failed (error_id=%s).", error_id)
            yield {
                "type": "error",
                "error": {
                    "code": "presentation_generation_failed",
                    "message": "PPT 生成失败，请稍后重试。",
                    "error_id": error_id,
                },
            }

    @staticmethod
    def _combined_mode(modes: list[GenerationMode]) -> GenerationMode:
        distinct = set(modes)
        return modes[0] if len(distinct) == 1 else "mixed"

    def _archive(
        self,
        db: Session,
        knowledge_point: str,
        session_id: str,
        style: str,
        outlines: list[SceneOutline],
        slides: list[Slide],
        generation_mode: GenerationMode,
        provider_name: str,
        *,
        owner_principal_id: str | None = None,
    ) -> Presentation:
        """Persist the finished deck as a ``presentation`` notebook item."""
        presentation = Presentation(
            id=f"pres-{uuid4().hex[:16]}",
            knowledge_point=knowledge_point,
            session_id=session_id,
            style=style,
            slides=slides,
            generation_mode=generation_mode,
            provider_name=provider_name,
            created_at=datetime.now(UTC),
        )
        entry = NotebookItemModel(
            user_id=owner_principal_id or "poc-user",
            owner_principal_id=owner_principal_id,
            session_id=session_id,
            knowledge_id=knowledge_point,
            item_type="presentation",
            content=knowledge_point,
            extra_data={
                "presentation_id": presentation.id,
                "style": style,
                "outlines": [o.model_dump() for o in outlines],
                "slides": [s.model_dump() for s in slides],
                "generation_mode": generation_mode,
                "provider_name": provider_name,
            },
        )
        db.add(entry)
        db.commit()
        return presentation


__all__ = [
    "PresentationGenerator",
    "PresentationGenerateRequest",
    "SceneOutline",
    "Slide",
]
