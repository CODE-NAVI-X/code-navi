# CodeNavi 平台功能优化与演示冲刺任务清单（按人分工与顶端设计输入）

> **基准演示节点**：2026-09-14（冲刺倒计时 1 周）  
> **统一学术主题**：**深度学习与卷积神经网络（CNN，以经典 ResNet 实际任务应用为核心）**  
> **演示战略方针**：**“以固定 CNN 演示路径防翻车，以极简直观 UI 显价值，以真实功能修复保底线”**  
> **使用说明**：本文档整理了 2026-09-07 会议纪要与最新排障反馈，作为下发给各专职 Agent 进行顶端设计与编码落地的统一规格输入文件（List Spec）。

---

## 目录与职责分配矩阵

| 模块 | 核心工作方向 | 责任人 | 目标交付物 |
| :--- | :--- | :--- | :--- |
| **模块一** | 学习端与导航栏改造 (Stepper改造 / 笔记入口重构 / 诊断客观题裁剪) | **苏育**、**夏俊杰** | Stepper 5步闭环、展开学习笔记按钮、诊断客观题裁剪 |
| **模块二** | 学情画像系统顶端设计与重构 (动态雷达图 / 知识图谱 / 缺口下钻 / 自主管理) | **lizhikeer（梓柯）** | 多维能力雷达图、知识缺口下钻详情、画像记录删除管理 |
| **模块三** | 动手实践与项目代码导航 (Issue #114 修复 / .py上传限制 / 代码挖空保留) | **张锦怡** | Issue #114 修复、.py 上传约束、code_fill 体验保留 |
| **模块四** | 科研模块深度排障与演进 (红线防误判 / 论文卡片去重 / 快捷选项 / 阶段大按钮) | **陈盛漳** | 解决红线拦截报错、推荐卡片去重、下一步大按钮、检索分词 |
| **模块五** | 全局通用底座与演示固化 (KaTeX 公式全链路渲染 / CNN 演示数据种子预置) | **全体协同** | 统一 Markdown+KaTeX 渲染、CNN 演示固定剧本 |

---

## 模块一：学习端与导航栏改造（责任人：苏育、夏俊杰）

### 1.1 流程导航栏（Stepper）重构（图一需求落地）
- **问题现状**：
  - 当前 [LearningFlowStepper.tsx:L33-L82](file:///E:/codenavi/frontend/components/learning/LearningFlowStepper.tsx#L33-L82) 定义了 6 步：`1 理解 > 2 检查 > 3 动手实践 > 4 复盘 > 5 笔记 > 6 科研引导`；
  - 第 2 步“检查”文案生硬，容易误导学生为代码语法检查或作业打勾；
  - 第 5 步“笔记”是一个贯穿全局的工具属性，硬塞入线性主流程中，导致主流程冗长，且打乱了从“4 复盘”到“6 科研引导”的承接关系。
- **改进设计**：
  1. **步骤名称优化**：将第 2 步更名为**「学情诊断」**（或「诊断测试」/「理解检验」），明确该环节为答题产生初始画像的诊断性评价；
  2. **主流程剥离笔记项**：从主流程 Stepper 中移除“5 笔记”，精简为**标准 5 步学习闭环**：
     ```text
     1 理解 ──> 2 学情诊断 ──> 3 动手实践 ──> 4 复盘 ──> 5 科研引导
     ```
- **涉及文件**：
  - [LearningFlowStepper.tsx:L16-L82](file:///E:/codenavi/frontend/components/learning/LearningFlowStepper.tsx#L16-L82)

### 1.2 “展开学习笔记”常驻入口重构（图一需求落地）
- **问题现状**：
  - 目前顶部工作区提示区（[WorkspaceContextBar.tsx:L104-L108](file:///E:/codenavi/frontend/components/WorkspaceContextBar.tsx#L104-L108)）显示为一段无交互的静态灰字：*“独立 Learning：解析会保存至个人工作区，但不关联 Task。”*；
  - 学生在做题、看讲义或复盘时无法随时展开笔记，且左侧栏“学习笔记”入口孤立。
- **改进设计**：
  1. **文字替换为功能按钮**：在 `WorkspaceContextBar.tsx` 中彻底删除该提示文字，原位置替换为醒目的**「展开学习笔记」**按钮（带 `<ClipboardList />` 图标）；
  2. **全局抽屉联动**：点击该按钮即可在当前页面右侧滑出轻量笔记抽屉面板（内嵌 `StructuredNotebook.tsx`），支持全屏与任意学习步骤下边学边记；
  3. **左侧栏联动**：左侧导航栏的“学习笔记”同步优化，支持直接触发抽屉或跳转独立笔记本页面。
- **涉及文件**：
  - [WorkspaceContextBar.tsx:L98-L109](file:///E:/codenavi/frontend/components/WorkspaceContextBar.tsx#L98-L109)
  - [AppShell.tsx:L30-L45](file:///E:/codenavi/frontend/components/AppShell.tsx#L30-L45)
  - [StructuredNotebook.tsx](file:///E:/codenavi/frontend/components/learning/StructuredNotebook.tsx)

### 1.3 诊断测试题型精准裁剪与多维画像数据保障
- **问题现状与明确裁决**：
  - **仅裁剪“学习诊断中的纯文字填空题”**：自然语言填空输入容易导致学生乱填，产生大量数据噪音导致画像误判，因此诊断测试不使用纯文本填空；
  - **单选题及其他多维度客观题型予以完整保留**：诊断性测试必须保留单选题、判断题等多维度客观题型，以便为后续 lizhikeer 的画像系统提供丰富的多维度评估数据（如概念辨析、计算推理、结构识别等）。
- **改进设计**：
  1. 修改 `quiz/prompts.py`，禁用纯自然语言 `fill_blank` 题目生成；
  2. 确保选择题生成聚焦于 CNN 核心概念（卷积核作用、感受野、池化层特征、通道数变化等），保证自动批改 100% 确定且准确。
- **涉及文件**：
  - [quiz/prompts.py:L20-L57](file:///E:/codenavi/src/code_navi/learning/quiz/prompts.py#L20-L57)
  - `src/code_navi/learning/quiz/services.py`
  - [QuizView.tsx](file:///E:/codenavi/frontend/components/learning/QuizView.tsx)

---

## 模块二：学情画像系统顶端设计与重构（责任人：lizhikeer 梓柯）

> **说明**：本模块由 **lizhikeer** 亲自负责后续顶端设计，以下为其核心设计输入规格与必达能力。

### 2.1 前端动态多维能力雷达图与知识图谱设计
- **需求规格**：
  1. **多维能力动态雷达图**：
     - 在复盘页开发前端动态交互雷达图（基于 ECharts / Chart.js 或轻量原生 SVG）；
     - 围绕 CNN 学习设定 5 大能力维度：
       - `① 基础概念`（卷积、激活函数、池化原理）；
       - `② 网络架构`（ResNet 残差块、跨层连接、网络深度退化问题）；
       - `③ 参数计算`（权重参数量、特征图尺寸演变、感受野推导）；
       - `④ 工程实战`（PyTorch 搭建、训练循环、损失与优化器）；
       - `⑤ 科研迁移`（经典骨干网络在下游实际任务中的选型与改造）。
     - 每个维度根据答题与实践表现动态计算得分与评级。
  2. **动态知识图谱/知识树简易视图**：
     - 直观呈现前置依赖与进阶路径（如：线性代数/矩阵运算 -> 卷积层原理 -> ResNet 残差结构 -> 图像分类科研实战）。

### 2.2 复盘知识缺口支持点击下钻（查看错题与掌握度）
- **需求规格**：
  1. **缺口列表可交互下钻**：在复盘页面中的“复盘知识缺口”区域，每一个薄弱知识点（如“ResNet 残差块跳跃连接计算”）支持**点击展开或弹窗浮层**；
  2. **弹窗内容要求**：
     - 显示关联的错题题干、学生的错误选择 vs 正确参考答案；
     - 显示大模型对该题的深度考点解析；
     - 明确标出该知识点的当前掌握程度（如：*掌握度 40% · 处于理解巩固期*）；
     - 提供直接行动建议（如：`[去动手实践此代码]` 或 `[将该点带入科研提问]`）。

### 2.3 画像记录主动管理能力
- **需求规格**：
  - 赋予学生自主管理权：在画像详情页中，支持学生对误操作或偶然猜错导致的记录进行**自行删除 / 标记重置**；
  - 点击“移除该次记录”后，前端乐观更新，后端从 `learning_profile` 软删除或标记归档，重新实时计算雷达图与弱项分布。

### 2.4 界面文案极简化与专业感重塑
- **需求规格**：
  - 彻底清理界面中原有的开发期技术词汇：删除“两套画像与跨板块桥接一次呈现”、“主要分布载体”、“样本不足不编造虚假百分比”；
  - 移除大批杂乱的高亮彩色框（`bg-amber-50`、`bg-rose-50`），重构成干净、现代、专业的学情分析报告排版。
- **涉及文件**：
  - [portrait/page.tsx](file:///E:/codenavi/frontend/app/(student)/learning/portrait/page.tsx)
  - `frontend/app/(student)/portrait/page.tsx`
  - `src/code_navi/portraits/service.py`
  - `src/code_navi/learning_profile/service.py`

---

## 模块三：动手实践与项目代码导航（责任人：张锦怡）

### 3.1 修复 Issue #114：上传项目后左侧文件/大纲点击无反应，右侧不显示代码
- **Issue 来源**：[Issue #114 · CODE-NAVI-X/code-navi](https://github.com/CODE-NAVI-X/code-navi/issues/114)
- **问题现状**：
  - 学生在代码实践页面上传项目后，左侧生成的项目文件目录树及代码大纲符号无法点击，或者点击后右侧编辑器处于空白，无法渲染代码内容。
- **改进设计**：
  1. **排查前端事件绑定**：检查项目文件树组件的 `onSelectFile` / `onSelectSymbol` 事件回调，确保选定文件后将其文本内容同步推送给右侧 Monaco/代码高亮视图；
  2. **后端文件解析返回完整性**：检查代码分析接口是否只返回了 AST 符号摘要而漏掉了文件正文 payload；
  3. **空态与加载态保护**：在切换文件时增加 Loading 状态与平滑过渡，确保演示点击立即显示对应 Python 代码。
- **涉及文件**：
  - [learning/practice/page.tsx](file:///E:/codenavi/frontend/app/(student)/learning/practice/page.tsx)
  - `frontend/app/(student)/practice/page.tsx`
  - [practice/router.py](file:///E:/codenavi/src/code_navi/practice/router.py)
  - `src/code_navi/online_compiler/`

### 3.2 项目代码上传格式严格限制：仅限 `.py`，彻底排除 `.json`/`.csv`
- **问题现状**：
  - 当前上传控件 `accept` 中包含了 `.json`、`.csv`、`.docx`、`.pdf`，学生若误上传数据集，导致后端 AST 解析器崩溃并报 500。
- **改进设计**：
  1. **前端控件限制**：`accept` 严格限制为 `.py,text/x-python`；
  2. **文案警示**：上传区域增加说明：“仅支持 `.py` 源代码文件；严禁上传 `.json`/`.csv` 等数据集文件”；
  3. **前端拦截**：检测到非法扩展名立即弹出 Toast 阻断，不发起网络请求；
  4. **后端白名单校验**：`practice/service.py` 校验文件名后缀及文件前 1024 字节内容，非法格式返回 `400 Bad Request`。
- **涉及文件**：
  - [learning/practice/page.tsx:L1104](file:///E:/codenavi/frontend/app/(student)/learning/practice/page.tsx#L1104)
  - [practice/router.py](file:///E:/codenavi/src/code_navi/practice/router.py) 与 `service.py`

### 3.3 保留并优化代码挖空填空（`code_fill`）体验
- **明确决策**：
  - 区别于学习端的自然语言填空，**动手实践模块的代码挖空填空（`code_fill`）予以完整保留**！
- **优化要求**：
  - 为 CNN 演示主题设计一段 ResNet 核心残差块（`BasicBlock`）的代码挖空：例如挖空 `self.conv1` 卷积步长参数、`stride` 与 `downsample` 残差连接相加代码；
  - 保证挖空判分（规则/LLM）流畅反馈，填入正确代码后给予精准提示。

---

## 模块四：科研模块深度排障与演进（责任人：陈盛漳）

### 4.1 修复红线过度拦截 Bug（重大阻断：误报“复现成功”导致会话崩溃）
- **真实故障现场（图二触发案例）**：
  - 用户输入：“用现有 CNN（如 ResNet）去解决某个实际问题，没有现成的数据集，有一张5060ti”；
  - 系统报错崩溃并弹出红字：
    ```text
    本次思考未成功完成
    Jiang Jiang output boundary validation failure: Output contains ungrounded affirmative reproduction success claim: 复现成功（你的输入已完整保留，阶段未发生变更）。
    ```
- **根因深度剖析**：
  - 位于 [conversation_prompt_templates.py:L1011](file:///E:/codenavi/src/code_navi/research/conversation_prompt_templates.py#L1011) 的 `_contains_ungrounded_reproduction_success_claim`；
  - 当模型生成：“在没有现成数据集且仅有一张 5060ti 的条件下，我们暂不能保证**复现成功**，需要分阶段验证...” 或类似客观讨论时，正则匹配到了“复现成功”四个字，但上下文的前置否定/条件判断前缀未完全覆盖该句型，导致判定逻辑误报为“未经证实的肯定性复现成功断言”，直接将整轮有效对话丢弃拦截！
- **修复方案**：
  1. **细化语义断言判定**：必须区分“肯定性断言（例如：我们已经复现成功了）”与“否定性/假设性探讨（例如：为了能够复现成功/暂不能断言复现成功/能否复现成功取决于...）”；
  2. **容错重试而非直接崩溃**：当触发安全边界拦截时，优先要求模型按规范重写，而非直接把报错红字展示给用户导致流程卡死。
- **涉及文件**：
  - [conversation_prompt_templates.py:L573-L630, L1011](file:///E:/codenavi/src/code_navi/research/conversation_prompt_templates.py#L573-L630)
  - `src/code_navi/research/conversation_agent.py`

### 4.2 修复精选论文推荐卡片每轮对话重复刷屏 Bug
- **问题现状**：
  - 进入论文检索后，`searchCandidates`（5 篇候选卡片）在每一次对话的气泡下方都会重新渲染一遍；
  - 即使学生已经明确点击了某篇论文并完成选择，这 5 张卡片依然顽固地悬挂在底部，严重遮挡最新对话。
- **修复方案**：
  1. **增加状态销毁与收拢逻辑**：在 `ResearchConversation.tsx` 中增加判定：当 `papers.current_paper` 已存在（即用户已完成论文选定），或者对话进入下一阶段时，`searchCandidates` 自动隐藏；
  2. **选定后折叠收录**：选定后仅以单行提示形式收录在折叠栏或右侧上下文卡片中，聊天主瀑布流区恢复清爽。
- **涉及文件**：
  - [ResearchConversation.tsx:L601-L613](file:///E:/codenavi/frontend/components/research/ResearchConversation.tsx#L601-L613)

### 4.3 修复快捷选项卡（选择题卡片）提取展示（图二场景落地）
- **问题现状（图二场景）**：
  - 姜姜追问两个关键问题（问题一：运行环境与显卡，如个人电脑/5060ti/服务器；问题二：时间投入，如两周/一个月）；
  - 正常预期应该在下方浮出可点击的快捷选择胶囊（如 `[5060ti (16G)]`、`[实验室服务器]`、`[2周完成]`、`[1个月]`），让演示者一键点击填入；
  - 但当前由于 `ResearchOptionSelector` 仅匹配严格的 `A.`、`B.` 格式，导致此类自由问答完全没有快捷选项卡。
- **修复方案**：
  1. **增强选项卡模式识别**：扩充 `ResearchOptionSelector`，支持识别 `• 选项内容` 或括号内的备选枚举；
  2. **针对 CNN 演示剧本定制选项提取**：当进入资源澄清轮次时，稳定向前端输出带有快捷填入标签的 Action Buttons。
- **涉及文件**：
  - [ResearchConversation.tsx:L615-L627](file:///E:/codenavi/frontend/components/research/ResearchConversation.tsx#L615-L627)
  - `frontend/components/research/ResearchOptionSelector.tsx`

### 4.4 阶段推进显式大按钮（一键开展研究）
- **需求规格**：
  - 当当前阶段条件达成（如需求明确完成、研究计划生成完毕、或论文选定完成），在对话框正下方或输入栏正上方弹出一个显眼的 Primary 大按钮；
  - 按钮文案示例：**`[ 确认计划并开展研究 → ]`** 或 **`[ 选定论文并开始精读 → ]`**；
  - 点击大按钮后，自动向后台发送确认意图并触发阶段跃迁，演示无需人工紧张输入文字。
- **涉及文件**：
  - [ResearchConversation.tsx](file:///E:/codenavi/frontend/components/research/ResearchConversation.tsx)
  - [conversation_orchestrator.py](file:///E:/codenavi/src/code_navi/research/conversation_orchestrator.py)

### 4.5 论文检索中文分词与双语检索词提取（根治“中国人口”无关文献）
- **问题根因**：
  - [academic.py:L613-L614](file:///E:/codenavi/src/code_navi/research/academic.py#L613-L614) 正则 `[a-z0-9]+` 过滤了全部汉字，导致中文查询完全无法匹配词频，排序退化为乱序；
- **修复方案**：
  1. 引入中文字符与 2-gram 分词支持；
  2. 针对 CNN 检索词自动提取中英文双语对照（如：“卷积神经网络图像分类/缺陷检测” -> `CNN image classification`, `ResNet surface defect detection`）；
  3. 设定 70% 相似度硬门禁，不满足条件的文献自动丢弃，确保输出的 5 篇文献真实且高度切题。
- **涉及文件**：
  - [academic.py:L613-L615](file:///E:/codenavi/src/code_navi/research/academic.py#L613-L615)
  - [conversation_search_service.py](file:///E:/codenavi/src/code_navi/research/conversation_search_service.py)

### 4.6 CNN 主题固定演示剧本与数据固化
- **战略要求**：
  - 不走随机跳步，而是把 CNN（ResNet 图像分类/缺陷检测）作为固定黄金路径；
  - 预先在本地数据库固化好该主题的候选文献包、精读蓝图和代码模板，确保演示全程零网络抖动、零输出幻觉。

---

## 模块五：全局通用底座与公式渲染（全体协同）

### 5.1 数学公式 KaTeX 全链路渲染修复
- **问题现状**：
  - 学习端选择题、解析、科研对话（`MarkdownText.tsx`）及讲义（`SlideRenderer.tsx`）中，部分公式显示为原始乱码或代码未渲染。
- **改进设计**：
  1. 封装通用的 `MathMarkdown` 组件，基于 `katex` 统一支持：
     - 行内公式：`$ ... $` 与 `\( ... \)`；
     - 独立公式块：`$$ ... $$` 与 `\[ ... \]`；
  2. 后端统一 Prompt 约束：严禁输出遗留的 HTML 标签或 OMML 格式，一律采用标准 LaTeX 语法输出数学公式。
- **涉及文件**：
  - [QuizView.tsx](file:///E:/codenavi/frontend/components/learning/QuizView.tsx)
  - [MarkdownText.tsx](file:///E:/codenavi/frontend/components/research/MarkdownText.tsx)
  - [SlideRenderer.tsx](file:///E:/codenavi/frontend/components/learning/presentation/SlideRenderer.tsx)

---

## 冲刺执行计划表（按人对接与验收）

| 时间窗口 | 责任人 | 关键落地目标 |
| :--- | :--- | :--- |
| **Day 1 ~ Day 2** | **陈盛漳**<br>**张锦怡** | 1. 修复科研端红线拦截误报（解除“复现成功”阻塞，4.1）<br>2. 修复 Issue #114（项目代码导航左侧点击无反应，3.1）<br>3. 修复代码上传 `.py` 约束，阻断 `.json`/`.csv` (3.2)<br>4. 修复论文检索中文分词与双语关键词 (4.5) |
| **Day 3 ~ Day 4** | **苏育**<br>**夏俊杰**<br>**陈盛漳** | 1. 改造 Stepper（“检查”更名为学情诊断，剥离笔记项为5步，1.1）<br>2. 上线顶部“展开学习笔记”常驻按钮 (1.2)<br>3. 诊断测试剔除纯文本填空，保留多维客观题 (1.3)<br>4. 科研端去除论文卡片重复刷屏 (4.2)，增加阶段推进大按钮 (4.4) |
| **Day 5** | **lizhikeer**<br>**全体协同** | 1. **lizhikeer** 交付学情画像系统顶端设计并落地多维雷达图/知识缺口下钻详情 (模块二)<br>2. 全链路贯通 CNN（ResNet 图像分类）演示固定剧本与数据种子注入 (4.6) |
| **Day 6 ~ Day 7** | **全体成员** | 1. 全程端到端彩排与排演走查<br>2. 锁定版本，禁止新增非验证功能，确保 09-14 演示圆满成功！ |
