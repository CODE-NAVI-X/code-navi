/**
 * 「进入结果分析」的阶段门控（纯逻辑，零依赖）。
 *
 * 真实浏览器事实（2026-09-11，研究开展阶段）：
 *
 * 用户确认四组检索词后后端并没有真正检索，页面上**没有任何候选论文**，
 * 但「进入结果分析」按钮依然可点——它只看 `currentStage === "research_execution"`，
 * 既不看 evidence bundle，也不看候选论文，更不看用户是否确认过当前论文。
 * 点下去还会隐式发起一次检索，拉回 4 篇与主题完全无关的中文论文。
 *
 * 于是「能不能进入结果分析」收敛成三个条件的合取：
 *
 * 1. 当前会话最新一次真实检索**有**候选论文（空结果也算“没有” → 阻塞）；
 * 2. 用户已经**确认**了当前论文（只有候选、没有确认 → 阻塞）；
 * 3. 其余阶段行为完全不变。
 *
 * 这里刻意只做判定、不产生任何副作用：点击哪也不去，不触发检索。
 */

/** 门控输入。 */
export interface AnalysisGateInput {
  /** 当前会话最新一次真实检索留下的候选论文数量。 */
  candidateCount: number;
  /** 用户是否已确认当前论文（orchestrator 的 `current_paper`）。 */
  hasConfirmedPaper: boolean;
}

/** 没有真实检索候选时的阻塞原因。 */
export const ANALYSIS_BLOCK_NO_CANDIDATES =
  "还没有真实检索到的候选论文：请先确认检索词并完成一次正式检索，再进入结果分析。";

/** 有候选但尚未确认当前论文时的阻塞原因。 */
export const ANALYSIS_BLOCK_NO_CONFIRMED_PAPER =
  "还没有你确认的当前论文：请先在候选论文卡片中确认一篇，再进入结果分析。";

/**
 * 返回阻塞原因；`null` 表示允许进入结果分析。
 *
 * 不抛错、不修改输入，便于在单元测试里直接覆盖各组合。
 */
export function describeAnalysisBlocker(input: AnalysisGateInput): string | null {
  const count = Number.isFinite(input?.candidateCount) ? input.candidateCount : 0;
  if (count <= 0) return ANALYSIS_BLOCK_NO_CANDIDATES;
  if (!input?.hasConfirmedPaper) return ANALYSIS_BLOCK_NO_CONFIRMED_PAPER;
  return null;
}
