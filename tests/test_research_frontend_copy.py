"""Static regression checks for the conversational research workspace."""

from pathlib import Path

PAGE = Path("frontend/app/(student)/research/page.tsx")
WORKSPACE = Path("frontend/components/research/ResearchConversation.tsx")
PROFILE = Path("frontend/components/research/ResearchProfilePanel.tsx")
PROVIDER = Path("frontend/components/research/ProviderStatusCard.tsx")
PLAN = Path("frontend/components/research/ResearchPlanPanel.tsx")
MINDMAP = Path("frontend/components/research/ResearchMindMapPanel.tsx")
DIFFICULTY = Path("frontend/components/research/ResearchDifficultyPanel.tsx")
EXPERIMENT = Path("frontend/components/research/ExperimentDesignPanel.tsx")
CITATION = Path("frontend/components/research/CitationScaffoldPanel.tsx")
PAPER_DRAFT_REVIEW = Path("frontend/components/research/PaperDraftReviewPanel.tsx")
REPRODUCTION_EVALUATION = Path(
    "frontend/components/research/ReproductionEvaluationPanel.tsx"
)
ACADEMIC_SEARCH = Path("frontend/components/research/AcademicSearchPanel.tsx")
EXPERIMENT_EVIDENCE = Path("frontend/components/research/ExperimentEvidencePanel.tsx")
REPRODUCTION_PIPELINE = Path("frontend/components/research/ReproductionPipelinePanel.tsx")
WORKFLOW = Path("frontend/components/research/ResearchWorkflowNav.tsx")
API = Path("frontend/lib/api/research.ts")
NEXT_CONFIG = Path("frontend/next.config.ts")


def test_research_page_uses_conversation_api_instead_of_fixed_sessions() -> None:
    api_source = API.read_text(encoding="utf-8")

    assert '"/api/v1/research/conversations"' in api_source
    message_path = "/api/v1/research/conversations/${encodeURIComponent(conversationId)}/messages"
    assert message_path in api_source
    assert "research-conversation.v1" in api_source
    assert "/api/v1/research/sessions" not in api_source


def test_research_workspace_is_chat_first_and_restorable() -> None:
    page_source = PAGE.read_text(encoding="utf-8")
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "ResearchConversation" in page_source
    assert "RESEARCH_CONVERSATION_STORAGE_KEY" in workspace_source
    assert "code-navi.research.conversation-id" in api_source
    assert "本轮处理过程" in workspace_source
    assert "正在理解并整理研究画像" in workspace_source
    assert "基础规则（非模型）" in workspace_source
    assert "需求确认 Skill" in workspace_source
    assert "信息源检索 Skill" in workspace_source
    assert "context_provenance" in workspace_source
    assert "本会话来自已确认的 Learning 上下文" in workspace_source
    assert "查看保留的学习内容" in workspace_source
    assert "五字段" not in workspace_source
    assert "missing_fields" not in workspace_source


def test_research_profile_explains_search_boundary() -> None:
    profile_source = PROFILE.read_text(encoding="utf-8")

    assert "当前对话不会自动联网检索" in profile_source
    assert "只有你明确触发" in profile_source
    assert "下一阶段接入" not in profile_source
    assert "科研画像" in profile_source
    assert "候选研究问题" in profile_source


def test_provider_status_has_local_only_key_configuration_ui() -> None:
    provider_source = PROVIDER.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "输入 API Key" in provider_source
    assert "保存并测试连接" in provider_source
    assert 'autoComplete="new-password"' in provider_source
    assert "测试连接" in provider_source
    assert "网页配置已禁用" in provider_source
    assert "browser_configuration_enabled" in provider_source
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


def test_model_backed_conversation_turn_allows_more_time_than_restore() -> None:
    api_source = API.read_text(encoding="utf-8")
    send_region = api_source.split(
        "export async function sendResearchMessage", 1
    )[1].split("export async function getResearchProviderStatus", 1)[0]

    assert "const MODEL_TURN_TIMEOUT_MS = 25_000" in api_source
    assert "MODEL_TURN_TIMEOUT_MS" in send_region


def test_next_development_server_allows_documented_loopback_host() -> None:
    config_source = NEXT_CONFIG.read_text(encoding="utf-8")
    env_example = Path("frontend/.env.example").read_text(encoding="utf-8")

    assert "allowedDevOrigins" in config_source
    assert '"127.0.0.1"' in config_source
    assert '"localhost"' in config_source
    assert "CODE_NAVI_ALLOWED_DEV_ORIGINS" in config_source
    assert "CODE_NAVI_ALLOWED_DEV_ORIGINS" in env_example
    assert "192.168.0.32" not in config_source
    assert "agentRules: false" in config_source


def test_research_workspace_displays_a_rules_based_conversation_plan() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    plan_source = PLAN.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "ResearchPlanPanel" in workspace_source
    assert "research_plan" in workspace_source
    assert "research-plan.v1" in api_source
    assert "规则研究计划" in plan_source
    assert "待确认或待验证" in plan_source
    assert "<PlanEntry entry={item.risk} />" in plan_source
    assert "<PlanEntry entry={item.mitigation} />" in plan_source


