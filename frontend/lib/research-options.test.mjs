import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildAnswerMessage,
  buildAssistantConversationMessage,
  buildOptionFillText,
  buildStructuredOptionGroup,
  parseOptionGroups,
  splitMessageSegments,
  toggleOptionKey,
} from "./research-options.ts";

/** 读取同级组件源码，用于锁定“选项组件不得具备发送能力”这一结构契约。 */
function readComponentSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

/**
 * 科研对话真实场景：姜姜的回复正文里已经把 A/B/C/D 写成静态列表，前端又单独解析出
 * 同一组选项，导致同一题目出现两份 A/B/C/D。
 *
 * 修复目标有两层：
 * 1. 同一组选项只出现一次，且正文里对应的静态行被摘掉；
 * 2. 选项组必须渲染在**对应题干的正下方**，而不是整条消息的末尾——
 *    即“问题 1 题干 < 交互选项 < 问题 2 题干”的顺序不能被打乱。
 */
const CNN_REPLY = [
  "问题 1：你想研究 CNN 的哪个层面？",
  "",
  "A. 应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）",
  "B. 方法层：改进 CNN 结构或训练方法",
  "C. 理解层：分析 CNN 的机制、鲁棒性或可解释性",
  "D. 还没想好，想让我帮你列几个具体子方向",
  "",
  "问题 2：你目前手上有哪些条件？",
  "",
  "- 数据集：有没有可用的数据？",
  "- GPU：显存与算力条件如何？",
  "- 研究偏好：更偏向理论还是工程？",
].join("\n");

const EXPLICIT_TEXT = [
  "A. 应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）",
  "B. 方法层：改进 CNN 结构或训练方法",
  "C. 理解层：分析 CNN 的机制、鲁棒性或可解释性",
  "D. 还没想好，想让我帮你列几个具体子方向",
];

const QUESTION_1 = "问题 1：你想研究 CNN 的哪个层面？";
const QUESTION_2 = "问题 2：你目前手上有哪些条件？";

/** 只保留 markdown 片段的正文，用来验证“正文里不再有静态选项行”。 */
function markdownOnly(content) {
  return splitMessageSegments(content)
    .filter((segment) => segment.kind === "markdown")
    .map((segment) => segment.content)
    .join("\n\n");
}

/**
 * 按组件实际渲染顺序把消息展开成一段文本：
 * markdown 片段原样输出，选项组按 `A. 选项文本` 展开。
 * 组件就是按 segments 数组顺序渲染的，因此这个字符串的字符先后即 DOM 先后。
 */
function renderOrder(content) {
  return splitMessageSegments(content)
    .map((segment) =>
      segment.kind === "markdown"
        ? segment.content
        : segment.group.options.map((option) => `${option.key}. ${option.text}`).join("\n"),
    )
    .join("\n");
}

test("问题 1 的 A/B/C/D 解析为唯一一组选项，每项只出现一次", () => {
  const groups = parseOptionGroups(CNN_REPLY);

  assert.equal(groups.length, 1);
  const [group] = groups;
  assert.equal(group.options.length, 4);
  assert.deepEqual(
    group.options.map((option) => option.key),
    ["A", "B", "C", "D"],
  );
  assert.equal(group.title, QUESTION_1);

  // 选项文本保持原文，不做改写
  assert.equal(group.options[0].text, "应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）");
  assert.equal(group.options[3].text, "还没想好，想让我帮你列几个具体子方向");
});

test("消息被切成 顺序片段：题干 markdown -> 选项组 -> 问题 2 markdown", () => {
  const segments = splitMessageSegments(CNN_REPLY);

  assert.deepEqual(
    segments.map((segment) => segment.kind),
    ["markdown", "options", "markdown"],
  );

  // 片段 0：只有问题 1 题干，不含问题 2
  assert.equal(segments[0].content.includes(QUESTION_1), true);
  assert.equal(segments[0].content.includes(QUESTION_2), false);

  // 片段 1：就是那一组 A/B/C/D 交互选项
  assert.deepEqual(
    segments[1].group.options.map((option) => option.key),
    ["A", "B", "C", "D"],
  );

  // 片段 2：问题 2 及其引导文字完整保留
  assert.equal(segments[2].content.includes(QUESTION_2), true);
  assert.equal(segments[2].content.includes("- 数据集：有没有可用的数据？"), true);
  assert.equal(segments[2].content.includes("- GPU：显存与算力条件如何？"), true);
  assert.equal(segments[2].content.includes("- 研究偏好：更偏向理论还是工程？"), true);
});

