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
PAPER_ANALYSIS = Path("frontend/components/research/PaperDeepAnalysisPanel.tsx")
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
    assert "模型未生成（需重试）" in workspace_source
    assert "Agent 失败，规则接管" not in workspace_source
    assert "系统未展示规则替代内容" in workspace_source
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


def test_paper_artifact_requests_allow_the_model_generation_window() -> None:
    api_source = API.read_text(encoding="utf-8")
    analysis_region = api_source.split(
        "export async function analyzeResearchPaper", 1
    )[1].split("export async function createUnderstandingQuestion", 1)[0]
    mindmap_region = api_source.split(
        "export async function generateResearchMindMap", 1
    )[1].split("export async function generateExperimentDesign", 1)[0]
    pipeline_region = api_source.split(
        "export async function createReproductionPipeline", 1
    )[1].split("export async function listReproductionPipelines", 1)[0]

    assert "const PAPER_ARTIFACT_TIMEOUT_MS = 120_000" in api_source
    assert "PAPER_ARTIFACT_TIMEOUT_MS" in analysis_region
    assert "PAPER_ARTIFACT_TIMEOUT_MS" in mindmap_region
    assert "PAPER_ARTIFACT_TIMEOUT_MS" in pipeline_region


def test_experiment_artifact_requests_allow_the_model_generation_window() -> None:
    api_source = API.read_text(encoding="utf-8")
    experiment_region = api_source.split(
        "export async function generateExperimentDesign", 1
    )[1].split("export async function createExperimentEvidenceBundle", 1)[0]
    draft_region = api_source.split(
        "export async function createExperimentCodeDraft", 1
    )[1].split("export async function createExperimentEvidenceBundle", 1)[0]

    assert "PAPER_ARTIFACT_TIMEOUT_MS" in experiment_region
    assert "PAPER_ARTIFACT_TIMEOUT_MS" in draft_region


def test_topic_difficulty_requests_allow_the_model_generation_window() -> None:
    api_source = API.read_text(encoding="utf-8")
    difficulty_region = api_source.split(
        "export async function generateTopicDifficultyAnalysis", 1
    )[1].split("export async function generateResearchPlan", 1)[0]

    assert "PAPER_ARTIFACT_TIMEOUT_MS" in difficulty_region


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


def test_research_workspace_displays_an_llm_conversation_plan() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    plan_source = PLAN.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "ResearchPlanPanel" in workspace_source
    assert "research_plan" in workspace_source
    assert "research-plan.v1" in api_source
    assert "模型研究计划" in plan_source
    assert "生成模型研究计划" in workspace_source
    assert "待确认或待验证" in plan_source
    assert "<PlanEntry entry={item.risk} />" in plan_source
    assert "<PlanEntry entry={item.mitigation} />" in plan_source


def test_research_plan_keeps_classification_data_out_of_the_visual_summary() -> None:
    plan_source = PLAN.read_text(encoding="utf-8")

    assert "ClassificationBadge" not in plan_source


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
    assert "generationModeLabel" in difficulty_source
    assert "GenerationFailure" in difficulty_source
    assert "rules_fallback" not in difficulty_source
    assert "分析元数据/摘要难点" in search_source


def test_experiment_design_discloses_model_or_rules_generation_mode() -> None:
    experiment_source = EXPERIMENT.read_text(encoding="utf-8")

    assert "generationModeLabel" in experiment_source
    assert "GenerationFailure" in experiment_source
    assert "rules_fallback" not in experiment_source
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


def test_reproduction_pipeline_defaults_to_compact_readable_summary() -> None:
    pipeline_source = REPRODUCTION_PIPELINE.read_text(encoding="utf-8")

    assert "核心复现目标" in pipeline_source
    assert "数据、基线与指标" in pipeline_source
    assert "完整实验路径" in pipeline_source
    assert "查看完整依据与待核对项" in pipeline_source
    assert "<details" in pipeline_source
    assert "text-base" in pipeline_source
    assert "leading-7" in pipeline_source
    assert "min-h-10" in pipeline_source
    assert "ClassificationBadge" not in pipeline_source


def test_experiment_design_groups_entries_into_readable_prose_without_badges() -> None:
    experiment_source = EXPERIMENT.read_text(encoding="utf-8")

    assert "ClassificationBadge" not in experiment_source
    assert 'entries.map((item) => item.content).join(" ")' in experiment_source
    assert "whitespace-pre-line" in experiment_source
    assert "text-base" in experiment_source
    assert "leading-7" in experiment_source


def test_research_panels_hide_classification_badges_without_changing_contracts() -> None:
    panel_sources = [
        (DIFFICULTY, DIFFICULTY.read_text(encoding="utf-8")),
        (EXPERIMENT_EVIDENCE, EXPERIMENT_EVIDENCE.read_text(encoding="utf-8")),
        (REPRODUCTION_EVALUATION, REPRODUCTION_EVALUATION.read_text(encoding="utf-8")),
        (CITATION, CITATION.read_text(encoding="utf-8")),
        (PAPER_DRAFT_REVIEW, PAPER_DRAFT_REVIEW.read_text(encoding="utf-8")),
    ]

    for path, source in panel_sources:
        assert "ClassificationBadge" not in source, path


