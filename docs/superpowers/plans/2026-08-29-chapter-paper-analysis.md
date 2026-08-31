# 按论文章节分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将选定论文分析从主题列表升级为按论文原章节顺序组织的、来源受限的章节分析。

**Architecture:** 在现有 PDF 读取结果上增加确定性的章节识别与排序；DeepSeek 只接收当前章节片段和科研上下文，返回带章节标识、依据和来源范围的分析项。没有正文时保留摘要级兼容路径，并明确不可进行章节级分析。前端按章节顺序渲染折叠内容和理解检查。

**Tech Stack:** Python、Pydantic、FastAPI、Next.js、React、pytest。

---

### Task 1: 扩展章节数据契约

**Files:**
- Modify: `src/code_navi/research/conversation_schemas.py`
- Test: `tests/test_research_paper_reading.py`

- [ ] 为分析项增加可选章节标题和顺序字段，保持旧数据可读取。
- [ ] 测试章节字段可序列化并按顺序排序。

### Task 2: 实现 PDF 章节识别

**Files:**
- Modify: `src/code_navi/research/paper_reading.py`
- Test: `tests/test_research_paper_reading.py`

- [ ] 识别常见英文和中文章节标题，保留未识别正文为当前章节。
- [ ] 生成固定六类章节的可读片段，缺失章节不补造正文。

### Task 3: 章节化 DeepSeek 分析

**Files:**
- Modify: `src/code_navi/research/conversation_difficulty.py`
- Test: `tests/test_research_artifact_llm.py`

- [ ] 将章节上下文和严格输出字段加入 paper analysis prompt。
- [ ] 服务端校验章节身份、顺序和来源范围，按章节稳定排序。

### Task 4: 前端章节展示

**Files:**
- Modify: `frontend/components/research/PaperDeepAnalysisPanel.tsx`
- Test: `tests/test_research_frontend_copy.py`

- [ ] 按章节顺序分组并显示章节标题、内容和依据。
- [ ] 对摘要级分析显示正文不可用提示。

### Task 5: 验证

- [ ] 运行章节、论文分析和前端契约定向测试。
- [ ] 运行 Ruff、ESLint、TypeScript、Next build 和 `git diff --check`。
- [ ] 使用真实 DeepSeek 请求验证有 PDF 与无 PDF 两种边界。
