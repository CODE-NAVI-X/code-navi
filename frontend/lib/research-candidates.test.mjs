import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MAX_CANDIDATE_PAPERS,
  createCandidateScope,
  loadSearchCandidates,
  pickLatestCandidatePapers,
} from "./research-candidates.ts";

/**
 * 回归背景：点击“新建对话”后，页面清空了会话/编排器状态/方向卡/已选论文/草稿，
 * 却没有清空候选论文列表，也没有按新的 conversation_id 重新读取 evidence bundles。
 * 于是新会话一打开就显示上一个会话的候选论文，看起来像“新会话自动检索过”。
 *
 * 后端按 conversation_id 隔离本身是正确的，本轮只修前端会话切换时的候选状态：
 *   1. 新建会话时旧候选必须立即清空；
 *   2. 新会话必须按自己的 conversation_id 重新读取候选；
 *   3. 旧会话的迟到响应（成功或失败）都不得污染新会话；
 *   4. 刷新页面恢复旧会话的既有持久化语义保持不变。
 */

/** 只保留候选卡片关心的字段，避免测试被无关类型细节绑住。 */
function paper(title) {
  return { paper_id: `paper-${title}`, title, url: `https://example.org/${title}` };
}

/** 一个 evidence bundle（后端按 conversation_id 隔离返回）。 */
function bundle(...titles) {
  return { papers: titles.map(paper) };
}

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
// 7. 候选挑选沿用既有语义（本轮不改变检索/排序行为）
// ---------------------------------------------------------------------------

test("候选挑选沿用既有语义：跳过空 bundle、取最后一个、最多 5 篇、保持原顺序", () => {
  assert.equal(MAX_CANDIDATE_PAPERS, 5);

  const sixPapers = bundle("甲", "乙", "丙", "丁", "戊", "己");
  assert.deepEqual(titles(pickLatestCandidatePapers([sixPapers])), [
    "甲",
    "乙",
    "丙",
    "丁",
    "戊",
  ]);

  // 没有论文的 bundle 被跳过，取最后一个带论文的 bundle（既有行为）
  const bundles = [sixPapers, { papers: [] }, bundle("庚")];
  assert.deepEqual(titles(pickLatestCandidatePapers(bundles)), ["庚"]);

  // 不修改调用方传入的数据
  const input = [bundle("甲")];
  pickLatestCandidatePapers(input);
  assert.equal(input[0].papers.length, 1);
});
