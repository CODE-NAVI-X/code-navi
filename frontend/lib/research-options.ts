/**
 * 科研对话选择题的解析与作答文案构造（纯函数）。
 *
 * 背景：姜姜的回复正文本身就把 A/B/C/D 写成静态列表，组件又解析出同一组选项
 * 渲染成独立的“快速作答”卡片，于是同一题目会同时出现两份 A/B/C/D。
 *
 * 因此这里同时提供两件事：
 * 1. `parseOptionGroups` 解析出真正需要用户作答的选项组，并保留各选项在原文中的行下标；
 * 2. `splitMessageSegments` 依据这些行下标把整条消息切成**顺序明确**的片段，
 *    让交互选项正好落在对应题干下方（而不是被挤到整条消息末尾），
 *    同时把这些静态行从 markdown 片段里摘掉，保证同一题目的选项只出现一份。
 */

export interface ParsedOption {
  key: string;
  text: string;
  fillValue?: string;
}

export interface ParsedOptionGroup {
  title?: string;
  options: ParsedOption[];
  /** 该组选项在原文中的行下标（0 起），用于从正文里摘掉这些静态行。 */
  lineIndexes: number[];
}

/** 明确的字母标号选项（A. / · A. / - **A.** / A、 / A： 等），严格限定 A-G，不匹配纯数字序号。 */
const LETTER_OPTION_LINE =
  /^(?:[-*•·+]\s*)?(?:\*\*)?([A-Ga-g])(?:\*\*)?\s*(?:端)?[.、：:\s]\s*(.+)$/;

/** 决策拍板分支（如“· 如果纳入：...” / “· 如果跳过：...”等待拍板事项）。 */
export const BRANCH_LINE =
  /^(?:[-*•·+]\s*)?(?:\*\*)?(如果(?:纳入|跳过|保留|暂缓|增加|减少|采用|执行|同意|不同意|是|否)|(?:方案|选项|路径|分支)[一二三四1234ABC]|纳入|跳过|保留|暂缓)(?:\*\*)?[：:]\s*(.+)$/;

/**
 * 解析姜姜回复中真正需要用户作答的选项：
 * 1. 明确的字母标号选项（A. / · A. / - **A.** / A、 / A： 等）；
 * 2. 决策分支（如“· 如果纳入：...” / “· 如果跳过：...”等待拍板事项）；
 * 3. 计划/执行阶段的确认提问（如“四、计划确认：如果你确认无误...对计划有任何调整需求...”）；
 * 4. 严格排除正文中的普通数字执行步骤（1. / 2. / 3.）与限制说明条目。
 */
