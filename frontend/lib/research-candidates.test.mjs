import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MAX_CANDIDATE_PAPERS,
  createCandidateScope,
  filterEnglishCandidatePapers,
  loadSearchCandidates,
  pickLatestCandidatePapers,
} from "./research-candidates.ts";

/**
 * 回归背景（两轮）：
 *
 * 第一轮：点击“新建对话”后，页面清空了会话/编排器状态/方向卡/已选论文/草稿，
 * 却没有清空候选论文列表，也没有按新的 conversation_id 重新读取 evidence bundles。
 * 于是新会话一打开就显示上一个会话的候选论文，看起来像“新会话自动检索过”。
 *
 * 第二轮（真实浏览器）：一次明确返回空结果的检索之后，页面仍然显示上一轮检索
 * 留下的 5 张无关英文论文卡片（NASA 系外行星 / 超导 / 数学递推 / D3-brane / LiFeAs），
 * 用户因此无法选择论文、无法进入第四阶段。根因是“跳过空 bundle 去找更早的有论文 bundle”。
 *
 * 后端按 conversation_id 隔离本身是正确的，本轮只修前端候选状态：
 *   1. 新建会话时旧候选必须立即清空；
 *   2. 新会话必须按自己的 conversation_id 重新读取候选；
 *   3. 旧会话的迟到响应（成功或失败）都不得污染新会话；
 *   4. 刷新页面恢复旧会话的既有持久化语义保持不变；
 *   5. **最新 bundle 为空结果时，候选必须是空的——绝不回退到更早的 bundle**。
 */

/**
 * “最新 evidence bundle”的定义（已核对后端源码，见 tests/test_research_frontend_copy.py
 * 的排序契约用例）：
 *
 *   GET /api/v1/research/conversations/{id}/evidence-bundles
 *     → ConversationSearchService.list_bundles
 *     → .order_by(ResearchEvidenceBundleModel.created_at.desc())
 *   会话恢复路径 ConversationService._evidence_bundles 同样是 created_at.desc()。
 *
 * 即接口按时间倒序返回，**数组下标 0 就是最新一次检索的 bundle**。
 * 下面所有用例都按这个顺序构造数组。
 */

/** 只保留候选卡片关心的字段，避免测试被无关类型细节绑住。 */
function paper(title) {
  return { paper_id: `paper-${title}`, title, url: `https://example.org/${title}` };
}

/** 一个 evidence bundle（后端按 conversation_id 隔离返回）。 */
function bundle(...titles) {
  return { papers: titles.map(paper) };
}

/** 带来源状态 / provenance / 失败原因的 bundle（用于锁定空结果语义不被改写）。 */
function bundleWithMetadata(...titles) {
  return {
    papers: titles.map(paper),
    source_statuses: [{ source: "crossref", status: "ok" }],
    queried_sources: ["crossref", "arxiv"],
    failure_reasons: titles.length === 0 ? ["no_relevant_result"] : [],
    provenance_note: "仅元数据与摘要，未下载全文",
  };
}

/** 真实浏览器里出现的 5 篇无关论文（第一轮检索的遗留结果）。 */
const UNRELATED_OLD_TITLES = [
  "Exoplanet atmospheres with JWST",
  "Superconductivity in twisted bilayer graphene",
  "A recursive approach to counting",
  "Branes and D3-brane dynamics",
  "LiFeAs: a stoichiometric superconductor",
];

/** 手工可控的 promise，用来模拟“旧请求晚返回”。 */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function titles(papers) {
  return papers.map((item) => item.title);
}

const CONVERSATION_SOURCE = readFileSync(
  new URL("../components/research/ResearchConversation.tsx", import.meta.url),
  "utf8",
);

/** 取出一个函数体，避免断言匹配到文件里别处的同名符号。 */
function functionBody(source, from, to) {
  return source.split(from, 2)[1].split(to, 1)[0];
}

const NEW_CONVERSATION_BODY = functionBody(
  CONVERSATION_SOURCE,
  "async function handleStartNewConversation",
  "function handleFormSubmit",
);

const RESTORE_BODY = functionBody(
  CONVERSATION_SOURCE,
  "const restoreOrCreate = useCallback",
  "\n  }, [",
);

// ---------------------------------------------------------------------------
// 1. 新建会话立即隐藏旧候选
// ---------------------------------------------------------------------------

