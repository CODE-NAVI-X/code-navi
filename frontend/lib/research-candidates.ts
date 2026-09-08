/**
 * 科研对话“候选论文卡片”的会话归属与加载（纯逻辑）。
 *
 * 背景（两轮）：
 * 1. 点击“新建对话”后，页面清空了会话、编排器状态、方向卡、已选论文与草稿，
 *    却没有清空候选论文列表，也没有按新的 conversation_id 重新读取 evidence bundles。
 *    结果是新会话一打开就显示上一个会话的候选论文，看起来像“新会话自动检索过”。
 * 2. 一次明确返回空结果的检索之后，页面仍显示上一轮检索留下的无关论文——
 *    因为“最新候选”是按「最后一个带论文的 bundle」算的，等于跳过空结果去找更早的一轮。
 *
 * 后端按 conversation_id 隔离本身是正确的，需要四件事：
 * 1. 切换会话时立即清空候选；
 * 2. 候选按当前会话 id 重新读取；
 * 3. 旧会话的迟到响应（成功或失败）不得覆盖新会话的结果——归属校验；
 * 4. 候选**只以最新一次检索为准**：最新 bundle 为空就是没有候选，绝不回退。
 *
 * 本模块刻意不依赖任何运行时模块，便于用 node --test 直接覆盖这些时序场景。
 */

/** 候选卡片最多展示的论文数量（沿用既有行为，本轮不改变）。 */
export const MAX_CANDIDATE_PAPERS = 5;

/** evidence bundle 里候选卡片真正用到的部分。 */
export interface CandidateBundleLike<T> {
  papers: readonly T[];
}

/**
 * 「最新 evidence bundle」的定义。
 *
 * 已核对后端源码（两处读取路径完全一致）：
 *
 * - `GET /api/v1/research/conversations/{id}/evidence-bundles`
 *   → `ConversationSearchService.list_bundles`
 *   → `.order_by(ResearchEvidenceBundleModel.created_at.desc())`
 * - 会话恢复路径 `ConversationService._evidence_bundles`
 *   → 同样 `created_at.desc()`
 *
 * 也就是说接口**按时间倒序**返回：**数组下标 0 就是最新一次检索的 bundle**，
 * 数组末尾才是最旧的。`tests/test_research_frontend_copy.py` 里有一个用例
 * 专门锁死这个契约，后端若改成升序会立刻失败，而不是静默地让这里读错。
 */
const NEWEST_BUNDLE_INDEX = 0;

/**
 * 取当前会话最新一次检索的候选论文。
 *
 * 严格语义（每条都有对应用例）：
 * 1. 有最新 bundle 就以它为准；
 * 2. 最新 bundle 的 papers 为空 → 返回 `[]`；
 * 3. **不跳过空 bundle**去更早的 bundle 里找论文——那会把上一轮检索的无关论文
 *    在空结果之后重新贴回页面；
 * 4. 完全没有 bundle 时才返回 `[]`；
 * 5. 有论文时保持后端返回的原始顺序，最多 `MAX_CANDIDATE_PAPERS` 篇。
 *
 * 只读取最新 bundle 的 `papers`：不重排、不按来源过滤、不改写来源状态与 provenance。
 */
export function pickLatestCandidatePapers<T>(
  bundles: readonly CandidateBundleLike<T>[],
  limit: number = MAX_CANDIDATE_PAPERS,
): T[] {
  const newest = (bundles ?? [])[NEWEST_BUNDLE_INDEX];
  if (!newest || !Array.isArray(newest.papers)) return [];
  return newest.papers.slice(0, limit);
}

const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const ASCII_WORD_PATTERN = /[A-Za-z]{2,}/;

/**
 * 保守判断候选题名是否为英文。
 *
 * 这里只看标题本身：没有英文词、标题为空、或包含中文字符时都过滤；
 * 不根据来源名称推断语言，也不翻译或改写题名。
 */
export function isEnglishCandidateTitle(title: unknown): boolean {
  const text = typeof title === "string" ? title.trim() : "";
  if (!text) return false;
  return !CJK_PATTERN.test(text) && ASCII_WORD_PATTERN.test(text);
}

export function isDisplayableEnglishTitle(title: string | null | undefined): boolean {
  return isEnglishCandidateTitle(title);
}

/**
 * 过滤面向用户展示的候选论文，不改变条目字段或原数组顺序。
 *
 * 后端新检索已经执行同一规则；这里作为历史 evidence bundle 的展示边界，
 * 防止旧会话中遗留的中文题录重新出现在候选卡片上。
 */