export function parseOptionGroups(content: string): ParsedOptionGroup[] {
  const entries = content
    .split(/\r?\n/)
    .map((raw, index) => ({ index, text: raw.trim() }))
    .filter((entry) => Boolean(entry.text));

  const groups: ParsedOptionGroup[] = [];

  // --- 模式 1：明确字母标号选择题 ---
  let pendingLetter: ParsedOption[] = [];
  let pendingLetterIndexes: number[] = [];
  let pendingLetterTitle: string | undefined = undefined;
  let lastNonOptionLine: string | undefined = undefined;

  const flushLetter = () => {
    if (pendingLetter.length >= 2) {
      groups.push({
        title: pendingLetterTitle,
        options: pendingLetter,
        lineIndexes: pendingLetterIndexes,
      });
    }
    pendingLetter = [];
    pendingLetterIndexes = [];
    pendingLetterTitle = undefined;
  };

  for (const entry of entries) {
    const match = LETTER_OPTION_LINE.exec(entry.text);
    if (match) {
      const rawKey = match[1].trim().toUpperCase();
      const rawText = match[2].trim().replace(/^\*\*(.*?)\*\*/, "$1");
      if (/^[A-G]$/.test(rawKey)) {
        if (pendingLetter.length === 0 && lastNonOptionLine) {
          pendingLetterTitle = lastNonOptionLine.replace(/^[#*·•\s->]+/, "").trim();
        }
        pendingLetter.push({
          key: rawKey,
          text: rawText,
          fillValue: `我选 ${rawKey}：${rawText}`,
        });
        pendingLetterIndexes.push(entry.index);
        continue;
      }
    }
    flushLetter();
    lastNonOptionLine = entry.text;
  }
  flushLetter();

  // --- 模式 2：决策拍板分支 ---
  let pendingBranch: ParsedOption[] = [];
  let pendingBranchIndexes: number[] = [];
  let pendingBranchTitle: string | undefined = undefined;
  let lastNonBranchLine: string | undefined = undefined;

  const flushBranch = () => {
    if (pendingBranch.length >= 2) {
      groups.push({
        title: pendingBranchTitle || "拍板决策事项",
        options: pendingBranch,
        lineIndexes: pendingBranchIndexes,
      });
    }
    pendingBranch = [];
    pendingBranchIndexes = [];
    pendingBranchTitle = undefined;
  };

  for (const entry of entries) {
    const branchMatch = BRANCH_LINE.exec(entry.text);
    if (branchMatch) {
      const branchTag = branchMatch[1].trim();
      const branchDesc = branchMatch[2].trim();
      if (pendingBranch.length === 0 && lastNonBranchLine) {
        pendingBranchTitle = lastNonBranchLine.replace(/^[#*·•\s->]+/, "").trim();
      }
      const charKey = String.fromCharCode(65 + pendingBranch.length); // A, B, C...
      pendingBranch.push({
        key: charKey,
        text: `${branchTag}：${branchDesc}`,
        fillValue: `我选择【${branchTag}】：${branchDesc}`,
      });
      pendingBranchIndexes.push(entry.index);
      continue;
    }
    flushBranch();
    lastNonBranchLine = entry.text;
  }
  flushBranch();

  // --- 模式 3：计划确认 / 阶段执行确认 ---
  if (groups.length === 0) {
    const tailContent = content.slice(-600);
    const isPlanConfirmation =
      /(?:计划确认|需要你确认的事项|确认计划|执行确认|方案确认)/i.test(tailContent) &&
      /(?:确认无误.*(?:进入|开始)|对计划有任何调整需求.*开始执行|如果你确认|确认后，我们开始执行)/i.test(tailContent);

    if (isPlanConfirmation) {
      groups.push({
        title: "计划执行确认",
        options: [
          {
            key: "A",
            text: "确认无误，正式开始执行",
            fillValue: "计划已经确认无误，我们可以正式进入 Day 1 的执行阶段！",
          },
          {
            key: "B",
            text: "我需要微调计划（时间/范围/环境）",
            fillValue: "我对计划有一些微调需求：",
          },
        ],
        lineIndexes: [],
      });
    }
  }

  return groups;
}

/**
 * 一条 assistant Markdown 消息渲染顺序上的一段。
 * - `markdown`：交给 MarkdownText 渲染的正文；
 * - `options`：交给 ResearchOptionSelector 渲染的交互选项组。
 */
export type MessageSegment =
  | { kind: "markdown"; content: string }
  | { kind: "options"; group: ParsedOptionGroup; groupIndex: number };

/**
 * 按原文顺序把一条消息切成 markdown 与选项组交替的片段。
 *
 * 这一步是为了修正“选项被挂到整条消息末尾”的顺序错误：当消息写成
 *
 *     问题 1 ... / A. ... B. ... / 问题 2 ...
 *
 * 时，必须渲染成「问题 1 题干 -> 交互选项 -> 问题 2 题干」，
 * 而不是「问题 1 题干 -> 问题 2 题干 -> 交互选项」。
 *
 * 规则：
 * 1. 被选项组接管的那几行从 markdown 片段里摘掉，避免同一题目出现两份选项；
 * 2. 选项组落在本组第一行在原文中的位置，因此正好贴在对应题干下方；
 * 3. 没有原文行的虚拟选项组（如“计划执行确认”）没有可定位的位置，
 *    按其原有合理行为追加到消息末尾。
 */
export function splitMessageSegments(
  content: string,
  structured: ParsedOptionGroup | null = null,
): MessageSegment[] {
  const base = buildBaseSegments(content);
  if (!structured) return base;

  // 结构化字段是唯一可靠来源：正文里解析出的文本选项组一律丢弃，
  // 避免“结构化选项 + 正文 A/B/C/D”同时渲染出两份。
  const markdownOnly = base.filter(
    (segment): segment is Extract<MessageSegment, { kind: "markdown" }> =>
      segment.kind === "markdown" && segment.content.trim().length > 0,
  );

  // 插到承载该题干的那段正文之后，这样选项正好落在对应问题下方。
  const question = (structured.title ?? "").trim();
  let insertAt = markdownOnly.length;
  if (question) {
    const found = markdownOnly.findIndex((segment) => segment.content.includes(question));
    if (found >= 0) insertAt = found + 1;
  }

  const segments: MessageSegment[] = [...markdownOnly];
  segments.splice(insertAt, 0, {
    kind: "options",
    group: structured,
    groupIndex: 0,
  });
  return segments;
}

function buildBaseSegments(content: string): MessageSegment[] {
  const groups = parseOptionGroups(content);
  if (groups.length === 0) return [{ kind: "markdown", content }];

  const lines = content.split(/\r?\n/);
  const consumed = new Set<number>();
  /** 本组第一行在原文中的下标 -> 该组。 */
  const anchorToGroup = new Map<number, number>();

  groups.forEach((group, groupIndex) => {
    if (group.lineIndexes.length === 0) return;
    for (const index of group.lineIndexes) consumed.add(index);
    const anchor = Math.min(...group.lineIndexes);
    if (!anchorToGroup.has(anchor)) anchorToGroup.set(anchor, groupIndex);
  });

  const segments: MessageSegment[] = [];
  let buffer: string[] = [];

  const flushMarkdown = () => {
    const text = buffer.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    if (text) segments.push({ kind: "markdown", content: text });
    buffer = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const groupIndex = anchorToGroup.get(index);
    if (groupIndex !== undefined) {
      flushMarkdown();
      segments.push({ kind: "options", group: groups[groupIndex], groupIndex });
      continue;
    }
    if (consumed.has(index)) continue;
    buffer.push(lines[index]);
  }
  flushMarkdown();

  // 虚拟选项组（没有可定位的原文行）追加在末尾，保持既有行为。
  groups.forEach((group, groupIndex) => {
    if (group.lineIndexes.length > 0) return;
    segments.push({ kind: "options", group, groupIndex });
  });

  return segments;
}

/** 建议答案至少要有 2 条才值得渲染成可点选选项；只有 1 条时保持自由输入。 */
export const MIN_SUGGESTED_ANSWERS = 2;

/** 后端结构化澄清契约：一道待答问题 + 若干条建议答案。 */
export interface SuggestedAnswersSource {
  next_question?: string | null;
  suggested_answers?: readonly string[] | null;
}

/**
 * 把结构化的 `next_question` / `suggested_answers` 转成可渲染的选项组。
 *
 * 这是**唯一可靠来源**：不再要求模型在正文里恰好写出 A/B/C/D。
 * 不满足条件时返回 `null`，调用方应保持自由输入，绝不伪造候选。
 */
export function buildStructuredOptionGroup(
  source: SuggestedAnswersSource,
): ParsedOptionGroup | null {
  const title = (source.next_question ?? "").trim();
  if (!title) return null;

  const answers = (source.suggested_answers ?? [])
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  if (answers.length < MIN_SUGGESTED_ANSWERS) return null;

  return {
    title,
    options: answers.map((text, index) => {
      const key = String.fromCharCode(65 + index);
      return { key, text, fillValue: `我选 ${key}：${text}` };
    }),
    // 结构化选项没有对应的正文行可摘除。
    lineIndexes: [],
  };
}

/** 编排器返回的 assistant 回复（可用字段子集，便于流式/重试/历史复用）。 */
export interface AssistantReplyLike extends SuggestedAnswersSource {
  id: string;
  content: string;
  created_at: string;
}

/** 与 `ResearchConversationMessage` 结构兼容的 assistant 消息。 */
export interface AssistantConversationMessage {
  message_id: string;
  role: "assistant";
  content: string;
  created_at: string;
  generation_mode: "agent";
  run_id: null;
  event_count: number;
  intent: null;
  next_question: string | null;
  suggested_answers: string[];
  candidate_questions: string[];
  recommended_action: null;
}

/**
 * 把编排器回复映射成前端消息。
 *
 * 实时流式完成、重试完成、历史恢复三条路径共用这一个映射，
 * 因此 `next_question` / `suggested_answers` 不会被某一层硬编码清空。
 */
export function buildAssistantConversationMessage(
  reply: AssistantReplyLike,
): AssistantConversationMessage {
  return {
    message_id: reply.id,
    role: "assistant",
    content: reply.content,
    created_at: reply.created_at,
    generation_mode: "agent",
    run_id: null,
    event_count: 1,
    intent: null,
    next_question: reply.next_question ?? null,
    suggested_answers: [...(reply.suggested_answers ?? [])],
    candidate_questions: [],
    recommended_action: null,
  };
}

/** 再次点击同一选项即取消选中。 */
export function toggleOptionKey(current: string | undefined, key: string): string {
  return current === key ? "" : key;
}

/**
 * 点击选项（或编辑补充说明）后应写入页面底部输入框的草稿文本。
 *
 * 这是选项组**唯一**的作答出口：只产出一段可继续编辑的草稿交给 `setDraft`，
 * 不发送任何请求、不触发任何发送链路。用户确认后由页面底部的全局“发送”按钮提交。
 * 没有选中项时返回空串，调用方应保持自由输入。
 */
export function buildOptionFillText(
  option: ParsedOption | null | undefined,
  supplement = "",
): string {
  if (!option) return "";
  const base = option.fillValue || `我选 ${option.key}：${option.text}`;
  const extra = supplement.trim();
  return extra ? `${base}（补充：${extra}）` : base;
}

/**
 * 把当前选中项与补充说明组合成发送给姜姜的用户消息。
 * 未选中任何项时返回空串，调用方据此禁用提交。
 */
export function buildAnswerMessage(
  groups: ParsedOptionGroup[],
  selected: Record<number, string>,
  supplements: Record<number, string>,
): string {
  const lines: string[] = [];
  groups.forEach((group, index) => {
    const chosen = group.options.find((option) => option.key === selected[index]);
    const supplement = (supplements[index] ?? "").trim();
    if (chosen) {
      const baseFill = chosen.fillValue || `我选 ${chosen.key}：${chosen.text}`;
      lines.push(`${baseFill}${supplement ? `（补充：${supplement}）` : ""}`);
    } else if (supplement) {
      lines.push(`第 ${index + 1} 组补充：${supplement}`);
    }
  });
  return lines.join("\n");
}
