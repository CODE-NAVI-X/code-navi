"""Unit tests for the presentation (knowledge-PPT) generation feature.

Covers schema construction, rule-based offline fallbacks, the backend-driven
SSE event stream (outlines → slide × N → done), persistence to the notebook,
and the kernel-routing invariant (no vendor SDK imports, no tools granted).

All tests use ``sqlite:///:memory:`` and ``CODE_NAVI_PROVIDER=mock`` so the
pipeline runs entirely offline and repeatedly.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi imports execute.
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning.models import NotebookItemModel  # noqa: E402
from code_navi.learning.presentation import services as pres_services  # noqa: E402
from code_navi.learning.presentation.schemas import (  # noqa: E402
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    LatexElement,
    PresentationGenerateRequest,
    SceneOutline,
    ShapeElement,
    Slide,
    TextElement,
)
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_event_logs(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep kernel Event JSONL out of the working tree during tests."""
    monkeypatch.setenv("CODE_NAVI_EVENTS_DIR", str(tmp_path_factory.mktemp("events")))


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the presentation pipeline fully offline, regardless of any .env key."""
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    """Recreate all tables before each test so tests are fully isolated."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a per-test database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to the in-memory database."""
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# 1.  Schema construction & discriminated union
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_five_element_types_discriminate(self) -> None:
        text = TextElement(
            type="text", left=80, top=50, width=700, height=70, content="<p>hi</p>"
        )
        shape = ShapeElement(
            type="shape", left=80, top=50, width=100, height=100, fill="#4f46e5"
        )
        latex = LatexElement(
            type="latex", left=80, top=50, width=400, height=60, latex="\\sum_{i=1}^{n} i"
        )
        slide = Slide(elements=[text, shape, latex])
        assert len(slide.elements) == 3
        assert [e.type for e in slide.elements] == ["text", "shape", "latex"]

    def test_roundtrip_model_dump_validate(self) -> None:
        slide = Slide(
            background={"type": "solid", "color": "#f8fafc"},
            elements=[
                TextElement(
                    type="text", left=80, top=50, width=700, height=70, content="<p>t</p>"
                )
            ],
        )
        restored = Slide.model_validate(json.loads(slide.model_dump_json()))
        assert restored.background.color == "#f8fafc"
        assert restored.elements[0].type == "text"

    def test_rejects_unknown_element_type(self) -> None:
        with pytest.raises(ValidationError):
            Slide(
                elements=[
                    {
                        "type": "video",  # not allowed in iteration one
                        "left": 0,
                        "top": 0,
                        "width": 100,
                        "height": 100,
                    }
                ]
            )


# ---------------------------------------------------------------------------
# 2.  Offline rule fallbacks
# ---------------------------------------------------------------------------


class TestOfflineFallbacks:
    def test_mock_outlines_are_4_to_10_pages(self) -> None:
        req = PresentationGenerateRequest(knowledge_point="DHCP 四阶段")
        outlines = pres_services._mock_outlines(req.knowledge_point, req.style)
        assert 4 <= len(outlines) <= 10
        titles = [o.title for o in outlines]
        assert any("核心概念" in t for t in titles)
        assert any("总结" in t for t in titles)
        assert all(o.order == i for i, o in enumerate(outlines, start=1))

    def test_mock_slide_elements_stay_in_canvas(self) -> None:
        outline = SceneOutline(
            id="slide_1",
            title="封面",
            description="介绍",
            key_points=["要点A", "要点B"],
            order=1,
        )
        slide = pres_services._mock_slide("TCP", outline, 1)
        assert len(slide.elements) >= 3
        for el in slide.elements:
            assert el.left >= 0 and el.top >= 0
            assert el.left + el.width <= CANVAS_WIDTH
            assert el.top + el.height <= CANVAS_HEIGHT

    def test_generate_outlines_mock_returns_valid_deck(self) -> None:
        gen = pres_services.PresentationGenerator()
        req = PresentationGenerateRequest(knowledge_point="B树")
        outlines = gen.generate_outlines(req.knowledge_point, req.style, "sess-t")
        assert 4 <= len(outlines) <= 10
        assert all(isinstance(o, SceneOutline) for o in outlines)

    def test_generate_slide_mock_returns_valid_slide(self) -> None:
        gen = pres_services.PresentationGenerator()
        outlines = gen.generate_outlines("排序算法", "professional", "sess-t")
        slide = gen.generate_slide("排序算法", outlines[0], "professional", "sess-t")
        assert isinstance(slide, Slide)
        assert len(slide.elements) >= 1


# ---------------------------------------------------------------------------
# 3.  Backend-driven SSE event stream
# ---------------------------------------------------------------------------