test("会话切换后旧会话的在途请求立即作废（迟到响应无法回填候选）", () => {
  const scope = createCandidateScope();

  const oldTicket = scope.beginRequest("conv-old");
  assert.equal(scope.accepts(oldTicket), true, "当前会话的请求应当被采纳");

  // 用户点击“新建对话”：先切离旧会话
  scope.switchTo(null);
  assert.equal(
    scope.accepts(oldTicket),
    false,
    "切离旧会话后，旧请求必须立即作废，否则迟到响应会把旧候选重新贴到新会话上",
  );

  // 新会话开始读取自己的候选
  const newTicket = scope.beginRequest("conv-new");
  assert.equal(scope.accepts(oldTicket), false);
  assert.equal(scope.accepts(newTicket), true);
});

test("新建会话的重置逻辑里必须同步清空候选，且发生在发起创建请求之前", () => {
  assert.ok(
    NEW_CONVERSATION_BODY.includes("setSearchCandidates([])"),
    "handleStartNewConversation 必须清空 searchCandidates",
  );
  assert.ok(
    NEW_CONVERSATION_BODY.indexOf("setSearchCandidates([])") <
      NEW_CONVERSATION_BODY.indexOf("await createResearchConversation()"),
    "候选必须在发起创建请求之前就清空：重置要立即生效，不能等接口返回",
  );
  assert.ok(
    NEW_CONVERSATION_BODY.includes("switchTo(null)"),
    "重置时必须切离旧会话，作废旧会话在途的候选读取",
  );
});

test("同一会话内重复读取时，只有最后一次请求的结果会被采纳", () => {
  const scope = createCandidateScope();
  const first = scope.beginRequest("conv-1");
  const second = scope.beginRequest("conv-1");

  assert.equal(scope.accepts(first), false, "更早的请求必须让位给最新请求");
  assert.equal(scope.accepts(second), true);
});

// ---------------------------------------------------------------------------
// 2. 新会话重新读取候选使用新 conversation_id
// ---------------------------------------------------------------------------

test("新会话按自己的 conversation_id 重新读取候选，不使用旧会话 id", () => {
  assert.ok(
    NEW_CONVERSATION_BODY.includes("refreshSearchCandidates(created.conversation_id)"),
    "新建会话成功后必须按 created.conversation_id 重新读取候选",
  );
  assert.ok(
    !NEW_CONVERSATION_BODY.includes("refreshSearchCandidates(conversation.conversation_id)"),
    "新会话不得沿用旧会话 id 读取候选",
  );
});

test("读取候选时把请求打到传入的 conversation_id 上", async () => {
  const scope = createCandidateScope();
  const requested = [];
  const applied = [];

  await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async (conversationId) => {
      requested.push(conversationId);
      return [bundle("新会话论文 A")];
    },
    apply: (papers) => applied.push(titles(papers)),
  });

  assert.deepEqual(requested, ["conv-new"]);
  assert.deepEqual(applied, [["新会话论文 A"]]);
});

// ---------------------------------------------------------------------------
// 3. 后端返回空 bundle 时页面没有候选卡
// ---------------------------------------------------------------------------

test("新会话没有任何 evidence bundle 时，候选被清空（页面不显示候选卡）", async () => {
  const scope = createCandidateScope();
  const applied = [];

  const accepted = await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => [],
    apply: (papers) => applied.push(titles(papers)),
  });

  assert.equal(accepted, true);
  assert.deepEqual(applied, [[]], "空 bundle 必须把候选置空，而不是保留旧值");
  assert.deepEqual(pickLatestCandidatePapers([]), []);
  assert.deepEqual(pickLatestCandidatePapers([{ papers: [] }]), []);
  // 页面只在有候选时才渲染候选卡
  assert.ok(CONVERSATION_SOURCE.includes("searchCandidates.length > 0"));
});

test("读取候选失败时按“没有候选”处理，不留旧值", async () => {
  const scope = createCandidateScope();
  const applied = [];

  const accepted = await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => {
      throw new Error("后端不可用");
    },
    apply: (papers) => applied.push(titles(papers)),
  });

  assert.equal(accepted, true);
  assert.deepEqual(applied, [[]]);
});

// ---------------------------------------------------------------------------
// 4. 新会话已有 bundle 时只显示新会话候选
// ---------------------------------------------------------------------------

test("旧会话先读到候选，新建会话后只显示新会话自己的候选", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  await loadSearchCandidates("conv-old", {
    scope,
    fetchBundles: async () => [bundle("旧会话论文 1", "旧会话论文 2")],
    apply,
  });
  assert.deepEqual(applied, [["旧会话论文 1", "旧会话论文 2"]]);

  // 点击“新建对话”：立即清空并切离旧会话
  scope.switchTo(null);

  await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => [bundle("新会话论文 A")],
    apply,
  });

  assert.deepEqual(applied.at(-1), ["新会话论文 A"], "新会话只能显示自己的候选");
});

