"""Business-logic services for the learning module.

- ``PromptDecontaminationEngine`` isolates academic knowledge points from
  narrative / anecdotal contamination.
- ``DeepSeekLLM`` wraps the DeepSeek V4 Flash API (OpenAI-compatible).
- ``QueryOrchestrator`` produces an explanation with citations and persists the
  result in the student notebook.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session

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
# DeepSeek LLM wrapper
# ---------------------------------------------------------------------------


@dataclass
class DeepSeekLLM:
    """Thin wrapper around the DeepSeek V4 Flash API (OpenAI-compatible)."""

    client: OpenAI = field(init=False)

    def __post_init__(self) -> None:
        if not DEEPSEEK_API_KEY:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set.  Create a .env file or export the variable."
            )
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=_DEFAULT_TIMEOUT,
        )

    def chat(self, system_prompt: str, user_message: str) -> str:
        """Send a single-turn request and return the raw assistant text."""
        logger.debug("→ DeepSeek request: %s", user_message[:120])
        response = self.client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        content = response.choices[0].message.content or ""
        logger.debug("← DeepSeek response: %s", content[:120])
        return content


@dataclass
class OfflineLearningLLM:
    """Deterministic local fallback for the learning-module PoC."""

    def chat(self, _system_prompt: str, user_message: str) -> str:
        """Return the documented offline response shape without a network call."""
        return json.dumps(
            {
                "summary": user_message,
                "detail": "离线 PoC 回退响应；未调用外部模型。",
                "citations": [
                    {
                        "source_title": "PoC stub citation",
                        "uri": None,
                        "snippet": "Deterministic offline learning-module fallback.",
                    }
                ],
            }
        )


# ---------------------------------------------------------------------------
# Query orchestrator
# ---------------------------------------------------------------------------


@dataclass
class QueryOrchestrator:
    """Orchestrates: decontaminate → explain with citations → archive to notebook."""

    decontamination_engine: PromptDecontaminationEngine = field(
        default_factory=PromptDecontaminationEngine,
    )

    def _build_system_prompt(self) -> str:
        return _SYSTEM_TEMPLATE.format(passphrase=self.decontamination_engine.passphrase)

    def _parse_response(self, raw: str, knowledge_point: str) -> ExplainResponse:
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
            summary=data.get("summary", raw[:500]),
            detail=data.get("detail"),
            citations=citations,
        )

    def explain(self, request: ExplainRequest, db: Session) -> ExplainResponse:
        """Run the full explain pipeline and persist the result."""

        # 1. Compose prompts (decontamination passphrase baked into system prompt)
        system_prompt = self._build_system_prompt()
        user_message = _USER_TEMPLATE.format(
            knowledge_point=self.decontamination_engine.decontaminate(request.knowledge_point),
            persona=request.persona or "academic",
        )

        # 2. Use the configured provider when available; otherwise stay offline.
        llm = DeepSeekLLM() if DEEPSEEK_API_KEY else OfflineLearningLLM()
        raw = llm.chat(system_prompt, user_message)

        # 3. Parse structured response
        response = self._parse_response(raw, request.knowledge_point)

        # 4. Optionally drop citations if the client doesn't want them
        if not request.include_citations:
            response.citations = []

        # 5. Archive to notebook
        notebook_entry = NotebookItemModel(
            user_id="poc-user",  # TODO: replace with real auth user id
            knowledge_id=request.knowledge_point,
            item_type="summary",
            content=response.summary,
            extra_data={
                "citations": [c.model_dump() for c in response.citations],
                "persona": request.persona,
                "detail": response.detail,
            },
        )
        db.add(notebook_entry)
        db.commit()

        return response
