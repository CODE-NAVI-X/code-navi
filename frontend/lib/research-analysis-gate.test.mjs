import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { describeAnalysisBlocker } from "./research-analysis-gate.ts";

/**
 * 回归背景（真实浏览器 2026-09-11）：
 *
 * 研究开展阶段，用户确认四组检索词后后端并没有真正检索（没有候选论文），
 * 但页面上的「进入结果分析」按钮**一直可点**——它只看当前阶段，不看
 * evidence bundle / 候选论文 / 已确认论文。点下去还会隐式发起一次检索，
 * 拉回 4 篇与主题完全无关的中文论文（乙肝指南 / HUVEC / 新冠 / APTox）。
 *
 * 因此这里把「进入结果分析」的阻塞条件收敛成一个纯函数：
 *   1. 没有真实检索候选论文 → 阻塞（如实说明，不引导去检索）；
 *   2. 有候选但没有用户确认的当前论文 → 阻塞（必须先确认候选）；
 *   3. 两者都满足 → 放行（既有行为保留）。
 */

const here = dirname(fileURLToPath(import.meta.url));
const CONVERSATION_SOURCE = readFileSync(
  join(here, "..", "components", "research", "ResearchConversation.tsx"),
  "utf8",
);

/** 取源码中某个锚点之后的片段，用于锁定按钮接线。 */
function blockAround(source, anchor, radius = 700) {
  const index = source.indexOf(anchor);
  assert.notEqual(index, -1, `未找到锚点：${anchor}`);
  return source.slice(index, index + radius);
}

test("用例 1：没有任何候选论文时，必须阻塞并说明原因", () => {
  const reason = describeAnalysisBlocker({ candidateCount: 0, hasConfirmedPaper: false });
  assert.equal(typeof reason, "string");
  assert.match(reason, /候选论文/);
  // 阻塞原因只做说明，不得变成“点这里去检索”的暗示。
  assert.doesNotMatch(reason, /开始检索|触发检索|点击检索/);
});

test("用例 2：有候选但没有已确认的当前论文时，必须阻塞", () => {
  const reason = describeAnalysisBlocker({ candidateCount: 3, hasConfirmedPaper: false });
  assert.equal(typeof reason, "string");
  assert.match(reason, /确认/);
});

test("用例 3：候选为空（最新一次检索是空结果）时，必须阻塞", () => {
  const reason = describeAnalysisBlocker({ candidateCount: 0, hasConfirmedPaper: true });
  assert.equal(typeof reason, "string");
  assert.match(reason, /候选论文/);
});

test("用例 4：有候选且用户已确认当前论文时，放行", () => {
  assert.equal(
    describeAnalysisBlocker({ candidateCount: 1, hasConfirmedPaper: true }),
    null,
  );
  assert.equal(
    describeAnalysisBlocker({ candidateCount: 5, hasConfirmedPaper: true }),
    null,
  );
});

test("用例 5：按钮必须由门控驱动，并显示阻塞原因", () => {
  assert.match(CONVERSATION_SOURCE, /from "@\/lib\/research-analysis-gate"/);
  assert.match(CONVERSATION_SOURCE, /describeAnalysisBlocker\(/);
  // 候选数与被确认的当前论文必须一起参与判定。
  const gate = blockAround(CONVERSATION_SOURCE, "describeAnalysisBlocker({", 320);
  assert.match(gate, /candidateCount/);
  assert.match(gate, /hasConfirmedPaper/);
  // 禁用与提示都要接上，不能只靠阶段。
  assert.match(
    CONVERSATION_SOURCE,
    /disabled=\{disabled \|\| analysisBlocker !== null\}/,
  );
  assert.match(CONVERSATION_SOURCE, /title=\{analysisBlocker \?\? undefined\}/);
});

test("用例 6：点击「进入结果分析」不得触发隐藏检索", () => {
  const button = blockAround(
    CONVERSATION_SOURCE,
    'onClick={() => void handleSend("文献精读与实验方案已完成，可以进入结果分析。")}',
    200,
  );
  // 该消息是阶段推进陈述，不得含任何检索/搜索字样。
  assert.doesNotMatch(button, /检索/);
  assert.doesNotMatch(button, /搜索/);
});

test("用例 7：点击候选论文仍然只进入待确认流程", () => {
  assert.match(CONVERSATION_SOURCE, /我想选择这篇论文作为复现候选/);
  // 候选卡片不得直接调用选论文接口。
  const cards = blockAround(CONVERSATION_SOURCE, "<SearchCandidateCards", 400);
  assert.doesNotMatch(cards, /selectOrchestratorPaper/);
});

test("用例 8：没有候选时不渲染候选卡片区块", () => {
  assert.match(CONVERSATION_SOURCE, /\{searchCandidates\.length > 0 && \(/);
});