test("顺序契约：问题 1 题干 < 交互式 A/B/C/D < 问题 2 题干", () => {
  const rendered = renderOrder(CNN_REPLY);

  const q1 = rendered.indexOf(QUESTION_1);
  const q2 = rendered.indexOf(QUESTION_2);
  const optionPositions = EXPLICIT_TEXT.map((text) =>
    rendered.indexOf(`${text.slice(0, 1)}. ${text.slice(3)}`),
  );

  assert.notEqual(q1, -1, "题干“问题 1”必须出现");
  assert.notEqual(q2, -1, "题干“问题 2”必须出现");
  for (const [index, position] of optionPositions.entries()) {
    assert.notEqual(position, -1, `选项 ${EXPLICIT_TEXT[index]} 必须渲染出来`);
  }

  // 选项组整体夹在问题 1 与问题 2 之间
  assert.ok(q1 < Math.min(...optionPositions), "A/B/C/D 必须渲染在问题 1 之后");
  assert.ok(Math.max(...optionPositions) < q2, "A/B/C/D 必须渲染在问题 2 之前");

  // 每个选项按 A、B、C、D 的先后出现
  assert.deepEqual(
    optionPositions.slice().sort((a, b) => a - b),
    optionPositions,
  );
});

test("正文里不再残留静态 A/B/C/D，只由交互选项渲染一份", () => {
  const body = markdownOnly(CNN_REPLY);

  for (const line of EXPLICIT_TEXT) {
    assert.equal(body.includes(line), false, `正文不应再包含静态选项行：${line}`);
  }
  for (const key of ["A", "B", "C", "D"]) {
    assert.equal(new RegExp(`^${key}\\.`, "m").test(body), false);
  }

  assert.equal(body.includes(QUESTION_1), true);
  assert.equal(body.includes(QUESTION_2), true);

  // 摘掉选项后不应留下成片空行
  assert.equal(/\n{3,}/.test(body), false);
});

test("渲染结果里每个选项键都只出现一次", () => {
  const rendered = renderOrder(CNN_REPLY);

  for (const line of EXPLICIT_TEXT) {
    const marker = `${line.slice(0, 1)}. ${line.slice(3)}`;
    assert.equal(rendered.split(marker).length - 1, 1, `${marker} 只能出现一次`);
  }
});

test("没有原文行的“计划执行确认”虚拟选项追加在正文之后", () => {
  const confirmReply = [
    "四、计划确认",
    "如果你确认无误，我们开始执行；如果对计划有任何调整需求请直接提出。",
  ].join("\n");

  const segments = splitMessageSegments(confirmReply);

  // 虚拟选项没有原文行，只能挂在末尾：先是正文，再是选项组
  assert.deepEqual(
    segments.map((segment) => segment.kind),
    ["markdown", "options"],
  );
  assert.equal(segments[1].group.title, "计划执行确认");
  assert.deepEqual(
    segments[1].group.options.map((option) => option.key),
    ["A", "B"],
  );
  assert.equal(segments[0].content.includes("四、计划确认"), true);
});

test("拍板决策分支的选项同样切在题干正下方", () => {
  const branchReply = [
    "是否把这篇论文纳入复现范围？",
    "",
    "- 如果纳入：我会把它加入复现清单并安排基线对比",
    "- 如果跳过：我会继续检索其他候选论文",
    "",
    "补充说明：以上任一选择都可以再补充条件。",
  ].join("\n");

  const segments = splitMessageSegments(branchReply);

  assert.deepEqual(
    segments.map((segment) => segment.kind),
    ["markdown", "options", "markdown"],
  );
  assert.equal(segments[0].content.includes("是否把这篇论文纳入复现范围？"), true);
  assert.equal(segments[1].group.options.length, 2);
  assert.equal(segments[2].content.includes("补充说明：以上任一选择都可以再补充条件。"), true);
});