class TestEventStream:
    def test_stream_emits_outlines_slides_done(self, db: Session) -> None:
        gen = pres_services.PresentationGenerator()
        req = PresentationGenerateRequest(
            knowledge_point="DHCP 四阶段报文交互",
            session_id="sess-stream",
        )
        events = list(gen.stream_presentation(req, db))

        assert events[0]["type"] == "outlines"
        outline_data = events[0]["data"]
        assert isinstance(outline_data, list)
        assert 4 <= len(outline_data) <= 10

        slide_events = [e for e in events if e["type"] == "slide"]
        assert len(slide_events) == len(outline_data)
        for e in slide_events:
            assert e["data"]["background"]["type"] == "solid"
            assert len(e["data"]["elements"]) >= 1

        done = events[-1]
        assert done["type"] == "done"
        assert done["presentation"]["knowledge_point"] == "DHCP 四阶段报文交互"

    def test_stream_persists_presentation_notebook_item(self, db: Session) -> None:
        gen = pres_services.PresentationGenerator()
        req = PresentationGenerateRequest(
            knowledge_point="TCP 拥塞控制",
            session_id="sess-persist",
        )
        events = list(gen.stream_presentation(req, db))

        item = (
            db.query(NotebookItemModel)
            .filter_by(session_id="sess-persist", item_type="presentation")
            .first()
        )
        assert item is not None
        assert item.knowledge_id == "TCP 拥塞控制"
        slides = item.extra_data["slides"]
        assert len(slides) == len([e for e in events if e["type"] == "slide"])
        assert item.extra_data["presentation_id"].startswith("pres-")


# ---------------------------------------------------------------------------
# 4.  SSE API endpoint
# ---------------------------------------------------------------------------


class TestPresentationEndpoint:
    def test_generate_endpoint_streams_events(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/presentations/generate",
            json={"knowledge_point": "快速排序", "session_id": "sess-api"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        # Parse SSE: every `data: {...}` line followed by a blank line.
        types: list[str] = []
        for chunk in resp.text.split("\n\n"):
            for line in chunk.splitlines():
                if line.startswith("data: "):
                    event = json.loads(line[len("data: "):])
                    types.append(event["type"])
        assert types[0] == "outlines"
        assert "done" in types
        assert "slide" in types

    def test_generate_validates_input(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/presentations/generate",
            json={"knowledge_point": ""},
        )
        assert resp.status_code == 422

    def test_endpoint_persists_for_later_notebook_read(self, client: TestClient) -> None:
        client.post(
            "/api/v1/learning/presentations/generate",
            json={"knowledge_point": "红黑树", "session_id": "sess-nb"},
        )
        items = client.get(
            "/api/v1/learning/notebook", params={"session_id": "sess-nb"}
        ).json()
        assert any(item["kind"] == "presentation" for item in items)


# ---------------------------------------------------------------------------
# 5.  Kernel-routing invariants
# ---------------------------------------------------------------------------


class TestKernelRouting:
    def test_presentation_module_does_not_import_vendor_sdk(self) -> None:
        source = Path(pres_services.__file__).read_text(encoding="utf-8")
        assert "from openai import" not in source
        assert "from anthropic import" not in source

    def test_deepseek_settings_disable_thinking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
        monkeypatch.delenv("CODE_NAVI_MODEL", raising=False)
        settings = pres_services.PresentationGenerator()._provider_settings("{}")
        assert settings.name == "deepseek"
        # Reasoning models truncate structured JSON on their chain-of-thought;
        # the PPT pipeline opts out so content returns directly.
        assert settings.thinking == "disabled"
        assert settings.max_tokens == 8192

    def test_explain_context_is_threaded_into_prompts(self) -> None:
        from code_navi.learning.presentation.prompts import (
            outline_user_prompt,
            slide_user_prompt,
        )

        context = "深度解析：TCP 是面向连接的可靠传输协议，使用三次握手建立连接。"
        outline = outline_user_prompt("TCP", "professional", context)
        assert context in outline

        slide = slide_user_prompt(
            "TCP",
            "核心概念",
            "定义",
            ["面向连接", "可靠传输"],
            "professional",
            context,
        )
        assert context in slide
        # Without context, no grounding section is emitted.
        assert "已有深度解析上下文" not in outline_user_prompt("TCP", "professional")

    def test_request_accepts_optional_context(self) -> None:
        req = PresentationGenerateRequest(
            knowledge_point="TCP", context="已有深度解析上下文素材"
        )
        assert req.context == "已有深度解析上下文素材"
        assert PresentationGenerateRequest(knowledge_point="UDP").context is None

    def test_stream_writes_auditable_event_log(self, db: Session) -> None:
        gen = pres_services.PresentationGenerator()
        req = PresentationGenerateRequest(
            knowledge_point="哈希表",
            session_id="sess-events",
        )
        list(gen.stream_presentation(req, db))

        item = (
            db.query(NotebookItemModel)
            .filter_by(session_id="sess-events", item_type="presentation")
            .first()
        )
        assert item is not None
        events_dir = Path(os.environ["CODE_NAVI_EVENTS_DIR"])
        log_files = list(events_dir.rglob("*.jsonl"))
        # One kernel run for outlines + one per page.
        assert len(log_files) >= 4
