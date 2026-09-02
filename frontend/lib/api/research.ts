/** Browser client for the versioned conversational research API. */

export const RESEARCH_CONVERSATION_SCHEMA = "research-conversation.v1" as const;
export const RESEARCH_CONVERSATION_STORAGE_KEY =
  "code-navi.research.conversation-id";

export type ResearchStage = "exploring" | "focusing" | "ready_for_plan";
export type GenerationMode = "agent" | "rules" | "rules_fallback";
export type RecommendedAction =
  | "continue_dialogue"
  | "review_profile"
  | "prepare_search";

export interface ResearchProfile {
  topic: string | null;
  motivation: string | null;
  research_questions: string[];
  candidate_questions: string[];
  context: string | null;
  methods: string[];
  data_requirements: string | null;
  evidence_preferences: string[];
  time_scope: string | null;
  constraints: string[];
  expected_output: string | null;
  assumptions: string[];
  uncertainties: string[];
}

export interface ResearchReadiness {
  score: number;
  stage: ResearchStage;
  can_prepare_search: boolean;
  reasons: string[];
}

export type ResearchPlanClassification = "inference" | "to_verify";

export interface ResearchPlanEntry {
  content: string;
  classification: ResearchPlanClassification;
  basis: string;
  /** Checkpoint-3 evidence contract; absent in plans stored before it. */
  relevance?: string | null;
  suggested_action?: string | null;
}

export interface ResearchPlanRisk {
  risk: ResearchPlanEntry;
  mitigation: ResearchPlanEntry;
}

export interface ReadingReport {
  schema_version: "reading-report.v1";
  report_id: string;
  paper_url: string;
  title: string;
  content: string;
  source_scope: "user_submitted_text_unverified";
  created_at: string;
}

export interface ReproductionConditions {
  schema_version: "reproduction-conditions.v1";
  hardware?: string | null;
  vram?: string | null;
  operating_system?: string | null;
  python_environment?: string | null;
  available_time?: string | null;
  reproduction_goal?: string | null;
  updated_at: string;
}

export interface ConversationResearchPlan {
  schema_version: "research-plan.v1";
  research_title: ResearchPlanEntry;
  research_goal: ResearchPlanEntry;
  candidate_methods_or_baselines: ResearchPlanEntry[];
  suggested_datasets_or_metrics: ResearchPlanEntry[];
  two_week_mvp_plan: ResearchPlanEntry[];
  risks_and_mitigations: ResearchPlanRisk[];
  suggested_search_keywords: string[];
  pending_items: ResearchPlanEntry[];
  core_judgment?: string | null;
  next_action?: string | null;
  provenance_note: string;
  generation_mode: "llm" | "rules";
  run_id: string | null;
  event_count: number;
}

export interface ReproductionConditionsInput {
  hardware?: string | null;
  vram?: string | null;
  operating_system?: string | null;
  python_environment?: string | null;
  available_time?: string | null;
  reproduction_goal?: string | null;
}

export type ResearchMindMapNodeStatus =
  | "confirmed"
  | "inference"
  | "to_verify"
  | "evidence"
  | "risk";

export interface ResearchMindMapSource {
  label: string;
  url: string;
  accessed_at: string;
}

export interface ResearchMindMapNode {
  id: string;
  label: string;
  status: ResearchMindMapNodeStatus;
  detail: string;
  /** Program-derived link to a paper-analysis section; never model-authored. */
  section_key: string | null;
  sources: ResearchMindMapSource[];
}

export interface ResearchMindMapEdge {
  source_id: string;
  target_id: string;
  relation: string;
}

export interface ResearchMindMap {
  schema_version: "research-mindmap.v1";
  root_node_id: string;
  nodes: ResearchMindMapNode[];
  edges: ResearchMindMapEdge[];
  generation_mode: "rules" | "llm";
  run_id: string | null;
  event_count: number;
  generated_at: string | null;
  provenance_note: string;
}

export interface SelectedResearchPaper {
  bundle_id: string;
  title: string;
  url: string;
  authors: string[];
  year: number | null;
  source_name: string;
  doi: string | null;
  arxiv_id: string | null;
  abstract_excerpt: string | null;
  paper_kind: string | null;
  abstract_available: boolean;
}

export type AnalysisClassification = "fact" | "inference" | "to_verify";

export interface EvidenceReference {
  bundle_id: string;
  paper_url: string;
  title: string;
  source_name: string;
  year: number | null;
  evidence_level: "metadata" | "abstract" | "full_text";
  evidence_summary: string | null;
}

export type AreaCode =
  | "research_goal"
  | "research_motivation"
  | "method_difficulty"
  | "data_practice_difficulty";

export interface ResearchAnalysisItem {
  area: string;
  area_code?: AreaCode | null;
  content: string;
  classification: AnalysisClassification;
  basis: string;
  source_scope: "profile_and_plan_only" | "metadata_and_abstract_only" | "full_text_user_triggered";
  /** Program-derived from area; the model never produces this value. */
  section_key: string;
  chapter_key?: string | null;
  chapter_order?: number | null;
  capability_note?: string | null;
  relevance?: string | null;
  suggested_action?: string | null;
  evidence_refs: EvidenceReference[];
}