def test_research_workflow_uses_the_five_primary_research_zones() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    workflow_source = WORKFLOW.read_text(encoding="utf-8")

    assert "当前阶段" in workflow_source
    assert "当前研究主题" in workflow_source
    assert "当前选择论文" in workflow_source
    assert "当前缺失信息" in workflow_source
    assert "唯一下一步" in workflow_source
    for label in (
        "研究起点",
        "方向与文献",
        "论文深度分析",
        "复现工作台",
        "证据与成果",
    ):
        assert label in workflow_source
    assert "总结已学习知识" not in workflow_source
    assert "检查用户理解程度" not in workflow_source
    assert "PaperDraftReviewPanel" in workspace_source
    assert "ResearchMindMapPanel" in workspace_source


def test_research_profile_hides_context_as_a_primary_display_field() -> None:
    profile_source = PROFILE.read_text(encoding="utf-8")

    assert "对象与场景" not in profile_source
    assert "readiness.score" not in profile_source
    assert "当前缺失信息" in profile_source


def test_research_page_groups_paper_analysis_and_mindmap_before_the_workbench() -> None:
    workspace_source = WORKSPACE.read_text(encoding="utf-8")
    paper_source = PAPER_ANALYSIS.read_text(encoding="utf-8")

    assert "PaperDeepAnalysisPanel" in workspace_source
    assert workspace_source.index("research-section-paper-analysis") < workspace_source.index(
        "research-section-mindmap"
    ) < workspace_source.index("research-section-workbench")
    assert "自动寻找公开论文" in paper_source
    assert "待核验内容" in paper_source
    assert "GenerationFailure" in paper_source
    assert "rules_fallback" not in paper_source
    assert "读取论文并生成分析" in paper_source
    assert "上传本地 PDF" in paper_source
    api_source = API.read_text(encoding="utf-8")
    assert "analyzeResearchPaperUpload" in api_source
    assert "<details" in paper_source


def test_research_primary_content_does_not_use_ten_or_eleven_pixel_text() -> None:
    for path in (WORKSPACE, PROFILE, WORKFLOW, PAPER_ANALYSIS):
        source = path.read_text(encoding="utf-8")
        assert "text-[10px]" not in source
        assert "text-[11px]" not in source


def test_research_conversation_keeps_the_selected_paper_in_the_primary_flow() -> None:
    conversation_source = WORKSPACE.read_text(encoding="utf-8")
    pipeline_source = REPRODUCTION_PIPELINE.read_text(encoding="utf-8")

    assert 'const [selectedPaperTitle, setSelectedPaperTitle]' in conversation_source
    assert 'selectedPaperTitle={selectedPaperTitle}' in conversation_source
    assert 'onPipelineSaved={(pipeline) =>' in conversation_source
    assert 'onPipelineSaved?: (pipeline: ReproductionPipeline) => void;' in pipeline_source
    assert 'onPipelineSaved?.(savedPipeline);' in pipeline_source


def test_paper_analysis_embeds_evidence_bound_understanding_checks() -> None:
    paper_source = PAPER_ANALYSIS.read_text(encoding="utf-8")
    academic_search_source = ACADEMIC_SEARCH.read_text(encoding="utf-8")

    assert "createUnderstandingQuestion" in paper_source
    assert "assessUnderstandingAnswer" in paper_source
    assert "source_scope" in paper_source
    assert "paper-analysis-section-${item.section_key}" in paper_source
    assert "const paperSections = analysis?.paper_reading?.sections ?? []" in paper_source
    assert "item.chapter_key" in paper_source
    assert "尚未生成本章节的针对性分析" in paper_source
    assert "bundleId: bundle.bundle_id" in academic_search_source


def test_mindmap_nodes_jump_to_stable_paper_analysis_anchors() -> None:
    mindmap_source = MINDMAP.read_text(encoding="utf-8")

    assert "paper-analysis-section-${sectionKey}" in mindmap_source
    assert "scrollIntoView" in mindmap_source
    assert "focus" in mindmap_source


def test_mindmap_generation_is_explicit_and_discloses_a_real_failure() -> None:
    mindmap_source = MINDMAP.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert "generateResearchMindMap" in mindmap_source
    assert "生成科研思维导图" in mindmap_source
    assert "本次未生成科研建议" in mindmap_source
    assert "系统没有使用规则模板替代本次分析" in mindmap_source
    assert "/research-mindmap" in api_source


def test_open_access_actions_are_click_only_and_do_not_claim_full_text() -> None:
    api_source = API.read_text(encoding="utf-8")
    search_source = ACADEMIC_SEARCH.read_text(encoding="utf-8")

    assert "researchPaperLinks" in api_source
    assert "https://doi.org/" in api_source
    assert "https://arxiv.org/pdf/" in api_source
    assert "在新窗口打开 arXiv PDF" in search_source
    assert "不会自动下载或缓存 PDF" in search_source
    assert 'rel="noreferrer"' in search_source