def test_research_workspace_exposes_a_traceable_mind_map_without_a_graph_runtime() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    mindmap_source = MINDMAP.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "ResearchMindMapPanel" in workspace_source
    assert "research_mindmap" in workspace_source
    assert "research-mindmap.v1" in api_source
    assert "不联网" in mindmap_source
    assert "导出 SVG" in mindmap_source


def test_research_workspace_labels_direction_analysis_as_a_non_paper_fact() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    difficulty_source = DIFFICULTY.read_text(encoding="utf-8")
    search_source = Path("frontend/components/research/AcademicSearchPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "ResearchDifficultyPanel" in workspace_source
    assert "topic_difficulty_analysis" in workspace_source
    assert "不是论文精读或实验结论" in difficulty_source
    assert "模型个性化建议" in difficulty_source
    assert "模型失败后的规则降级" in difficulty_source
    assert "分析元数据/摘要难点" in search_source


def test_experiment_design_discloses_model_or_rules_generation_mode() -> None:
    experiment_source = EXPERIMENT.read_text(encoding="utf-8")

    assert "模型个性化建议" in experiment_source
    assert "模型失败后的规则降级" in experiment_source
    assert "我确认仅预览代码草案" in experiment_source
    assert "复制代码" in experiment_source
    assert "下载草案文本" in experiment_source
    assert "不写入项目" in experiment_source


def test_citation_panel_requires_an_explicit_offline_quality_check() -> None:
    citation_source = CITATION.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "运行引用完整性检查" in citation_source
    assert "仅在你点击后检查当前选择" in citation_source
    assert "不会自动联网" in citation_source
    assert "标记为已人工插入" in citation_source
    assert "下方是历史结果，请重新运行检查" in citation_source
    assert "来源—章节映射" in citation_source
    assert "不代表引用正确或论文可以投稿" in citation_source
    assert "/citation-quality-checks" in api_source
    assert "CitationQualityCheck" in api_source


def test_citation_panel_exposes_a_traceable_copyable_reference_draft() -> None:
    citation_source = CITATION.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "可核验参考文献草案" in citation_source
    assert "复制文本草案" in citation_source
    assert "查看原始来源" in citation_source
    assert "作者 / 导师集中核验清单" in citation_source
    assert "navigator.clipboard.writeText(referencePackage.copy_text)" in citation_source
    assert "/reference-draft-package" in api_source
    assert "ReferenceDraftPackage" in api_source


def test_submission_profile_is_explicit_and_never_claims_venue_compliance() -> None:
    panel_source = PAPER_DRAFT_REVIEW.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "SubmissionProfile" in api_source
    assert "submission-profile" in api_source
    assert "saveSubmissionProfile" in api_source
    assert "投稿准备档案" in panel_source
    assert "本地规则辅助，不代表满足任何会议或期刊要求" in panel_source
    assert "我确认执行投稿前检查" in panel_source


def test_submission_export_is_labeled_as_a_metadata_only_pre_submission_package() -> None:
    panel_source = PAPER_DRAFT_REVIEW.read_text(encoding="utf-8")

    assert "导出投稿前辅助包" in panel_source
    assert "不含初稿/修订稿全文" in panel_source
    assert "待作者或导师核对" in panel_source


def test_reproduction_evaluation_is_explicit_restorable_and_evidence_bounded() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    panel_source = REPRODUCTION_EVALUATION.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "ReproductionEvaluationPanel" in workspace_source
    assert "证据完整度评估" in workspace_source
    assert "我确认运行证据完整度评估" in panel_source
    assert "不可评估" in panel_source
    assert "查看评分依据" in panel_source
    assert "复现改进任务" in panel_source
    assert "接受任务" in panel_source
    assert "标记为已完成" in panel_source
    assert "不会联网、读取全文、执行代码或修改论文" in panel_source
    assert "不代表复现成功或论文质量" in workspace_source
    assert "/reproduction-evaluations" in api_source
    assert "/reproduction-improvement-tasks/" in api_source


def test_research_downstream_refreshes_only_from_saved_contracts() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    search_source = ACADEMIC_SEARCH.read_text(encoding="utf-8")
    pipeline_source = REPRODUCTION_PIPELINE.read_text(encoding="utf-8")
    experiment_source = EXPERIMENT_EVIDENCE.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "onEvidenceSaved" in search_source
    assert "evidenceVersion" in workspace_source
    assert "evidenceVersion" in pipeline_source
    assert "paper_id" in api_source
    assert "listReproductionPipelines" in experiment_source
    assert "related_plan_item" in experiment_source
    assert "不代表实验正确、完成或复现成功" in experiment_source
    assert "来源范围：{item.source_scope}" in experiment_source


def test_research_workflow_uses_the_five_step_primary_path() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    workflow_source = WORKFLOW.read_text(encoding="utf-8")

    assert "当前阶段" in workflow_source
    assert "当前缺失信息" in workflow_source
    assert "唯一下一步" in workflow_source
    for label in (
        "研究需求",
        "检索计划",
        "保存原始论文",
        "复现方案",
        "证据边界与下一步任务",
    ):
        assert label in workflow_source
    assert "PaperDraftReviewPanel" in workspace_source
    assert "ResearchMindMapPanel" in workspace_source