test("没有选项组时只有一段 markdown，正文原样保留", () => {
  const plain = "我们今天先聊聊你的研究兴趣。";
  assert.deepEqual(parseOptionGroups(plain), []);
  assert.deepEqual(splitMessageSegments(plain), [{ kind: "markdown", content: plain }]);
});

test("单行字母内容不成组，也不会把正文切碎", () => {
  const single = ["引言", "A. 只有一个孤立的字母条目", "结论"].join("\n");
  assert.deepEqual(parseOptionGroups(single), []);
  assert.deepEqual(splitMessageSegments(single), [{ kind: "markdown", content: single }]);
});

// ---------------------------------------------------------------------------
// 结构化字段（next_question / suggested_answers）
// ---------------------------------------------------------------------------

/** 后端结构化契约：一道待答问题 + 2~4 条建议答案。 */
const STRUCTURED_REPLY = {
  content: CNN_REPLY,
  next_question: QUESTION_1,
  suggested_answers: EXPLICIT_TEXT.map((line) => line.slice(3)),
};

test("结构化建议答案 >=2 条时构造出可点选选项组", () => {
  const group = buildStructuredOptionGroup(STRUCTURED_REPLY);

  assert.notEqual(group, null);
  assert.deepEqual(
    group.options.map((option) => option.key),
    ["A", "B", "C", "D"],
  );
  assert.equal(group.title, QUESTION_1);
  assert.equal(group.options[0].text, EXPLICIT_TEXT[0].slice(3));
  // 填充文案与既有交互保持一致
  assert.equal(group.options[0].fillValue, `我选 A：${EXPLICIT_TEXT[0].slice(3)}`);
});

test("建议答案少于 2 条时不构造选项组，保持自由输入", () => {
  assert.equal(buildStructuredOptionGroup({ next_question: QUESTION_1 }), null);
  assert.equal(
    buildStructuredOptionGroup({ next_question: QUESTION_1, suggested_answers: [] }),
    null,
  );
  assert.equal(
    buildStructuredOptionGroup({ next_question: QUESTION_1, suggested_answers: ["只有一个"] }),
    null,
  );
  assert.equal(buildStructuredOptionGroup({ suggested_answers: ["a", "b"] }), null);
});

test("结构化选项优先：与正文 A/B/C/D 同时存在时只渲染一份", () => {
  const group = buildStructuredOptionGroup(STRUCTURED_REPLY);
  const segments = splitMessageSegments(CNN_REPLY, group);

  const optionSegments = segments.filter((segment) => segment.kind === "options");
  assert.equal(optionSegments.length, 1, "只能有一组交互选项");

  // 渲染的是结构化来源，而不是碰巧写在正文里的同款文本
  assert.deepEqual(optionSegments[0].group, group);

  const markdown = segments
    .filter((segment) => segment.kind === "markdown")
    .map((segment) => segment.content)
    .join("\n\n");
  for (const line of EXPLICIT_TEXT) {
    assert.equal(markdown.includes(line), false, `正文不应残留静态选项行：${line}`);
  }
});

test("结构化选项插在对应题干之后、问题 2 之前", () => {
  const group = buildStructuredOptionGroup(STRUCTURED_REPLY);
  const segments = splitMessageSegments(CNN_REPLY, group);

  assert.deepEqual(
    segments.map((segment) => segment.kind),
    ["markdown", "options", "markdown"],
  );
  assert.equal(segments[0].content.includes(QUESTION_1), true);
  assert.equal(segments[0].content.includes(QUESTION_2), false);
  assert.equal(segments[2].content.includes(QUESTION_2), true);
  assert.deepEqual(segments[2].group ?? null, null);
});

test("结构化选项在正文里找不到题干时落在末尾，不丢选项", () => {
  const group = buildStructuredOptionGroup({
    next_question: "一个正文里并不存在的题干？",
    suggested_answers: ["甲方案", "乙方案"],
  });
  const segments = splitMessageSegments("我们先随便聊聊别的。", group);

  assert.deepEqual(
    segments.map((segment) => segment.kind),
    ["markdown", "options"],
  );
  assert.equal(segments[1].group.options.length, 2);
});

