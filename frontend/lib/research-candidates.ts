/**
 * 科研对话“候选论文卡片”的会话归属与加载（纯逻辑）。
 *
 * 背景：点击“新建对话”后，页面清空了会话、编排器状态、方向卡、已选论文与草稿，
 * 却没有清空候选论文列表，也没有按新的 conversation_id 重新读取 evidence bundles。
 * 结果是新会话一打开就显示上一个会话的候选论文，看起来像“新会话自动检索过”。
 *
 * 后端按 conversation_id 隔离本身是正确的，问题只在前端状态，需要三件事：
 * 1. 切换会话时立即清空候选；
 * 2. 候选按当前会话 id 重新读取；
 * 3. 旧会话的迟到响应（成功或失败）不得覆盖新会话的结果——归属校验。
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
 * 从当前会话的 evidence bundles 中取出候选论文。
 *
 * 语义与既有实现保持一致（本轮不改变检索、排序与切片行为）：
 * 跳过没有论文的 bundle，取**最后一个**带论文的 bundle，最多 `MAX_CANDIDATE_PAPERS` 篇，
 * 并保持后端返回的原始顺序。
 */
export function pickLatestCandidatePapers<T>(
  bundles: readonly CandidateBundleLike<T>[],
  limit: number = MAX_CANDIDATE_PAPERS,
): T[] {
  const withPapers = (bundles ?? []).filter(
    (bundle) => Array.isArray(bundle?.papers) && bundle.papers.length > 0,
  );
  const latest = withPapers[withPapers.length - 1];
  if (!latest) return [];
  return latest.papers.slice(0, limit);
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
