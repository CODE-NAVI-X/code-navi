"""Static regression checks for the conversational research workspace."""

from pathlib import Path

PAGE = Path("frontend/app/(student)/research/page.tsx")
WORKSPACE = Path("frontend/components/research/ResearchConversation.tsx")
PROFILE = Path("frontend/components/research/ResearchProfilePanel.tsx")
PROVIDER = Path("frontend/components/research/ProviderStatusCard.tsx")
API = Path("frontend/lib/api/research.ts")
NEXT_CONFIG = Path("frontend/next.config.ts")


def test_research_page_uses_conversation_api_instead_of_fixed_sessions() -> None:
    api_source = API.read_text(encoding="utf-8")

    assert '"/api/v1/research/conversations"' in api_source
    message_path = (
        "/api/v1/research/conversations/"
        "${encodeURIComponent(conversationId)}/messages"
    )
    assert message_path in api_source
    assert "research-conversation.v1" in api_source
    assert "/api/v1/research/sessions" not in api_source


def test_research_workspace_is_chat_first_and_restorable() -> None:
    page_source = PAGE.read_text(encoding="utf-8")
    workspace_source = WORKSPACE.read_text(encoding="utf-8")

    assert "ResearchConversation" in page_source
    assert "code-navi.research.conversation-id" in workspace_source
    assert "本轮处理过程" in workspace_source
    assert "正在理解并整理研究画像" in workspace_source
    assert "基础规则（非模型）" in workspace_source
    assert "需求确认 Skill" in workspace_source
    assert "信息源检索 Skill" in workspace_source
    assert "五字段" not in workspace_source
    assert "missing_fields" not in workspace_source


def test_research_profile_explains_search_boundary() -> None:
    profile_source = PROFILE.read_text(encoding="utf-8")

    assert "当前对话不会自动联网检索" in profile_source
    assert "科研画像" in profile_source
    assert "候选研究问题" in profile_source


def test_provider_status_has_local_only_key_configuration_ui() -> None:
    provider_source = PROVIDER.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "输入 API Key" in provider_source
    assert "保存并测试连接" in provider_source
    assert 'autoComplete="new-password"' in provider_source
    assert "测试连接" in provider_source
    assert "API Key" in provider_source
    assert "localStorage.setItem" not in provider_source
    assert "/api/v1/research/provider/configuration" in api_source
    assert "20_000" in api_source


def test_research_api_has_a_bounded_request_timeout() -> None:
    api_source = API.read_text(encoding="utf-8")

    assert '"http://127.0.0.1:8000"' in api_source
    assert "const REQUEST_TIMEOUT_MS = 10_000" in api_source
    assert "controller.abort()" in api_source
    assert "科研服务在 ${timeoutMs / 1000} 秒内没有响应" in api_source
    assert "25_000" in api_source


def test_next_development_server_allows_documented_loopback_host() -> None:
    config_source = NEXT_CONFIG.read_text(encoding="utf-8")

    assert 'allowedDevOrigins: ["127.0.0.1", "localhost"]' in config_source
