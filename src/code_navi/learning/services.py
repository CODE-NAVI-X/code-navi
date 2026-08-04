"""Business-logic services for the learning module.

- ``PromptDecontaminationEngine`` isolates academic knowledge points from
  narrative / anecdotal contamination.
- ``QueryOrchestrator`` produces an explanation with citations and persists the
  result in the student notebook.

Every model call goes through ``code_navi.providers.create_provider`` and the
kernel's ``AgentRuntime``.  The module never instantiates a vendor SDK client
itself, so each explanation produces an auditable Event log and runs under the
kernel's deny-by-default permission layer with no tools granted.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from code_navi.providers import ProviderSettings, create_provider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from .models import NotebookItemModel
from .schemas import Citation, ExplainRequest, ExplainResponse

# ---------------------------------------------------------------------------
# Environment & logger
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

_DEFAULT_TIMEOUT = 30.0  # seconds
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.3

# ---------------------------------------------------------------------------
# Prompt-decontamination engine
# ---------------------------------------------------------------------------

_DECONTAMINATION_PASSPHRASE = (
    "Focus strictly on the academic or technical definition, mechanism, "
    "and evidence for the requested knowledge point.  Omit personal stories, "
    "analogies, marketing language, and unverified lore."
)

_SYSTEM_TEMPLATE = """\
你是一个严谨的学术知识解释助手。{passphrase}

请严格按以下 JSON 结构输出（不要输出任何其他文字）：

{{
  "summary": "300 字以内的精炼解释",
  "detail": "可选的扩展解释（可为 null）",
  "citations": [
    {{
      "source_title": "来源名称",
      "uri": "可解析的 URL 或 DOI（可为 null）",
      "snippet": "支持该解释的关键原文摘录"
    }}
  ]
}}