// ---------------------------------------------------------------------------
// 5. 旧请求晚返回不会污染新会话
// ---------------------------------------------------------------------------

test("旧会话的迟到成功响应不得覆盖新会话候选", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  const oldResponse = deferred();
  const oldLoad = loadSearchCandidates("conv-old", {
    scope,
    fetchBundles: () => oldResponse.promise,
    apply,
  });

  // 用户新建会话，并读到新会话自己的候选
  scope.switchTo(null);
  await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => [bundle("新会话论文")],
    apply,
  });
  assert.deepEqual(applied, [["新会话论文"]]);

  // 旧会话的响应此刻才回来
  oldResponse.resolve([bundle("旧会话论文")]);
  assert.equal(await oldLoad, false, "过期请求不得报告为已采纳");
  assert.deepEqual(applied, [["新会话论文"]], "旧请求晚返回不得污染新会话候选");
});

test("旧会话的迟到失败响应同样不得清空新会话候选", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  const oldResponse = deferred();
  const oldLoad = loadSearchCandidates("conv-old", {
    scope,
    fetchBundles: () => oldResponse.promise,
    apply,
  });

  scope.switchTo(null);
  await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => [bundle("新会话论文")],
    apply,
  });

  oldResponse.reject(new Error("旧会话读取失败"));
  assert.equal(await oldLoad, false);
  assert.deepEqual(applied, [["新会话论文"]]);
});

test("直接从旧会话切到新会话时，旧会话在途请求同样作废", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  const oldResponse = deferred();
  const oldLoad = loadSearchCandidates("conv-old", {
    scope,
    fetchBundles: () => oldResponse.promise,
    apply,
  });

  await loadSearchCandidates("conv-new", {
    scope,
    fetchBundles: async () => [bundle("新会话论文")],
    apply,
  });

  oldResponse.resolve([bundle("旧会话论文")]);
  await oldLoad;
  assert.deepEqual(applied, [["新会话论文"]]);
});

// ---------------------------------------------------------------------------
// 6. 刷新页面恢复旧会话的既有行为不被破坏
// ---------------------------------------------------------------------------

test("刷新恢复会话时仍按恢复到的会话 id 读取历史候选，且不清空", () => {
  assert.ok(
    RESTORE_BODY.includes("getResearchConversation(savedId)"),
    "刷新时必须继续从 localStorage 恢复旧会话（持久化语义不变）",
  );
  assert.ok(
    RESTORE_BODY.includes("refreshSearchCandidates(activeConversationId)"),
    "恢复会话后必须继续按恢复到的会话 id 读取历史候选",
  );
  assert.ok(
    !RESTORE_BODY.includes("setSearchCandidates([])"),
    "恢复路径不得清空候选：这是持久化恢复，不是新建会话",
  );
  assert.ok(
    !RESTORE_BODY.includes("switchTo(null)"),
    "恢复路径不得切离会话",
  );
});

test("按恢复到的会话 id 读取时能拿回该会话自己的历史候选", async () => {
  const scope = createCandidateScope();
  const requested = [];
  const applied = [];

  await loadSearchCandidates("conv-restored", {
    scope,
    fetchBundles: async (conversationId) => {
      requested.push(conversationId);
      return [bundle("历史候选论文")];
    },
    apply: (papers) => applied.push(titles(papers)),
  });

  assert.deepEqual(requested, ["conv-restored"]);
  assert.deepEqual(applied, [["历史候选论文"]]);
});

// ---------------------------------------------------------------------------
// 7. 最新 bundle 语义（严格）：空结果不得回退到更早的 bundle
// ---------------------------------------------------------------------------

test("用例 1：最新 bundle 为空、较早 bundle 有论文 → 必须为空", () => {
  // 顺序 = 接口顺序 = created_at.desc()：下标 0 是最新一次检索（空结果）
  const bundles = [bundle(), bundle(...UNRELATED_OLD_TITLES)];

  assert.deepEqual(
    pickLatestCandidatePapers(bundles),
    [],
    "空结果之后不得把更早一轮的无关论文重新显示出来",
  );
});

test("用例 2：只有一个空 bundle → 必须为空", () => {
  assert.deepEqual(pickLatestCandidatePapers([bundle()]), []);
  // 空 bundle 自己也带 metadata 时同样是空
  assert.deepEqual(pickLatestCandidatePapers([bundleWithMetadata()]), []);
});