export function filterEnglishCandidatePapers<T>(papers: readonly T[] | null | undefined): T[] {
  return (papers ?? []).filter((paper) => {
    const title =
      typeof paper === "object" && paper !== null && "title" in paper
        ? (paper as { title?: unknown }).title
        : undefined;
    return isEnglishCandidateTitle(title);
  });
}

export function filterDisplayableEnglishCandidates<T extends { title?: string | null }>(
  candidates: T[],
): T[] {
  return candidates.filter((candidate) => isDisplayableEnglishTitle(candidate.title));
}

/** 一次候选读取的归属票据。 */
export interface CandidateTicket {
  conversationId: string;
  sequence: number;
}

/** 候选列表的会话归属守卫：保证只有当前会话的最新一次读取能落到页面上。 */
export interface CandidateScope {
  /** 切换到指定会话（`null` 表示“正在新建会话”）；所有在途请求随即作废。 */
  switchTo(conversationId: string | null): void;
  /** 登记一次候选读取（发起请求前调用），返回本次请求的票据。 */
  beginRequest(conversationId: string): CandidateTicket;
  /** 该票据的响应是否仍然属于当前会话，且仍是最新一次请求。 */
  accepts(ticket: CandidateTicket): boolean;
}

/**
 * 创建一个候选归属守卫。
 *
 * 用一个单调递增的序号同时表达“切换了会话”和“发起了更新的请求”：
 * 只要序号不再匹配，响应就被判定为过期，调用方必须丢弃它。
 */
export function createCandidateScope(): CandidateScope {
  let conversationId: string | null = null;
  let sequence = 0;

  return {
    switchTo(next) {
      conversationId = next;
      // 序号自增让所有在途请求立即作废，旧响应回来时会被丢弃。
      sequence += 1;
    },
    beginRequest(target) {
      sequence += 1;
      conversationId = target;
      return { conversationId: target, sequence };
    },
    accepts(ticket) {
      return (
        conversationId !== null &&
        ticket.conversationId === conversationId &&
        ticket.sequence === sequence
      );
    },
  };
}

export interface CandidateLoadOptions<T> {
  /** 候选归属守卫。 */
  scope: CandidateScope;
  /** 读取指定会话的 evidence bundles（通常是 `listResearchEvidence`）。 */
  fetchBundles: (conversationId: string) => Promise<readonly CandidateBundleLike<T>[]>;
  /** 只有归属校验通过时才会被调用，拿到的是当前会话的候选（可能为空数组）。 */
  apply: (papers: T[]) => void;
}

/**
 * 按指定会话读取候选论文。
 *
 * 读取失败按“当前会话没有候选”处理；但**失败同样要走归属校验**，
 * 否则旧会话的失败响应会把新会话刚读到的候选清空。
 *
 * @returns 本次结果是否被采纳；`false` 表示请求已过期，页面不应发生任何变化。
 */
export async function loadSearchCandidates<T>(
  conversationId: string,
  options: CandidateLoadOptions<T>,
): Promise<boolean> {
  const ticket = options.scope.beginRequest(conversationId);
  let papers: T[] = [];
  try {
    const bundles = await options.fetchBundles(conversationId);
    papers = pickLatestCandidatePapers(bundles);
  } catch {
    papers = [];
  }
  if (!options.scope.accepts(ticket)) return false;
  options.apply(papers);
  return true;
}

export interface HasCurrentPaper {
  current_paper?: unknown | null;
  paper_history?: unknown[] | null;
}

/**
 * Candidate cards are hidden once a paper is selected so that a later bundle
 * response cannot suggest switching away from the user's current choice.
 */
export function shouldShowSearchCandidates<T extends { title?: string | null }>(
  candidates: T[] | null | undefined,
  papers: HasCurrentPaper | null | undefined,
): boolean {
  if (!Array.isArray(candidates) || candidates.length === 0 || papers?.current_paper) {
    return false;
  }
  return filterEnglishCandidatePapers(candidates).length > 0;
}

/** Do not refresh cards after a paper has been selected. */
export function shouldRefreshSearchCandidates(
  papers: HasCurrentPaper | null | undefined,
): boolean {
  return !papers?.current_paper;
}

/** A selected paper clears the effective candidate list. */
export function resolveEffectiveCandidates<T extends { title?: string | null }>(
  candidates: T[],
  papers: HasCurrentPaper | null | undefined,
): T[] {
  if (papers?.current_paper) return [];
  return filterEnglishCandidatePapers(candidates);
}