test("普通编号步骤 1./2. 不会被当成文本选项", () => {
  const numberedPlan = [
    "下面是我建议的推进路径：",
    "1. 先确认研究问题与评价指标",
    "2. 再挑选一篇可复现的基线论文",
    "3. 最后在本地跑通最小实验",
  ].join("\n");

  assert.deepEqual(parseOptionGroups(numberedPlan), []);
  assert.deepEqual(splitMessageSegments(numberedPlan), [
    { kind: "markdown", content: numberedPlan },
  ]);
});

test("实时流式完成的回复映射不会把结构化字段清成 null / []", () => {
  const message = buildAssistantConversationMessage({
    id: "assistant-1",
    content: CNN_REPLY,
    created_at: "2026-09-10T00:00:00Z",
    next_question: QUESTION_1,
    suggested_answers: EXPLICIT_TEXT.map((line) => line.slice(3)),
  });

  assert.equal(message.message_id, "assistant-1");
  assert.equal(message.role, "assistant");
  assert.equal(message.next_question, QUESTION_1);
  assert.deepEqual(message.suggested_answers, EXPLICIT_TEXT.map((line) => line.slice(3)));
});

test("缺少结构化字段时映射成空值而不是抛错（历史兼容降级）", () => {
  const message = buildAssistantConversationMessage({
    id: "assistant-legacy",
    content: "我们先聊聊你的研究兴趣。",
    created_at: "2026-09-10T00:00:00Z",
  });

  assert.equal(message.next_question, null);
  assert.deepEqual(message.suggested_answers, []);
  // 没有结构化字段时仍可回退到正文解析
  assert.equal(buildStructuredOptionGroup(message), null);
});

test("历史会话消息带结构化字段时，仍能重建出可点选选项", () => {
  // 重新加载历史会话：GET 返回的消息已经带上了持久化的结构化字段
  const restored = buildAssistantConversationMessage({
    id: "assistant-restored",
    content: CNN_REPLY,
    created_at: "2026-09-10T00:00:00Z",
    next_question: QUESTION_1,
    suggested_answers: ["应用层：做具体任务", "方法层：改进结构"],
  });

  const group = buildStructuredOptionGroup(restored);
  assert.notEqual(group, null);
  assert.deepEqual(
    group.options.map((option) => option.text),
    ["应用层：做具体任务", "方法层：改进结构"],
  );
});

test("点击选项复用既有填充文案：自动填入输入框并带上补充说明", () => {
  const groups = parseOptionGroups(CNN_REPLY);

  // 只选中 A：填入“我选 A：...”
  assert.equal(
    buildAnswerMessage(groups, { 0: "A" }, {}),
    "我选 A：应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）",
  );

  // 选中 A 并补充说明：补充内容追加在括号里
  assert.equal(
    buildAnswerMessage(groups, { 0: "A" }, { 0: "已有 CIFAR-10" }),
    "我选 A：应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）（补充：已有 CIFAR-10）",
  );

  // 未选择但写了补充：作为该组补充提交
  assert.equal(buildAnswerMessage(groups, {}, { 0: "想先聊聊" }), "第 1 组补充：想先聊聊");

  // 什么都没选也没补充：不产生提交内容
  assert.equal(buildAnswerMessage(groups, {}, {}), "");
});

test("切换选中状态：再次点击同一选项取消选中", () => {
  assert.equal(toggleOptionKey(undefined, "B"), "B");
  assert.equal(toggleOptionKey("A", "B"), "B");
  assert.equal(toggleOptionKey("B", "B"), "");
});

/**
 * 本轮交互目标：
 *   一个问题 -> 问题下方 2~4 个可点击选项 -> 点选项只把内容填入底部输入框
 *   -> 用户可编辑或补充 -> 只有底部全局“发送”按钮负责提交。
 */
