"""DeepSeek coverage for guarded research-clarification guidance."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.providers import (  # noqa: E402
    ProviderConfigurationError,
    ProviderSettings,
    create_provider,
)
from code_navi.research.llm import (  # noqa: E402
    DEEPSEEK_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    DeepSeekGuidanceProvider,
    ProviderGuidanceGenerator,
)
from code_navi.research.router import _service  # noqa: E402
from code_navi.research.rules import next_question  # noqa: E402
from code_navi.research.schemas import ResearchState  # noqa: E402
from code_navi.server import app  # noqa: E402
from kernel.core import ContentBlock, Message  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_service_generator() -> Generator[None, None, None]:
    original = _service.guidance_generator
    yield
    _service.guidance_generator = original


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


class FakeDeepSeekProvider:
    def __init__(self, responses: list[str] | None = None, error: Exception | None = None) -> None:
        self.responses = responses or []
        self.error = error
        self.calls = 0

    def complete(self, _messages: object) -> SimpleNamespace:
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(
            message=Message(
                "assistant",
                (ContentBlock("text", {"text": self.responses.pop(0)}),),
            )
        )


def _question() -> object:
    question = next_question(ResearchState())
    assert question is not None
    return question


def _configure_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-value-123456")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")


def _guidance_json(*, suggested_value: str | None = None) -> str:
    import json

    return json.dumps(
        {
            "reply": "已记录研究领域，接下来请收窄核心问题。",
            "next_question": "你最想比较哪一种学习反馈效果？",
            "options": ["比较即时反馈", "比较延迟反馈", "分析学习体验"],
            "suggested_value": suggested_value,
        }
    )


def test_deepseek_provider_uses_chat_completions_and_existing_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            calls["client"] = kwargs

            def create(**request: object) -> SimpleNamespace:
                calls["request"] = request
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
                )

            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )

    _configure_deepseek(monkeypatch)
    monkeypatch.setattr("code_navi.research.llm.OpenAI", FakeClient)

    provider = DeepSeekGuidanceProvider()
    result = provider.complete(
        (Message("user", (ContentBlock("text", {"text": "{}"}),)),)
    )

    assert calls["client"] == {
        "api_key": "test-key-value-123456",
        "base_url": "https://deepseek.example/v1",
        "max_retries": 0,
    }
    assert calls["request"] == {
        "model": "deepseek-test",
        "messages": [{"role": "user", "content": "{}"}],
        "temperature": 0.2,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert result.metadata == {"provider": "deepseek", "model": "deepseek-test"}
    assert result.to_json()["message"]["role"] == "assistant"


def test_deepseek_defaults_and_cli_provider_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            calls["client"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_request: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
                    )
                )
            )

    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-value-123456")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setattr("code_navi.research.llm.OpenAI", FakeClient)

    provider = DeepSeekGuidanceProvider()
    provider.complete((Message("user", (ContentBlock("text", {"text": "{}"}),)),))

    assert calls["client"] == {
        "api_key": "test-key-value-123456",
        "base_url": DEEPSEEK_DEFAULT_BASE_URL,
        "max_retries": 0,
    }
    assert provider.model == DEEPSEEK_DEFAULT_MODEL
    monkeypatch.setenv("CODE_NAVI_MODEL", DEEPSEEK_DEFAULT_MODEL)
    cli_provider = create_provider(ProviderSettings.resolve())
    assert cli_provider.provider_name == "deepseek"


def test_deepseek_guidance_generates_validated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_deepseek(monkeypatch)
    fake = FakeDeepSeekProvider([_guidance_json()])
    monkeypatch.setattr("code_navi.research.llm.DeepSeekGuidanceProvider", lambda: fake)

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "generated"
    assert outcome.guidance is not None
    assert outcome.guidance.options == ["比较即时反馈", "比较延迟反馈", "分析学习体验"]
    assert fake.calls == 1


def test_deepseek_without_key_keeps_rules_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "unavailable"


def test_deepseek_missing_client_dependency_becomes_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_deepseek(monkeypatch)

    def unavailable_provider() -> None:
        raise ProviderConfigurationError("DeepSeek support is not installed")

    monkeypatch.setattr("code_navi.research.llm.DeepSeekGuidanceProvider", unavailable_provider)

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"


@pytest.mark.parametrize(
    "model_text",
    [
        "not JSON",
        '{"reply":"ok","next_question":"next","options":["only", "two"]}',
    ],
)
def test_deepseek_invalid_output_becomes_safe_failure(
    monkeypatch: pytest.MonkeyPatch, model_text: str
) -> None:
    _configure_deepseek(monkeypatch)
    fake = FakeDeepSeekProvider([model_text])
    monkeypatch.setattr(
        "code_navi.research.llm.DeepSeekGuidanceProvider", lambda: fake
    )

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"


@pytest.mark.parametrize("error", [TimeoutError("network timeout"), OSError("network unavailable")])
def test_deepseek_timeout_or_network_error_becomes_safe_failure(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    _configure_deepseek(monkeypatch)
    fake = FakeDeepSeekProvider(error=error)
    monkeypatch.setattr(
        "code_navi.research.llm.DeepSeekGuidanceProvider", lambda: fake
    )

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"


def test_deepseek_timeout_guard_becomes_safe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowProvider:
        def complete(self, _messages: object) -> SimpleNamespace:
            time.sleep(0.05)
            return SimpleNamespace(message=Message("assistant", ()))

    _configure_deepseek(monkeypatch)
    monkeypatch.setattr("code_navi.research.llm.DeepSeekGuidanceProvider", SlowProvider)

    outcome = ProviderGuidanceGenerator(timeout_seconds=0.001).generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=_question(),  # type: ignore[arg-type]
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"


def test_deepseek_suggested_value_replaces_uncertainty_in_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_deepseek(monkeypatch)
    fake = FakeDeepSeekProvider(
        [
            _guidance_json(),
            _guidance_json(suggested_value="比较两种教学反馈策略的学习效果"),
        ]
    )
    monkeypatch.setattr("code_navi.research.llm.DeepSeekGuidanceProvider", lambda: fake)
    _service.guidance_generator = ProviderGuidanceGenerator()

    session_id = client.post("/api/v1/research/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    )
    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "我不知道，有什么推荐吗"},
    ).json()

    assert body["generation_mode"] == "llm"
    assert body["state"]["core_question"] == "比较两种教学反馈策略的学习效果"
    assert body["state"]["core_question"] != "我不知道，有什么推荐吗"
    assert body["turns"][-1]["input_mode"] == "llm_suggested"