test("用例 3：只有一个有论文 bundle → 保持原顺序，最多 5 篇", () => {
  assert.equal(MAX_CANDIDATE_PAPERS, 5);

  const single = bundle("甲", "乙", "丙");
  assert.deepEqual(titles(pickLatestCandidatePapers([single])), ["甲", "乙", "丙"]);

  // 超过 5 篇时截断，且顺序与后端返回一致
  const six = bundle("甲", "乙", "丙", "丁", "戊", "己");
  assert.deepEqual(titles(pickLatestCandidatePapers([six])), [
    "甲",
    "乙",
    "丙",
    "丁",
    "戊",
  ]);
});

test("用例 4：最新 bundle 有论文、较早也有 → 只返回最新的，不混合", () => {
  const bundles = [
    bundle("最新·论文 1", "最新·论文 2"),
    bundle(...UNRELATED_OLD_TITLES),
  ];

  const result = titles(pickLatestCandidatePapers(bundles));
  assert.deepEqual(result, ["最新·论文 1", "最新·论文 2"]);
  for (const old of UNRELATED_OLD_TITLES) {
    assert.equal(result.includes(old), false, `不得混入更早 bundle 的论文：${old}`);
  }
});

test("用例 4b：多个历史 bundle 时只看最新那一个", () => {
  const bundles = [
    bundle("最新论文"),
    bundle("上一轮论文"),
    bundle("更早论文"),
  ];
  assert.deepEqual(titles(pickLatestCandidatePapers(bundles)), ["最新论文"]);
});

test("用例 1b：最新 bundle 为空、较早有多轮有论文 → 必须为空", () => {
  const bundles = [
    bundle(),
    bundle("上一轮论文 A", "上一轮论文 B"),
    bundle(...UNRELATED_OLD_TITLES),
  ];
  assert.deepEqual(pickLatestCandidatePapers(bundles), []);
});

test("用例 5：空结果 bundle 只按 papers 判定，不因来源状态/metadata 被跳过", () => {
  // 空结果 bundle 依然带 source_statuses / queried_sources / failure_reasons /
  // provenance_note。这些字段必须原样保留在 bundle 里，前端不得据此判定“跳过它”。
  const emptyWithMetadata = bundleWithMetadata();
  const bundles = [emptyWithMetadata, bundleWithMetadata(...UNRELATED_OLD_TITLES)];

  assert.deepEqual(pickLatestCandidatePapers(bundles), []);
  // 不改写来源状态与 provenance（只做读取）
  assert.equal(emptyWithMetadata.papers.length, 0);
  assert.deepEqual(emptyWithMetadata.queried_sources, ["crossref", "arxiv"]);
  assert.equal(emptyWithMetadata.provenance_note, "仅元数据与摘要，未下载全文");

  // 有论文时同样只看最新 bundle
  assert.deepEqual(
    titles(pickLatestCandidatePapers([bundleWithMetadata("唯一候选"), bundleWithMetadata("旧候选")])),
    ["唯一候选"],
  );
});

test("用例 9：完全没有任何 bundle → 空（不是错误，也不是伪造结果）", () => {
  assert.deepEqual(pickLatestCandidatePapers([]), []);
  assert.deepEqual(pickLatestCandidatePapers(null), []);
  assert.deepEqual(pickLatestCandidatePapers(undefined), []);
  // 缺 papers 字段的脏数据按空处理，不抛错
  assert.deepEqual(pickLatestCandidatePapers([{}]), []);

  // 只读：不修改调用方传入的 bundle 数组与其中的 papers
  const input = [bundle("甲", "乙")];
  const picked = pickLatestCandidatePapers(input);
  assert.deepEqual(titles(picked), ["甲", "乙"]);
  assert.equal(input.length, 1);
  assert.equal(input[0].papers.length, 2);
  assert.notEqual(picked, input[0].papers, "返回的是切片副本，不是原数组引用");
});

test("展示候选只保留可保守确认的英文标题", () => {
  const papers = [
    { title: "慢性乙型肝炎防治指南（2022年版）" },
    { title: "HUVEC 成管实验和结果分析" },
    { title: "Deep Learning for Image Classification" },
    { title: "" },
    { title: "CNN f(x) = ReLU(x) — Smith et al." },
    { title: "基于深度学习的 CIFAR-10 图像分类方法" },
    { title: "SHAP-based attribution stability" },
  ];

  assert.deepEqual(
    titles(filterEnglishCandidatePapers(papers)),
    [
      "Deep Learning for Image Classification",
      "CNN f(x) = ReLU(x) — Smith et al.",
      "SHAP-based attribution stability",
    ],
  );
});