export interface TopicDifficultyAnalysis {
  schema_version: "topic-difficulty-analysis.v1";
  title: string;
  information_scope: "profile_and_plan_only" | "metadata_and_abstract_only" | "full_text_user_triggered";
  core_judgment?: string | null;
  next_action?: string | null;
  items: ResearchAnalysisItem[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface PaperAnalysis {
  schema_version: "paper-analysis.v1";
  title: string;
  paper_url: string;
  information_scope: "metadata_and_abstract_only" | "full_text_user_triggered";
  abstract_available: boolean;
  core_judgment?: string | null;
  summary?: string | null;
  next_action?: string | null;
  items: ResearchAnalysisItem[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
  paper_reading: PaperReadingEvidence | null;
}

export interface PaperReadingEvidence {
  schema_version: "paper-reading.v1";
  source_url: string;
  page_count: number;
  pages_read: number;
  text_excerpt: string;
  sections: PaperReadingSection[];
}

export interface PaperReadingSection {
  key: string;
  title: string;
  order: number;
  text: string;
}

export type UnderstandingCheckStatus =
  | "not_started"
  | "question_ready"
  | "answer_submitted"
  | "needs_explanation"
  | "partially_understood"
  | "understood"
  | "generation_failed";

export interface UnderstandingCheck {
  schema_version: "understanding-check.v1";
  check_id: string;
  conversation_id: string;
  paper_url: string;
  bundle_id: string;
  section_key: string;
  question: string;
  question_basis: string;
  source_scope: "metadata_only" | "metadata_and_abstract_only";
  answer: string | null;
  assessment: string | null;
  missing_points: string[];
  correct_points: string[];
  explanation: string | null;
  example: string | null;
  recommended_next_action: string | null;
  status: UnderstandingCheckStatus;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * Derive a paper-analysis section key from an area label. Mirrors the Python
 * `section_key_for_area` map so mind-map nodes and paper-analysis anchors share
 * one program-controlled vocabulary; the model never produces these keys.
 */
export function sectionKeyForArea(area: string): string {
  const normalized = (area ?? "").trim();
  const mapping: Array<[string, string]> = [
    ["待核验", "to_verify"],
    ["研究问题", "research_question"],
    ["问题", "research_question"],
    ["核心方法", "core_method"],
    ["方法", "core_method"],
    ["数据集", "dataset"],
    ["数据", "dataset"],
    ["贡献", "contribution"],
    ["背景", "background"],
    ["动机", "motivation"],
    ["实验设计", "experiment"],
    ["实验", "experiment"],
    ["评价指标", "metrics"],
    ["指标", "metrics"],
    ["结果", "results"],
    ["局限", "limitations"],
    ["复现", "reproduction"],
  ];
  for (const [needle, key] of mapping) {
    if (normalized.includes(needle)) return key;
  }
  return "other";
}

/**
 * Describe open-access status only from saved metadata. An arXiv id suggests an
 * open preprint, but never that every version is open; without metadata it is
 * "待核验". The model must never decide this from memory.
 */
export function openAccessLabel(paper: {
  arxiv_id?: string | null;
  doi?: string | null;
}): { label: string; note: string } {
  if (paper.arxiv_id) {
    return {
      label: "arXiv 预印本（开放获取）",
      note: "存在 arXiv 标识不等于所有版本都开放获取，仍需人工核验。",
    };
  }
  if (paper.doi) {
    return {
      label: "待核验",
      note: "已保存 DOI，但开放获取状态需在原始来源人工核验。",
    };
  }
  return { label: "待核验", note: "检索元数据未提供开放获取状态。" };
}

/**
 * Return only user-clickable source links. This helper never fetches, downloads,
 * caches, or asserts that a PDF has been read. A DOI resolves through its
 * canonical source; an arXiv PDF is offered only for a validated arXiv id.
 */
export function researchPaperLinks(paper: {
  url: string;
  doi?: string | null;
  arxiv_id?: string | null;
}): { sourceUrl: string; arxivPdfUrl: string | null } {
  const sourceUrl = paper.doi ? `https://doi.org/${encodeURIComponent(paper.doi)}` : paper.url;
  const arxivId = paper.arxiv_id?.trim();
  const validArxivId = arxivId && /^\d{4}\.\d{4,5}(?:v\d+)?$/.test(arxivId);
  return {
    sourceUrl,
    arxivPdfUrl: validArxivId ? `https://arxiv.org/pdf/${arxivId}` : null,
  };
}

export type TaskType =
  | "classification"
  | "regression"
  | "clustering"
  | "retrieval"
  | "generation"
  | "other";

export interface MetricSpec {
  name: string;
  definition: string;
  formula?: string | null;
  higher_is_better: boolean;
  applies_to_task_type: TaskType[];
  source: "standard_catalog" | "model_suggested";
  to_verify: boolean;
}

export interface DatasetRef {
  name: string;
  url?: string | null;
  license_note?: string | null;
  to_verify: boolean;
}

export interface GenerateExperimentDesignRequest {
  user_confirmed: true;
  task_type_override?: TaskType | null;
}

export interface ExperimentDesign {
  schema_version: "experiment-design.v1";
  task_type: TaskType;
  hypothesis: ResearchPlanEntry;
  variables: ResearchPlanEntry[];
  metric_specs?: MetricSpec[];
  dataset_refs?: DatasetRef[];
  data_sources: ResearchPlanEntry[];
  baselines: ResearchPlanEntry[];
  metrics: ResearchPlanEntry[];
  steps: ResearchPlanEntry[];
  resources: ResearchPlanEntry[];
  risks: ResearchPlanEntry[];
  advisor_confirmation_items: ResearchPlanEntry[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface ExperimentCodeDraftFile { path: string; content: string; }
export interface ExperimentCodeDraft {
  schema_version: "experiment-code-draft.v1";
  title: string;
  directory_tree: string[];
  dependencies: string[];
  files: ExperimentCodeDraftFile[];
  run_instructions: string[];
  assumptions: string[];
  to_verify_items: string[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface ResearchConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  generation_mode: GenerationMode | null;
  run_id: string | null;
  event_count: number;
  intent: string | null;
  next_question: string | null;
  suggested_answers: string[];
  candidate_questions: string[];
  recommended_action: RecommendedAction | null;
  triggered_tool?: string | null;
  passive_tool_called?: string | null;
  stage_at_time?: string | null;
}

export interface ConfirmedContextProvenance {
  schema_version: "context-provenance.v1";
  transfer_id: string;
  source_module: "learning";
  source_object: { type: "notebook_item"; id: string };
  source_scope_id: string;
  target_module: "research";
  topic: string;
  summary: string;
  selected_content: Array<{
    kind: "summary" | "detail";
    label: string;
    content: string;
  }>;
  confirmed_at: string;
}

export interface ResearchConversationResponse {
  schema_version: typeof RESEARCH_CONVERSATION_SCHEMA;
  active_skill: "research-clarification";
  next_skill: "academic-search" | null;
  conversation_id: string;
  profile: ResearchProfile;
  readiness: ResearchReadiness;
  stage: ResearchStage;
  ready_for_plan: boolean;
  research_plan: ConversationResearchPlan | null;
  research_mindmap: ResearchMindMap | null;
  selected_paper: SelectedResearchPaper | null;
  paper_analysis: PaperAnalysis | null;
  topic_difficulty_analysis: TopicDifficultyAnalysis;
  reproduction_conditions?: ReproductionConditions | null;
  experiment_design: ExperimentDesign | null;
  reply: string;
  generation_mode: GenerationMode;
  recommended_action: RecommendedAction;
  next_question: string | null;
  suggested_answers: string[];
  candidate_questions: string[];
  messages: ResearchConversationMessage[];
  last_run_id: string | null;
  context_provenance: ConfirmedContextProvenance | null;
}

export interface ProviderStatusResponse {
  schema_version: "research-provider.v1";
  provider: string;
  model: string | null;
  configured: boolean;
  mode: "model" | "rules";
  configuration_method: "local_file" | "server_environment";
  browser_configuration_enabled: boolean;
  configuration_issue: "invalid_api_key" | "missing_model" | null;
}

export interface ProviderConnectionTestResponse {
  schema_version: "research-provider-test.v1";
  connected: boolean;
  provider: string;
  model: string | null;
  latency_ms: number;
  message: string;
  run_id: string | null;
  failure_code:
    | "invalid_credentials"
    | "model_unavailable"
    | "timeout"
    | "network_error"
    | "invalid_response"
    | "provider_error"
    | null;
}

export interface ConfigureProviderRequest {
  provider: "deepseek" | "openai";
  api_key: string;
  model: string | null;
  base_url: string | null;
}

export type AcademicSourceId = "arxiv" | "openalex" | "crossref";

export interface ResearchSearchSource {
  id: AcademicSourceId;
  display_name: string;
  homepage: string;
  enabled: boolean;
  scope: string;
}

export interface ResearchSearchPlan {
  schema_version: "research-search-plan.v1";
  conversation_id: string;
  query: string;
  alternative_queries: string[];
  sources: ResearchSearchSource[];
  evidence_scope: "metadata_and_abstract_only";
  user_confirmation_required: true;
  provenance_note: string;
}

export interface AcademicPaperResult {
  paper_id: string | null;
  title: string;
  authors: string[];
  year: number | null;
  source_name: string;
  url: string;
  identifier: string | null;
  doi: string | null;
  arxiv_id: string | null;
  abstract_excerpt: string | null;
  information_scope: "metadata_and_abstract_only";
  full_text_available: false;
  metadata_evidence: EvidenceStatement[];
  supporting_snippets: EvidenceStatement[];
  relevance: EvidenceStatement;
  paper_kind: EvidenceStatement | null;
  verification: EvidenceStatement;
}

export interface EvidenceStatement {
  content: string;
  classification: "fact" | "inference" | "to_verify";
  source_url: string | null;
  basis: string;
}

export interface AcademicSourceStatus {
  source: string;
  status:
    | "success"
    | "no_results"
    | "network_error"
    | "timeout"
    | "unavailable"
    | "disabled"
    | "not_allowed"
    | "dependency_missing";
  source_url: string | null;
  accessed_at: string;
  reason: string | null;
  duration_ms: number;
}

export interface ConversationEvidenceBundle {
  schema_version: "academic-evidence.v1";
  bundle_id: string;
  conversation_id: string;
  query: string;
  requested_sources: string[];
  allowed_sources: string[];
  queried_sources: string[];
  source_statuses: AcademicSourceStatus[];
  searched_at: string;
  papers: AcademicPaperResult[];
  source_links: Array<string | null>;
  failure_reasons: string[];
  provenance_note: string;
  tool_audit: Record<string, unknown> | null;
  cache_hit: boolean;
}

export type ExperimentEvidenceCategory =
  | "data_or_sample"
  | "setup"
  | "baseline_or_control"
  | "random_seed_or_reason"
  | "metric_or_result"
  | "result_table"
  | "chart_description"
  | "failure_or_limitation"
  | "ethics_or_data_governance"
  | "pending_item";

export interface ExperimentEvidenceItem {
  category: ExperimentEvidenceCategory;
  content: string;
  classification: AnalysisClassification;
  basis: string;
  source_scope: "user_submitted_text";
  related_plan_item: string | null;
  related_evidence_urls: string[];
}

export interface ExperimentEvidenceBundle {
  schema_version: "experiment-evidence.v1";
  bundle_id: string;
  conversation_id: string;
  experiment_name: ExperimentEvidenceItem;
  goal: ExperimentEvidenceItem;
  items: ExperimentEvidenceItem[];
  submitted_at: string;
  provenance_note: string;
}

export interface CreateExperimentEvidenceBundleRequest {
  experiment_name: string;
  goal: string;
  items: Array<Pick<ExperimentEvidenceItem, "category" | "content" | "classification"> & {
    related_plan_item?: string | null;
    related_evidence_urls?: string[];
  }>;
}

export type ReproductionEvaluationDimension =
  | "research_definition"
  | "source_traceability"
  | "reproduction_plan"
  | "execution_evidence"
  | "reflection_and_compliance";
export type ReproductionEvaluationStatus =
  | "not_evaluable"
  | "needs_revision"
  | "evidence_partial"
  | "checklist_complete";
export type ReproductionImprovementTaskStatus =
  | "pending"
  | "accepted"
  | "skipped"
  | "completed";
export interface ReproductionEvaluationEvidence {
  source_type:
    | "research_profile"
    | "selected_citation"
    | "reproduction_pipeline"
    | "experiment_evidence";
  source_id: string | null;
  label: string;
  classification: AnalysisClassification;
  information_scope: string;
  basis: string;
}
export interface ReproductionEvaluationDimensionResult {
  dimension: ReproductionEvaluationDimension;
  label: string;
  status: ReproductionEvaluationStatus;
  score: number | null;
  maximum_score: 20;
  issues: string[];
  evidence: ReproductionEvaluationEvidence[];
  fact_boundary: string;
  to_verify: string[];
  next_suggestions: string[];
}
export interface ReproductionEvaluationScoreSummary {
  earned_score: number;
  scored_maximum: number;
  total_maximum: 100;
  scored_dimension_count: number;
  unscored_dimension_count: number;
  display: string;
}
export interface ReproductionImprovementTask {
  schema_version: "reproduction-improvement-task.v1";
  task_id: string;
  evaluation_id: string;
  conversation_id: string;
  dimension: ReproductionEvaluationDimension;
  title: string;
  description: string;
  status: ReproductionImprovementTaskStatus;
  classification: "to_verify";
  basis: string;
  created_at: string;
  updated_at: string;
}
export interface ReproductionEvaluationCriterion {
  criterion_no: number;
  title: string;
  score: 0 | 1 | 2;
  basis: string;
  evidence_refs?: Array<{
    source_type: string;
    source_id?: string | null;
    label: string;
    classification: string;
    information_scope: string;
    basis: string;
  }> | null;
  improvement_task_id?: string | null;
}

export interface ReproductionEvaluationScoreSummaryV2 {
  earned_score: number;
  scored_maximum: number;
  total_maximum: 12;
  scored_criterion_count: number;
  unscored_criterion_count: number;
  display: string;
}

export interface ReproductionProjectEvaluationV1 {
  schema_version: "reproduction-project-evaluation.v1";
  evaluation_id: string;
  conversation_id: string;
  pipeline_id: string | null;
  pipeline_contract_status: "available" | "unavailable";
  selected_paper_count: number;
  experiment_record_count: number;
  score_summary: ReproductionEvaluationScoreSummary;
  dimensions: ReproductionEvaluationDimensionResult[];
  improvement_tasks: ReproductionImprovementTask[];
  created_at: string;
  boundary_note: string;
}

export interface ReproductionProjectEvaluationV2 {
  schema_version: "reproduction-project-evaluation.v2";
  evaluation_id: string;
  conversation_id: string;
  pipeline_id: string | null;
  pipeline_contract_status: "available" | "unavailable";
  selected_paper_count: number;
  experiment_record_count: number;
  total_score: number;
  score_summary: ReproductionEvaluationScoreSummaryV2;
  criteria: ReproductionEvaluationCriterion[];
  improvement_tasks: ReproductionImprovementTask[];
  created_at: string;
  boundary_note: string;
}

export type ReproductionProjectEvaluation =
  | ReproductionProjectEvaluationV1
  | ReproductionProjectEvaluationV2;

export interface ReproductionPipelineItem {
  content: string;
  classification: "fact" | "inference" | "to_verify";
  basis: string;
  source_scope: string;
}

export interface ReproductionPipeline {
  schema_version: "reproduction-pipeline.v1";
  pipeline_id: string;
  conversation_id: string;
  source_bundle_id: string;
  selected_paper: {
    url: string;
    title: string;
    source_name: string;
    year: number | null;
    identifier: string | null;
    abstract_scope: "metadata_only" | "metadata_and_abstract";
    abstract_excerpt: string | null;
  };
  reproduction_goal: ReproductionPipelineItem;
  research_question: ReproductionPipelineItem;
  known_method: ReproductionPipelineItem;
  data_and_sample_conditions: ReproductionPipelineItem[];
  candidate_baselines: ReproductionPipelineItem[];
  metrics: ReproductionPipelineItem[];
  experiment_steps: ReproductionPipelineItem[];
  resources: ReproductionPipelineItem[];
  risks: ReproductionPipelineItem[];
  ethics: ReproductionPipelineItem[];
  acceptance_criteria?: ReproductionPipelineItem[];
  confirmation_items: ReproductionPipelineItem[];
  tasks: Array<{
    task_id: string;
    title: string;
    description: string;
    classification: "fact" | "inference" | "to_verify";
    basis: string;
    source_scope: string;
    status: "not_started" | "evidence_linked";
    evidence_links: Array<{
      experiment_bundle_id: string;
      source_scope: "user_submitted_text_unverified";
      content: string;
      classification: "fact" | "inference" | "to_verify";
    }>;
  }>;
  two_week_mvp: ReproductionPipelineItem[];
  created_at: string;
  provenance_note: string;
  paper_reading: PaperReadingEvidence | null;
}

export interface PaperBlueprintReference {
  source_type: "research_profile" | "research_plan" | "academic_evidence" | "experiment_evidence";
  bundle_id: string | null;
  label: string;
  classification: AnalysisClassification;
  source_url: string | null;
  information_scope: string;
}

export interface PaperBlueprintEntry {
  content: string;
  classification: AnalysisClassification;
  basis: string;
}

export interface PaperBlueprintSection {
  section: "摘要" | "介绍" | "文献综述" | "方法" | "实验";
  writing_goal: PaperBlueprintEntry;
  evidence_references: PaperBlueprintReference[];
  missing_evidence: PaperBlueprintEntry[];
  forbidden_claims: string[];
  citation_placeholders: PaperBlueprintReference[];
}

export interface PaperBlueprint {
  schema_version: "paper-blueprint.v2";
  conversation_id: string;
  candidate_titles: PaperBlueprintEntry[];
  target_submission_direction: PaperBlueprintEntry;
  abstract_requirements: PaperBlueprintEntry[];
  sections: PaperBlueprintSection[];
  submission_readiness: PaperBlueprintEntry;
  gaps: PaperBlueprintEntry[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface PaperSection { section_id: string; heading: string; content: string; order: number; }
export interface PaperDraft {
  schema_version: "paper-draft.v1"; draft_id: string; conversation_id: string; title: string;
  content: string; format: "markdown" | "plain_text"; version: number; sections: PaperSection[];
  created_at: string; source_scope: "user_pasted_local_session";
}
export type ReviewSeverity = "blocker" | "major" | "minor" | "suggestion";
export interface ReviewFinding {
  id: string; severity: ReviewSeverity; section: string; issue: string; why_it_matters: string;
  recommended_action: string; classification: AnalysisClassification; basis: string;
  source_scope: string; related_blueprint_item: string | null; can_auto_suggest: boolean;
}
export interface RevisionTask { task_id: string; finding_id: string; status: "pending" | "accepted" | "skipped" | "completed"; finding: ReviewFinding; created_at: string; updated_at: string; }
export interface RevisionSuggestion {
  schema_version: "revision-suggestion.v1"; suggestion_id: string; revision_task_id: string; draft_id: string;
  section_heading: string; paragraph_anchor: string; original_excerpt: string; candidate_text: string;
  rationale: string; classification: AnalysisClassification; basis: string; source_scope: string;
  to_verify_items: string[]; generation_mode: "llm" | "rules" | "rules_fallback"; run_id: string | null; created_at: string;
}
export interface PaperReview {
  schema_version: "paper-review.v1"; review_id: string; draft_id: string; conversation_id: string;
  findings: ReviewFinding[]; revision_tasks: RevisionTask[]; provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback"; run_id: string | null; event_count: number; created_at: string;
}
export interface PaperRevision {
  schema_version: "paper-revision.v1"; revision_id: string; parent_draft_id: string; review_id: string;
  parent_revision_id: string | null;
  version: number; content: string; applied_task_ids: string[]; change_summary: string[];
  applied_suggestion_ids: string[];
  diff_preview: string; created_at: string; source_scope: "user_pasted_draft_plus_accepted_suggestions";
}
export type CitationTargetDocument = "paper_draft" | "paper_revision" | "paper_blueprint";
export type SelectedCitationStatus = "selected" | "inserted" | "skipped";
export interface CitationCandidate {
  schema_version: "citation-candidate.v1"; citation_id: string; conversation_id: string;
  evidence_bundle_id: string; paper_title: string; authors: string[]; year: number | null;
  source_name: string | null; url: string; doi: string | null; arxiv_id: string | null;
  abstract_scope: "metadata_only" | "metadata_and_abstract";
  metadata_completeness: "complete" | "partial"; classification: AnalysisClassification;
  source_scope: "metadata_and_abstract_only"; created_at: string;
}
export interface ReferenceEntryDraft {
  reference_id: string; selected_citation_id: string; display_text: string; citation_key: string;
  metadata_fields: Record<string, string | number | null>; classification: AnalysisClassification;
  to_verify_items: string[]; source_scope: "metadata_and_abstract_only";
}
export interface ReferenceDraftItem {
  selected_citation_id: string; source_url: string; citation_placeholder: string;
  display_text: string; classification: AnalysisClassification; to_verify_items: string[];
  format_notice: string;
}
export interface ReferenceDraftVerificationItem {
  selected_citation_id: string; source_url: string; missing_fields: string[];
  classification: "to_verify"; basis: string;
}
export interface ReferenceDraftPackage {
  schema_version: "reference-draft-package.v1"; session_id: string;
  entries: ReferenceDraftItem[]; copy_text: string;
  verification_items: ReferenceDraftVerificationItem[];
  empty_state_message: string | null; boundary_note: string;
  source_scope: "local_selected_evidence_only";
}
export interface SelectedCitation {
  schema_version: "selected-citation.v1"; selected_citation_id: string; session_id: string;
  citation: CitationCandidate; target_document: CitationTargetDocument; target_section: string;
  paragraph_anchor: string; citation_placeholder: string; user_note: string | null;
  status: SelectedCitationStatus; reference_entry: ReferenceEntryDraft; created_at: string;
}
export type CitationQualityStatus = "empty" | "needs_review" | "review_ready";
export interface CitationQualityIssue {
  issue_code: string; message: string; selected_citation_ids: string[];
  classification: AnalysisClassification; basis: string;
}
export interface CitationCoverageItem {
  target_document: CitationTargetDocument; target_section: string;
  selected_citation_ids: string[]; source_titles: string[]; citation_placeholders: string[];
  status: "mapped" | "needs_verification"; classification: "inference";
  information_scopes: ("metadata_only" | "metadata_and_abstract")[];
  basis: string; to_verify_items: string[];
}
export interface CitationQualityCheck {
  schema_version: "citation-quality-check.v1"; check_id: string; session_id: string;
  checked_at: string; quality_status: CitationQualityStatus; selected_source_count: number;
  unique_source_count: number; mapped_section_count: number;
  core_section_coverage_percent: number; coverage_items: CitationCoverageItem[];
  unmapped_core_sections: string[]; uninserted_placeholders: CitationQualityIssue[];
  duplicate_selections: CitationQualityIssue[]; metadata_gaps: CitationQualityIssue[];
  author_verification_items: CitationQualityIssue[]; empty_state_message: string | null;
  boundary_note: string; source_scope: "local_selected_evidence_only";
}
export interface SubmissionProfileInput {
  target_venue?: string | null;
  anonymity_required?: boolean | null;
  length_or_section_requirements?: string | null;
  ethics_and_data_requirements?: string | null;
  user_notes?: string | null;
}
export interface SubmissionProfile extends SubmissionProfileInput {
  schema_version: "submission-profile.v1"; profile_id: string; conversation_id: string;
  created_at: string; updated_at: string;
}
export type SubmissionReadinessStatus = "not_ready" | "needs_review" | "checklist_complete";
export interface SubmissionReadinessItem {
  id: string; category: string; message: string; classification: AnalysisClassification;
  basis: string; source_scope: string;
}
export interface SubmissionReadinessCheck {
  schema_version: "submission-readiness.v1"; check_id: string; draft_id: string;
  revision_id: string | null; conversation_id: string; submission_profile: SubmissionProfile | null;
  readiness_status: SubmissionReadinessStatus;
  blockers: SubmissionReadinessItem[]; warnings: SubmissionReadinessItem[];
  manual_checks: SubmissionReadinessItem[]; fact_boundary_notes: SubmissionReadinessItem[];
  recommended_next_actions: SubmissionReadinessItem[]; created_at: string;
  source_scope: "local_saved_research_artifacts";
}
export interface PaperExportFile {
  filename: string; content_type: "text/markdown" | "application/json"; content: string;
}
export interface PaperExportPackage {
  schema_version: "paper-export.v1"; draft_id: string; revision_id: string;
  readiness_check_id: string; files: PaperExportFile[]; provenance_note: string;
}

export interface SavedResearchNotebookNote {
  schema_version: "research-notebook-note.v1";
  notebook_item_id: string;
  learning_session_id: string;
  conversation_id: string;
  bundle_id: string;
  research_topic: string;
  research_question: string;
  evidence_refs: EvidenceReference[];
  next_steps: string[];
}

export class ResearchApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly stage?: string,
    public readonly missing?: string[],
  ) {
    super(message);
    this.name = "ResearchApiError";
  }

  /** True when key reproduction conditions are absent (HTTP 409 gate). */
  get isConditionsMissing(): boolean {
    return this.status === 409 && (this.missing?.length ?? 0) > 0;
  }

  /** True when the model failed to generate advice; the UI should offer a retry. */
  get isGenerationFailure(): boolean {
    return this.status === 503 || this.stage !== undefined;
  }
}

const API_BASE = (
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const REQUEST_TIMEOUT_MS = 10_000;
const MODEL_TURN_TIMEOUT_MS = 25_000;
// Paper analysis and mind-map generation can take longer than a chat turn while
// the backend validates structured LLM output. Keep the browser from aborting
// a request before the backend's generation window has elapsed.
const PAPER_ARTIFACT_TIMEOUT_MS = 120_000;

export async function createResearchConversation(
  initialMessage?: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>("/api/v1/research/conversations", {
    method: "POST",
    body: JSON.stringify({ initial_message: initialMessage || null }),
  });
  return validateConversationResponse(data);
}

export async function getResearchConversation(
  conversationId: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}`,
  );
  return validateConversationResponse(data);
}

export async function sendResearchMessage(
  conversationId: string,
  message: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/messages`,
    { method: "POST", body: JSON.stringify({ message }) },
    MODEL_TURN_TIMEOUT_MS,
  );
  return validateConversationResponse(data);
}

export async function retryResearchReply(
  conversationId: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/messages/retry-last`,
    { method: "POST" },
    MODEL_TURN_TIMEOUT_MS,
  );
  return validateConversationResponse(data);
}

export async function saveReproductionConditions(
  conversationId: string,
  conditions: ReproductionConditionsInput,
): Promise<ResearchConversationResponse> {
  return request<ResearchConversationResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reproduction-conditions`,
    { method: "PUT", body: JSON.stringify(conditions) },
  );
}

export async function saveReadingReport(
  conversationId: string,
  input: { paper_url: string; title: string; content: string },
): Promise<ReadingReport[]> {
  return request<ReadingReport[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reading-reports`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function listReadingReports(
  conversationId: string,
): Promise<ReadingReport[]> {
  return request<ReadingReport[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reading-reports`,
  );
}

export async function getResearchProviderStatus(): Promise<ProviderStatusResponse> {
  return request<ProviderStatusResponse>("/api/v1/research/provider/status");
}

export async function testResearchProvider(): Promise<ProviderConnectionTestResponse> {
  return request<ProviderConnectionTestResponse>("/api/v1/research/provider/test", {
    method: "POST",
  }, 20_000);
}

export async function configureResearchProvider(
  configuration: ConfigureProviderRequest,
): Promise<ProviderStatusResponse> {
  return request<ProviderStatusResponse>("/api/v1/research/provider/configuration", {
    method: "PUT",
    body: JSON.stringify(configuration),
  });
}

export async function getResearchSearchPlan(
  conversationId: string,
): Promise<ResearchSearchPlan> {
  return request<ResearchSearchPlan>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/search-plan`,
  );
}

export async function searchResearchEvidence(
  conversationId: string,
  query: string,
  sources: AcademicSourceId[],
): Promise<ConversationEvidenceBundle> {
  return request<ConversationEvidenceBundle>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/evidence-bundles`,
    {
      method: "POST",
      body: JSON.stringify({ query, sources }),
    },
    25_000,
  );
}

export async function listResearchEvidence(
  conversationId: string,
): Promise<ConversationEvidenceBundle[]> {
  return request<ConversationEvidenceBundle[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/evidence-bundles`,
  );
}

export async function saveResearchNotebookNote(
  conversationId: string,
  bundleId: string,
  learningSessionId: string,
  selectedPaperUrls: string[],
): Promise<SavedResearchNotebookNote> {
  return request<SavedResearchNotebookNote>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/evidence-bundles/${encodeURIComponent(bundleId)}/notebook-notes`,
    {
      method: "POST",
      body: JSON.stringify({
        learning_session_id: learningSessionId,
        selected_paper_urls: selectedPaperUrls,
      }),
    },
  );
}

export async function analyzeResearchPaper(
  conversationId: string,
  paperUrl: string,
  paperPdfUrl?: string,
): Promise<PaperAnalysis> {
  return request<PaperAnalysis>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-analysis`,
    { method: "POST", body: JSON.stringify({ paper_url: paperUrl, paper_pdf_url: paperPdfUrl || null }) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function analyzeResearchPaperUpload(
  conversationId: string,
  paperUrl: string,
  file: File,
): Promise<PaperAnalysis> {
  return request<PaperAnalysis>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-analysis/upload?paper_url=${encodeURIComponent(paperUrl)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/pdf", "X-Filename": file.name },
      body: file,
    },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function createUnderstandingQuestion(
  conversationId: string,
  payload: { paper_url: string; bundle_id: string; section_key: string },
): Promise<UnderstandingCheck> {
  return request<UnderstandingCheck>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/understanding-checks/question`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function assessUnderstandingAnswer(
  conversationId: string,
  payload: {
    check_id: string;
    paper_url: string;
    bundle_id: string;
    section_key: string;
    answer: string;
  },
): Promise<UnderstandingCheck> {
  return request<UnderstandingCheck>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/understanding-checks/assess`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listUnderstandingChecks(
  conversationId: string,
  paperUrl: string,
): Promise<UnderstandingCheck[]> {
  const query = new URLSearchParams({ paper_url: paperUrl });
  return request<UnderstandingCheck[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/understanding-checks?${query.toString()}`,
  );
}

export async function generateTopicDifficultyAnalysis(
  conversationId: string,
): Promise<TopicDifficultyAnalysis> {
  return request<TopicDifficultyAnalysis>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/topic-difficulty-analysis`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function generateResearchPlan(
  conversationId: string,
): Promise<ConversationResearchPlan> {
  return request<ConversationResearchPlan>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/research-plan`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
    MODEL_TURN_TIMEOUT_MS,
  );
}

export async function generateResearchMindMap(
  conversationId: string,
): Promise<ResearchMindMap> {
  return request<ResearchMindMap>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/research-mindmap`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function generateExperimentDesign(
  conversationId: string,
  taskTypeOverride?: TaskType | null,
): Promise<ExperimentDesign> {
  const body: GenerateExperimentDesignRequest = { user_confirmed: true };
  if (taskTypeOverride) {
    body.task_type_override = taskTypeOverride;
  }
  return request<ExperimentDesign>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-design`,
    { method: "POST", body: JSON.stringify(body) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function createExperimentCodeDraft(
  conversationId: string,
): Promise<ExperimentCodeDraft> {
  return request<ExperimentCodeDraft>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-code-draft`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function createExperimentEvidenceBundle(
  conversationId: string,
  payload: CreateExperimentEvidenceBundleRequest,
): Promise<ExperimentEvidenceBundle> {
  return request<ExperimentEvidenceBundle>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-evidence-bundles`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listExperimentEvidenceBundles(
  conversationId: string,
): Promise<ExperimentEvidenceBundle[]> {
  return request<ExperimentEvidenceBundle[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-evidence-bundles`,
  );
}

export async function createReproductionEvaluation(
  conversationId: string,
): Promise<ReproductionProjectEvaluation> {
  return request<ReproductionProjectEvaluation>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reproduction-evaluations`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function listReproductionEvaluations(
  conversationId: string,
): Promise<ReproductionProjectEvaluation[]> {
  return request<ReproductionProjectEvaluation[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reproduction-evaluations`,
  );
}

export async function updateReproductionImprovementTask(
  taskId: string,
  status: "accepted" | "skipped" | "completed",
): Promise<ReproductionImprovementTask> {
  return request<ReproductionImprovementTask>(
    `/api/v1/research/reproduction-improvement-tasks/${encodeURIComponent(taskId)}`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );
}

export async function createReproductionPipeline(
  conversationId: string,
  payload: { evidence_bundle_id: string; paper_url: string; paper_pdf_url?: string | null },
): Promise<ReproductionPipeline> {
  return request<ReproductionPipeline>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reproduction-pipelines`,
    { method: "POST", body: JSON.stringify(payload) },
    PAPER_ARTIFACT_TIMEOUT_MS,
  );
}

export async function listReproductionPipelines(conversationId: string): Promise<ReproductionPipeline[]> {
  return request<ReproductionPipeline[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reproduction-pipelines`,
  );
}

export async function generatePaperBlueprint(conversationId: string): Promise<PaperBlueprint> {
  return request<PaperBlueprint>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-blueprint`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function createPaperDraft(conversationId: string, payload: { title: string; content: string; format: "markdown" | "plain_text" }): Promise<PaperDraft> {
  return request<PaperDraft>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-drafts`, { method: "POST", body: JSON.stringify(payload) });
}
export async function listPaperDrafts(conversationId: string): Promise<PaperDraft[]> {
  return request<PaperDraft[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-drafts`);
}
export async function createPaperReview(draftId: string): Promise<PaperReview> {
  return request<PaperReview>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/reviews`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) }, MODEL_TURN_TIMEOUT_MS);
}
export async function listPaperReviews(draftId: string): Promise<PaperReview[]> {
  return request<PaperReview[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/reviews`);
}
export async function updatePaperRevisionTask(reviewId: string, taskId: string, status: "accepted" | "skipped"): Promise<PaperReview> {
  return request<PaperReview>(`/api/v1/research/paper-reviews/${encodeURIComponent(reviewId)}/revision-tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", body: JSON.stringify({ status }) });
}
export async function createRevisionSuggestion(reviewId: string, taskId: string): Promise<RevisionSuggestion> {
  return request<RevisionSuggestion>(`/api/v1/research/paper-reviews/${encodeURIComponent(reviewId)}/revision-tasks/${encodeURIComponent(taskId)}/suggestions`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) }, MODEL_TURN_TIMEOUT_MS);
}
export async function listRevisionSuggestions(reviewId: string, taskId: string): Promise<RevisionSuggestion[]> {
  return request<RevisionSuggestion[]>(`/api/v1/research/paper-reviews/${encodeURIComponent(reviewId)}/revision-tasks/${encodeURIComponent(taskId)}/suggestions`);
}
export async function applyRevisionSuggestion(suggestionId: string, action: "accepted" | "skipped", candidateText?: string): Promise<PaperRevision | null> {
  return request<PaperRevision | null>(`/api/v1/research/revision-suggestions/${encodeURIComponent(suggestionId)}/apply`, { method: "POST", body: JSON.stringify({ action, candidate_text: candidateText || null }) });
}
export async function listPaperRevisions(draftId: string): Promise<PaperRevision[]> {
  return request<PaperRevision[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/revisions`);
}
export async function listCitationCandidates(conversationId: string): Promise<CitationCandidate[]> {
  return request<CitationCandidate[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/citation-candidates`);
}
export async function createSelectedCitation(conversationId: string, payload: {
  evidence_bundle_id: string; paper_url: string; target_document: CitationTargetDocument;
  target_section: string; paragraph_anchor: string; user_note?: string | null;
}): Promise<SelectedCitation> {
  return request<SelectedCitation>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/selected-citations`, { method: "POST", body: JSON.stringify(payload) });
}
export async function listSelectedCitations(conversationId: string): Promise<SelectedCitation[]> {
  return request<SelectedCitation[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/selected-citations`);
}
export async function updateSelectedCitation(selectedCitationId: string, status: "inserted" | "skipped"): Promise<SelectedCitation> {
  return request<SelectedCitation>(`/api/v1/research/selected-citations/${encodeURIComponent(selectedCitationId)}`, { method: "PATCH", body: JSON.stringify({ status }) });
}
export async function listReferenceEntryDrafts(conversationId: string): Promise<ReferenceEntryDraft[]> {
  return request<ReferenceEntryDraft[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reference-entry-drafts`);
}
export async function getReferenceDraftPackage(conversationId: string): Promise<ReferenceDraftPackage> {
  return request<ReferenceDraftPackage>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/reference-draft-package`);
}
export async function createCitationQualityCheck(conversationId: string): Promise<CitationQualityCheck> {
  return request<CitationQualityCheck>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/citation-quality-checks`, { method: "POST" });
}
export async function listCitationQualityChecks(conversationId: string): Promise<CitationQualityCheck[]> {
  return request<CitationQualityCheck[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/citation-quality-checks`);
}
export async function getSubmissionProfile(conversationId: string): Promise<SubmissionProfile | null> {
  return request<SubmissionProfile | null>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/submission-profile`);
}
export async function saveSubmissionProfile(conversationId: string, payload: SubmissionProfileInput): Promise<SubmissionProfile> {
  return request<SubmissionProfile>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/submission-profile`, { method: "PUT", body: JSON.stringify(payload) });
}
export async function createSubmissionReadiness(draftId: string): Promise<SubmissionReadinessCheck> {
  return request<SubmissionReadinessCheck>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/submission-readiness`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) });
}
export async function listSubmissionReadiness(draftId: string): Promise<SubmissionReadinessCheck[]> {
  return request<SubmissionReadinessCheck[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/submission-readiness`);
}
export async function createPaperExportPackage(draftId: string): Promise<PaperExportPackage> {
  return request<PaperExportPackage>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/export-package`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) });
}

export interface StageBriefingKnowledgePoint {
  name: string;
  mastery: number | null;
}

export interface StageBriefingSummary {
  topic: string | null;
  digest: string | null;
  knowledge_points: StageBriefingKnowledgePoint[] | null;
}

export interface StageBriefingReproductionEntry {
  bundle_count: number;
  pipeline_status: string | null;
}

export interface StageBriefingEvidenceTrend {
  keyword: string;
  paper_count: number;
  evidence_refs: EvidenceReference[];
}

export interface StageBriefingResponse {
  conversation_id: string;
  has_learning_context: boolean;
  stage_summary: StageBriefingSummary;
  reproduction_entry: StageBriefingReproductionEntry;
  evidence_trends: StageBriefingEvidenceTrend[];
  generated_by: "rules";
  generated_at: string;
}

export interface StudyRecommendationAction {
  type: "learning_explain" | "practice_set";
  payload: Record<string, unknown>;
}

export interface StudyRecommendation {
  knowledge_point: string;
  reason: string;
  mastery_status: "mastered" | "weak" | "unknown";
  action: StudyRecommendationAction;
}

export interface StudyRecommendationsResponse {
  recommendations: StudyRecommendation[];
  provenance_note: string;
}

export async function fetchStageBriefing(
  conversationId: string,
  includeEvidenceTrends: boolean = false,
): Promise<StageBriefingResponse> {
  const query = includeEvidenceTrends ? "?include_evidence_trends=true" : "";
  return request<StageBriefingResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/stage-briefing${query}`,
  );
}

export async function fetchStudyRecommendations(
  conversationId: string,
  userConfirmed: boolean = true,
): Promise<StudyRecommendationsResponse> {
  return request<StudyRecommendationsResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/study-recommendations`,
    {
      method: "POST",
      body: JSON.stringify({ user_confirmed: userConfirmed }),
    },
  );
}

// Four-stage state machine orchestrator types
export type OrchestratorStage =
  | "research_need"
  | "research_plan"
  | "research_execution"
  | "research_analysis";

export const STAGE_DISPLAY_NAMES: Record<OrchestratorStage, string> = {
  research_need: "研究需求确定",
  research_plan: "研究计划生成",
  research_execution: "研究开展",
  research_analysis: "研究结果分析",
};

export const STAGE_SEQUENCE: OrchestratorStage[] = [
  "research_need",
  "research_plan",
  "research_execution",
  "research_analysis",
];

export type PaperUsage = "replace" | "compare" | "cite";

export interface OrchestratorSubtasks {
  need_defined: boolean;
  profile_ready: boolean;
  plan_generated: boolean;
  paper_selected: boolean;
  experiment_designed: boolean;
  results_analyzed: boolean;
}

export interface DirectionHistoryEntry {
  direction: string;
  timestamp: string;
}

export interface DirectionCard {
  id: string;
  title: string;
  description: string;
  prerequisite_gap: string | null;
  is_recommended: boolean;
}

export interface DirectionCardsResponse {
  conversation_id: string;
  learned_content: string | null;
  learning_progress: string | null;
  cards: DirectionCard[];
}

export interface OrchestratorStateResponse {
  conversation_id: string;
  current_stage: OrchestratorStage;
  completed_stages: OrchestratorStage[];
  subtasks: OrchestratorSubtasks;
  direction_history: DirectionHistoryEntry[];
  last_status: "thinking" | "completed" | "failed";
  last_error: string | null;
}

export interface OrchestratorMessageReply {
  id: string;
  sender: "assistant";
  content: string;
  created_at: string;
  passive_tool_called: string | null;
}

export interface OrchestratorMessageResponse {
  conversation_id: string;
  status: "completed" | "failed";
  reply_message: OrchestratorMessageReply | null;
  state: OrchestratorStateResponse;
  error: string | null;
}

export interface OrchestratorPaper {
  id: string;
  paper_url: string;
  title: string;
  purpose: PaperUsage;
  is_current: boolean;
  metadata_snapshot: Record<string, unknown>;
  selected_at: string;
}

export interface CurrentPaperCard {
  id: string;
  paper_url: string;
  title: string;
  purpose: PaperUsage;
  metadata_snapshot: Record<string, unknown>;
  selected_at: string;
}

export interface OrchestratorPapersResponse {
  conversation_id: string;
  current_paper: CurrentPaperCard | null;
  paper_history: OrchestratorPaper[];
}

export interface SelectPaperRequest {
  paper_url: string;
  title: string;
  purpose?: PaperUsage;
  metadata?: Record<string, unknown>;
}

export interface LearnerProfileData {
  domain_familiarity?: string | null;
  dev_experience?: string | null;
  projects?: string | null;
  hardware?: string | null;
  os?: string | null;
  python_env?: string | null;
  weekly_hours?: string | null;
  grade?: string | null;
  major?: string | null;
}

export interface LearnerProfileVersion {
  version: number;
  profile_data: LearnerProfileData;
  change_summary: string | null;
  created_at: string;
  is_current: boolean;
}

export interface LearnerProfileResponse {
  conversation_id: string;
  current_profile: LearnerProfileData | null;
  current_version: number | null;
  history: LearnerProfileVersion[];
}

export interface LearningContextState {
  conversation_id: string;
  learned_content: string | null;
  learning_progress: string | null;
  updated_at: string | null;
}

export async function getOrchestratorState(
  conversationId: string,
): Promise<OrchestratorStateResponse> {
  return request<OrchestratorStateResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/state`,
  );
}

export async function getOrchestratorDirectionCards(
  conversationId: string,
): Promise<DirectionCardsResponse> {
  return request<DirectionCardsResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/direction-cards`,
  );
}