用户将提供知识点 (knowledge_point) 和角色风格 (persona)：
- persona = "beginner" → 用通俗语言，避免专业术语
- persona = "academic" → 保持学术严谨，可适度使用术语
- persona = "practitioner" → 突出工程/实践应用视角
"""

_USER_TEMPLATE = "knowledge_point: {knowledge_point}\npersona: {persona}"


@dataclass
class PromptDecontaminationEngine:
    """Isolates core academic content from narrative contamination.

    The passphrase is injected into the system prompt sent to the LLM,
    enforcing a clean, fact-based response style.
    """

    passphrase: str = _DECONTAMINATION_PASSPHRASE

    def decontaminate(self, knowledge_point: str) -> str:
        """Attach the stable academic guard used by online and offline flows."""
        return f"[decontaminated] {knowledge_point}\nGuard: {self.passphrase}"


# ---------------------------------------------------------------------------
# Agent declaration
# ---------------------------------------------------------------------------


def build_knowledge_explainer_agent(passphrase: str = _DECONTAMINATION_PASSPHRASE) -> AgentSpec:
    """Declare the knowledge-point explainer run by the kernel runtime.

    ``tool_names`` stays empty: explanation is a pure model call, so the run
    gets no tool permissions at all.
    """
    return AgentSpec(
        name="knowledge_explainer",
        description="Explains one academic knowledge point as validated JSON with citations.",
        system_prompt=_SYSTEM_TEMPLATE.format(passphrase=passphrase),
        tool_names=(),
        output_format="json",
    )


knowledge_explainer_agent = build_knowledge_explainer_agent()


# ---------------------------------------------------------------------------
# Offline fallback payload
# ---------------------------------------------------------------------------


def _offline_payload(knowledge_point: str) -> str:
    """Return a presenter-friendly offline response without exposing prompts."""
    return json.dumps(
        {
            "summary": (
                f"已完成“{knowledge_point}”的离线结构化解析，并通过 Kernel 运行时记录本次会话。"
            ),
            "detail": (
                "当前使用确定性的 Mock Provider，用于验证请求编排、事件审计、"
                "会话隔离和笔记归档链路；配置在线 Provider 后会返回完整知识解释。"
            ),
            "citations": [
                {
                    "source_title": "Code Navi 离线演示说明",
                    "uri": None,
                    "snippet": "本次响应由本地 Mock Provider 生成，未调用外部知识源。",
                }
            ],
        }
    )


def _events_dir() -> Path:
    """Directory where per-run Event JSONL logs are written."""
    return Path(os.getenv("CODE_NAVI_EVENTS_DIR") or Path("var") / "runs")


# ---------------------------------------------------------------------------
# Query orchestrator
# ---------------------------------------------------------------------------


@dataclass
class QueryOrchestrator:
    """Orchestrates: decontaminate → explain via kernel runtime → archive."""

    decontamination_engine: PromptDecontaminationEngine = field(
        default_factory=PromptDecontaminationEngine,
    )

    def _provider_settings(self, offline_response: str) -> ProviderSettings:
        """Pick the provider without ever constructing a vendor client here.

        Falls back to the offline mock provider whenever no DeepSeek key is
        configured, so the PoC stays runnable with zero credentials.
        """
        name = (os.getenv("CODE_NAVI_PROVIDER") or "").strip().lower()
        if not name:
            name = "deepseek" if DEEPSEEK_API_KEY else "mock"
        if name == "mock":
            return ProviderSettings("mock", None, offline_response)
        return ProviderSettings(
            name,
            os.getenv("CODE_NAVI_MODEL") or (DEEPSEEK_MODEL if name == "deepseek" else None),
            offline_response,
            max_tokens=_DEFAULT_MAX_TOKENS,
            temperature=_DEFAULT_TEMPERATURE,
            timeout=_DEFAULT_TIMEOUT,
        )

    def _parse_response(self, raw: str, knowledge_point: str, session_id: str) -> ExplainResponse:
        """Extract JSON from the LLM output, falling back gracefully."""
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON; using raw text as summary.")
            return ExplainResponse(
                knowledge_point=knowledge_point,
                session_id=session_id,
                summary=raw[:500],
                detail=None,
                citations=[],
            )
        citations: list[Citation] = []
        for c in data.get("citations", []) or []:
            citations.append(
                Citation(
                    source_title=c.get("source_title", "Unknown"),
                    uri=c.get("uri"),
                    snippet=c.get("snippet"),
                )
            )
        return ExplainResponse(
            knowledge_point=knowledge_point,
            session_id=session_id,
            summary=data.get("summary", raw[:500]),
            detail=data.get("detail"),
            citations=citations,
        )

    def explain(self, request: ExplainRequest, db: Session) -> ExplainResponse:
        """Run the full explain pipeline and persist the result."""

        # 1. Compose the user turn (decontamination guard baked into the prompt)
        session_id = request.session_id or f"sess-{uuid4().hex[:16]}"
        persona = request.persona or "academic"
        user_message = _USER_TEMPLATE.format(
            knowledge_point=self.decontamination_engine.decontaminate(request.knowledge_point),
            persona=persona,
        )

        # 2. One audited kernel run — no tools granted, Events persisted to disk.
        agent = build_knowledge_explainer_agent(self.decontamination_engine.passphrase)
        provider = create_provider(
            self._provider_settings(_offline_payload(request.knowledge_point))
        )
        runtime = AgentRuntime(provider, session_dir=_events_dir())
        result = runtime.run(
            agent,
            RuntimeRequest(
                user_message,
                session_id=f"learning-{session_id}",
                metadata={"interface": "api", "persona": persona, "session_id": session_id},
            ),
        )
        raw = result.output_text or ""

        # 3. Parse structured response
        response = self._parse_response(raw, request.knowledge_point, session_id)

        # 4. Optionally drop citations if the client doesn't want them
        if not request.include_citations:
            response.citations = []

        # 5. Archive to notebook
        notebook_entry = NotebookItemModel(
            user_id="poc-user",  # TODO: replace with real auth user id
            session_id=session_id,
            knowledge_id=request.knowledge_point,
            item_type="summary",
            content=response.summary,
            extra_data={
                "citations": [c.model_dump() for c in response.citations],
                "persona": request.persona,
                "detail": response.detail,
                "run_id": result.run_id,
                "event_log_path": result.event_log_path,
            },
        )
        db.add(notebook_entry)
        db.commit()

        return response


__all__ = [
    "PromptDecontaminationEngine",
    "QueryOrchestrator",
    "build_knowledge_explainer_agent",
    "knowledge_explainer_agent",
]