test("英文标题过滤保持顺序并在展示层最多保留 5 篇", () => {
  const papers = [
    { title: "Paper 1" },
    { title: "中文论文" },
    { title: "Paper 2" },
    { title: "Paper 3" },
    { title: "Paper 4" },
    { title: "Paper 5" },
    { title: "Paper 6" },
  ];

  assert.deepEqual(
    titles(filterEnglishCandidatePapers(papers).slice(0, MAX_CANDIDATE_PAPERS)),
    ["Paper 1", "Paper 2", "Paper 3", "Paper 4", "Paper 5"],
  );
});

test("用例 5b：空结果后页面候选被清空，不再保留上一轮检索的论文", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  // 第一轮检索：真实候选（浏览器里是 5 篇无关英文论文）
  await loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: async () => [bundle(...UNRELATED_OLD_TITLES)],
    apply,
  });
  assert.deepEqual(applied.at(-1), UNRELATED_OLD_TITLES);

  // 第二轮检索返回空结果 → 新 bundle 排在数组最前
  await loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: async () => [bundle(), bundle(...UNRELATED_OLD_TITLES)],
    apply,
  });

  assert.deepEqual(applied.at(-1), [], "空结果必须把页面候选清空");
  for (const old of UNRELATED_OLD_TITLES) {
    assert.equal(applied.at(-1).includes(old), false, `旧论文不得残留：${old}`);
  }
  // 页面只在有候选时才渲染候选区域
  assert.ok(CONVERSATION_SOURCE.includes("searchCandidates.length > 0"));
});

test("用例 5c：重试本轮完成后同样按最新 bundle 刷新候选", () => {
  // 重试会重放上一轮用户消息；若那一轮触发了检索，就会再写一个 bundle
  // （空结果也算一个）。三条会追加 assistant 消息的路径都必须刷新候选，
  // 否则空结果之后卡片仍是上一轮的旧论文。
  const retryBody = functionBody(
    CONVERSATION_SOURCE,
    "async function handleRetry",
    "} finally {",
  );

  assert.ok(
    retryBody.includes("refreshSearchCandidates(conversation.conversation_id)"),
    "重试完成后必须按当前会话重新读取候选",
  );
});

// ---------------------------------------------------------------------------
// 8. 同一会话内新检索请求迟到，不得覆盖更新的结果
// ---------------------------------------------------------------------------

test("用例 8：同一会话里先发起的请求晚返回，不得覆盖后发起的请求结果", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  const firstResponse = deferred();
  const firstLoad = loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: () => firstResponse.promise,
    apply,
  });

  // 用户又触发了一次检索（或新一轮对话完成），候选重新读取
  await loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: async () => [bundle(), bundle("旧结果")],
    apply,
  });
  assert.deepEqual(applied, [[]], "第二次读取到空结果，候选应立即清空");

  // 第一次请求此刻才回来，带着过期的旧论文
  firstResponse.resolve([bundle("过期论文 1", "过期论文 2")]);
  assert.equal(await firstLoad, false, "过期请求不得被采纳");
  assert.deepEqual(applied, [[]], "过期的旧结果不得覆盖更新的空结果");
});

test("用例 8b：同一会话里新结果先到、旧结果后到，最终保留新结果", async () => {
  const scope = createCandidateScope();
  const applied = [];
  const apply = (papers) => applied.push(titles(papers));

  const staleResponse = deferred();
  const staleLoad = loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: () => staleResponse.promise,
    apply,
  });

  await loadSearchCandidates("conv-1", {
    scope,
    fetchBundles: async () => [bundle("新检索论文")],
    apply,
  });

  staleResponse.resolve([bundle("旧一轮论文")]);
  await staleLoad;

  assert.deepEqual(applied, [["新检索论文"]]);
});

// ---------------------------------------------------------------------------
// 9. 候选卡片的只读语义（点击只进待确认流程）
// ---------------------------------------------------------------------------

test("候选卡片点击只发待确认消息，不直接设置为当前论文", () => {
  assert.ok(CONVERSATION_SOURCE.includes("我想选择这篇论文作为复现候选"));
  assert.ok(
    !CONVERSATION_SOURCE.split("<SearchCandidateCards", 2)[1]
      .split("/>", 1)[0]
      .includes("selectOrchestratorPaper"),
    "点击候选卡片不得直接调用选论文接口",
  );
  // 卡片组件自身也不持有选论文能力
  const cards = readFileSync(
    new URL("../components/research/SearchCandidateCards.tsx", import.meta.url),
    "utf8",
  );
  assert.ok(cards.includes("确认后才会设为当前论文"));
  assert.ok(!cards.includes("selectOrchestratorPaper"));
});