export async function getOrchestratorPapers(
  conversationId: string,
): Promise<OrchestratorPapersResponse> {
  return request<OrchestratorPapersResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/papers`,
  );
}

export async function selectOrchestratorPaper(
  conversationId: string,
  payload: SelectPaperRequest,
): Promise<OrchestratorPapersResponse> {
  return request<OrchestratorPapersResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/papers/select`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function getOrchestratorLearnerProfiles(
  conversationId: string,
): Promise<LearnerProfileResponse> {
  return request<LearnerProfileResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/learner-profiles`,
  );
}

export async function updateOrchestratorLearnerProfile(
  conversationId: string,
  payload: Partial<LearnerProfileData> & { change_summary?: string },
): Promise<LearnerProfileResponse> {
  return request<LearnerProfileResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/learner-profiles`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function getOrchestratorLearningContext(
  conversationId: string,
): Promise<LearningContextState> {
  return request<LearningContextState>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/learning-context`,
  );
}

export async function updateOrchestratorLearningContext(
  conversationId: string,
  payload: { learned_content?: string | null; learning_progress?: string | null },
): Promise<LearningContextState> {
  return request<LearningContextState>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/learning-context`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function sendOrchestratorMessage(
  conversationId: string,
  message: string,
): Promise<OrchestratorMessageResponse> {
  return request<OrchestratorMessageResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/messages`,
    {
      method: "POST",
      body: JSON.stringify({ message }),
    },
    MODEL_TURN_TIMEOUT_MS,
  );
}

export async function retryLastOrchestratorMessage(
  conversationId: string,
): Promise<OrchestratorMessageResponse> {
  return request<OrchestratorMessageResponse>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/messages/retry-last`,
    {
      method: "POST",
    },
    MODEL_TURN_TIMEOUT_MS,
  );
}

export async function streamOrchestratorMessage(
  conversationId: string,
  message: string,
  callbacks: {
    onThinking?: (data: { status: string; stage: string; message: string }) => void;
    onCompleted?: (response: OrchestratorMessageResponse) => void;
    onFailed?: (response: OrchestratorMessageResponse) => void;
    onError?: (error: Error) => void;
  },
): Promise<void> {
  const url = `${API_BASE}/api/v1/research/conversations/${encodeURIComponent(conversationId)}/orchestrator/messages/stream`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const csrf = getStoredCsrfToken();
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  const response = await fetch(url, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    const info = await errorInfo(response);
    throw new ResearchApiError(
      response.status,
      info.message ?? `科研服务流式请求失败（HTTP ${response.status}）。`,
    );
  }
  if (!response.body) {
    throw new ResearchApiError(502, "科研服务未返回流式响应体。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split("\n");
        let eventType = "message";
        let dataStr = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice("event:".length).trim();
          } else if (line.startsWith("data:")) {
            dataStr = line.slice("data:".length).trim();
          }
        }
        if (!dataStr) continue;
        try {
          const parsed = JSON.parse(dataStr);
          if (eventType === "thinking") {
            callbacks.onThinking?.(parsed);
          } else if (eventType === "completed") {
            callbacks.onCompleted?.(parsed as OrchestratorMessageResponse);
          } else if (eventType === "failed") {
            callbacks.onFailed?.(parsed as OrchestratorMessageResponse);
          }
        } catch (parseError) {
          console.error("SSE parse error", parseError, dataStr);
        }
      }
    }
  } catch (streamError) {
    if (streamError instanceof Error) {
      callbacks.onError?.(streamError);
    }
    throw streamError;
  }
}