test("点击选项只把内容填入底部输入框（draft），不产生任何发送动作", () => {
  const [group] = parseOptionGroups(CNN_REPLY);
  const option = group.options[0];

  // 点击 A 得到的只是一段“草稿文本”，用于写入底部输入框
  const draft = buildOptionFillText(option, "");
  assert.equal(typeof draft, "string");
  assert.equal(
    draft,
    "我选 A：应用层：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）",
  );

  // 补充说明只是拼进同一段草稿，仍然不是一次发送
  assert.equal(
    buildOptionFillText(option, "已有 CIFAR-10"),
    `${draft}（补充：已有 CIFAR-10）`,
  );

  // 草稿是普通字符串，用户可以继续编辑改写
  assert.equal(
    draft.replace("应用层", "工程落地"),
    "我选 A：工程落地：用 CNN 做某个具体任务（请说明是什么任务、有没有数据）",
  );

  // 没有选中任何选项时不产生草稿，调用方保持自由输入
  assert.equal(buildOptionFillText(null, ""), "");
  assert.equal(buildOptionFillText(undefined, "   "), "");
});

test("ResearchOptionSelector 失去全部发送能力：只保留填充输入框", () => {
  const selector_source = readComponentSource(
    "../components/research/ResearchOptionSelector.tsx",
  );

  // 组件不再接收 onSend —— 类型层面就没有发送出口，重新加回会直接被 tsc 拒绝
  assert.ok(
    !selector_source.includes("onSend"),
    "选项组件不应再持有 onSend：点击选项不得发送请求",
  );
  // 组件不得直接触发既有发送链路
  assert.ok(
    !/handleSend/.test(selector_source),
    "选项组件不应调用 handleSend",
  );
  // 页面上的“提交选择”按钮已删除：提交只由底部全局发送按钮负责
  assert.ok(
    !selector_source.includes("提交选择"),
    "选项组件不应再渲染“提交选择”按钮",
  );
  // 删掉发送入口后，点击选项仍然把回答写入输入框
  assert.ok(
    selector_source.includes("onFillInput"),
    "点击选项必须仍能填充底部输入框",
  );
});

test("会话把选项组件只接到 setDraft，提交仍由全局发送按钮负责", () => {
  const conversation_source = readComponentSource(
    "../components/research/ResearchConversation.tsx",
  );
  const usage = conversation_source.split("<ResearchOptionSelector", 2)[1].split("/>", 1)[0];

  // 选项组只接线到输入框草稿
  assert.ok(usage.includes("onFillInput={(text) => setDraft(text)}"));
  assert.ok(!usage.includes("onSend"), "挂载选项组时不得传入发送回调");
  // 底部全局发送按钮仍然调用原有发送链路
  assert.ok(conversation_source.includes("void handleSend(draft)"));
});

test("重试完成路径与实时流式路径共用同一映射，结构化字段同样不丢", () => {
  const reply = {
    id: "assistant-retry",
    content: CNN_REPLY,
    created_at: "2026-09-10T00:00:00Z",
    next_question: QUESTION_1,
    suggested_answers: ["应用层：做具体任务", "方法层：改进结构"],
  };

  const retried = buildAssistantConversationMessage(reply);
  const streamed = buildAssistantConversationMessage(reply);

  // 两条路径产出完全一致，重试不会把字段清空
  assert.deepEqual(retried, streamed);
  assert.equal(retried.next_question, QUESTION_1);
  assert.deepEqual(retried.suggested_answers, ["应用层：做具体任务", "方法层：改进结构"]);
  // 重试回来的选项同样可点选
  assert.notEqual(buildStructuredOptionGroup(retried), null);
});

test("失败路径不构造助手消息，因此失败时不会渲染任何伪造选项", () => {
  const conversation_source = readComponentSource(
    "../components/research/ResearchConversation.tsx",
  );
  // 只看 handleRetry 函数体，避免匹配到顶部 import 里的同名符号
  const retry_block = conversation_source
    .split("async function handleRetry", 2)[1]
    .split("} finally {", 1)[0];

  // 只有 completed 且带 reply_message 才追加消息；failed 分支只记录错误
  assert.ok(retry_block.includes('response.status === "completed" && response.reply_message'));
  assert.ok(retry_block.includes('response.status === "failed"'));
  // 失败分支里不得存在任何追加 assistant 消息的写法
  const failed_branch = retry_block.split('response.status === "failed"', 2)[1];
  assert.ok(!failed_branch.includes("buildAssistantConversationMessage"));
});