function validateConversationResponse(data: unknown): ResearchConversationResponse {
  if (!data || typeof data !== "object") {
    throw new ResearchApiError(502, "科研服务返回了无法识别的数据。请刷新后重试。");
  }
  const candidate = data as Record<string, unknown>;
  if (candidate.schema_version !== RESEARCH_CONVERSATION_SCHEMA) {
    throw new ResearchApiError(
      502,
      `科研服务版本不兼容：需要 ${RESEARCH_CONVERSATION_SCHEMA}。`,
    );
  }
  if (
    typeof candidate.conversation_id !== "string" ||
    !candidate.profile ||
    typeof candidate.profile !== "object" ||
    !Array.isArray(candidate.messages)
  ) {
    throw new ResearchApiError(502, "科研服务响应缺少会话、画像或消息数据。");
  }
  return data as ResearchConversationResponse;
}

import { getStoredCsrfToken } from "@/lib/api/auth";

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const csrf = getStoredCsrfToken();
  if (csrf && init?.method && ["POST", "PUT", "PATCH", "DELETE"].includes(init.method.toUpperCase())) {
    headers["X-CSRF-Token"] = csrf;
  }

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      signal: controller.signal,
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ResearchApiError(
        0,
        `科研服务在 ${timeoutMs / 1000} 秒内没有响应。请确认后端已启动后重试。`,
      );
    }
    const reason = error instanceof Error ? error.message : String(error);
    throw new ResearchApiError(
      0,
      `无法连接科研服务（${API_BASE}）。请确认后端已启动。${reason ? ` ${reason}` : ""}`,
    );
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    const info = await errorInfo(response);
    throw new ResearchApiError(
      response.status,
      info.message ?? `科研服务请求失败（HTTP ${response.status}）。`,
      info.stage,
      info.missing,
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ResearchApiError(502, "科研服务没有返回有效 JSON。");
  }
}

interface ErrorInfo {
  message: string | null;
  stage?: string;
  missing?: string[];
}

async function errorInfo(response: Response): Promise<ErrorInfo> {
  try {
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("detail" in body)) {
      return { message: null };
    }
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return { message: detail };
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const info = detail as { message?: unknown; stage?: unknown; missing?: unknown };
      return {
        message: typeof info.message === "string" ? info.message : null,
        stage: typeof info.stage === "string" ? info.stage : undefined,
        missing: Array.isArray(info.missing)
          ? info.missing.filter((item): item is string => typeof item === "string")
          : undefined,
      };
    }
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const validation = item as { loc?: unknown; msg?: unknown };
        if (typeof validation.msg !== "string") return [];
        const location = Array.isArray(validation.loc)
          ? validation.loc.slice(1).join(" → ")
          : "请求内容";
        return [`${location || "请求内容"}：${validation.msg}`];
      });
      return { message: messages.length ? messages.join("；") : null };
    }
  } catch {
    // A proxy may return HTML or an empty body. Keep the status fallback.
  }
  return { message: response.statusText || null };
}
