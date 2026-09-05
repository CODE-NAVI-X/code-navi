# Code Navi 前端设计语言（DESIGN.md）

> **文档定位**：本文件是 Code Navi 前端唯一的设计语言源，供所有参与前端实现的模型与开发者共同遵守。
> **适用范围**：`frontend/` 全部页面与组件。架构事实（路由、API 边界、浏览器状态）仍以 [docs/architecture/frontend.md](../docs/architecture/frontend.md) 为准；两者冲突时按根 `AGENTS.md` 优先级由用户裁决。
> **依据**：D5（Issue #99）已拍板方案「Cyber-Modular Command Center（Resend 沉浸模块流 + 强化科技感）」，来源 `E:\揭榜挂帅codenavi\d5-agent-handoff.md` §一/§三 与拍板摘要；数值分歧按附录 C 裁决记录处理。
> **版本**：v1.0（2026-09-05，阶段 0 交付，待用户与 Gemini 走查终审）。

---

## 1. 设计理念与科技感原则

**风格陈述**：以模块化清晰架构为骨架，注入克制而精致的未来科技质感。汲取 Resend、Vercel 等现代工程控制台的卡片层级，结合深邃的环境微光与点阵底纹，将代码、算法训练与科研流打造成充满掌控感与专注感的「开发者学习座舱」。

**五大科技感元素**（全部以 Tailwind 原生类实现）：

| 元素 | 呈现 | 典型位置 |
| --- | --- | --- |
| 双层雷达呼吸状态灯 | 外环 `animate-ping` + 内芯圆点，双层光晕 | 顶栏 Provider/系统就绪状态 |
| 微光溢彩卡片边框 | 深色模式蓝色描边 + 柔和光晕阴影 | 核心能力卡、激活态、重点推荐卡 |
| 点阵网格科技底纹 | `.bg-grid-pattern`（深）/ `.bg-grid-pattern-light`（浅） | 主工作台大面积画布 |
| Mono 数字指标标号 | `01 // UNDERSTAND` 风格工程标签 | 能力闭环卡、进度与指标 |
| 渐变能量进度条 | 蓝→靛→翠绿渐变填充 | 掌握度、练习题集进度 |

**uiverse.io 控件灵感实现纪律**：

1. 严禁安装外部 UI 库、严禁整段复制第三方 CSS、严禁新增 NPM 依赖；
2. 全部使用 Tailwind 原生类重写；
3. 继承既有 `app-card`、`app-button-primary`、`app-button-secondary` 语义结构；
4. 代码结构明显借鉴第三方控件时，文件头部保留一行 MIT 来源注释。

**工程红线（触犯即打回）**：

1. `src/code_navi/providers.py` 永不触碰（本地有他人未提交改动，不 commit/stash/restore/修改）；
2. 正文字号 ≥ 16px：普通正文与说明文字 `text-base`，阅读区 `text-lg`；仅徽章、元信息、标签允许 `text-xs`；严禁全局压缩正文字号；
3. 色彩双模态覆盖：严格基于 Slate（浅色）与 Zinc（深色）双调色板，禁止写死硬编码的单模态色彩；
4. 离线安全字体栈：严禁引入任何外部字体 CDN（Google Fonts 等），保持系统字体栈以支持离线 NAS/Docker 构建；
5. 旧路由重定向 100% 可达：`/practice` 与 `/portrait` 的 redirect 必须有效，规范路由恒为 `/learning/practice`；
6. 科研端内部豁免：`/research` 内部组件（对话气泡、四阶段条交互、论文面板等）禁止修改代码，移动端仅允许纯 CSS 折叠次要文字；
7. 后端只读契约：不新增后端端点；聚合数据只读既有接口（如 `GET /api/v1/portraits/overview`），出题只对接既有 `POST /api/v1/practice/sets/generate-from-learning`。

---

## 2. 色彩角色与深浅双模态 Token

深浅模式切换沿用现状：`@media (prefers-color-scheme: dark)` 媒体查询，不做手动开关。所有颜色必须使用 CSS 变量或「浅色类 + 成对 `dark:` 类」两种写法之一。

### 2.1 核心 Token

| Token | 浅色模式 (Light) | 深色模式 (Dark — 科技感核心) | 角色 | 状态 |
| --- | --- | --- | --- | --- |
| `--app-surface` | `#f8fafc` (Slate-50) | `#09090b` (Zinc-950) | 主画布；叠加点阵纹理；禁止纯黑 `#000` 与纯白 `#fff` 画布 | 沿用 |
| `--app-card` | `#ffffff`（纯白浮层） | `#121215` (Zinc-900 科技黑) | 承载主要任务与数据的工作卡片 | 深色值调整 |
| `--app-card-subtle` | `#f1f5f9` (Slate-100) | `#18181b` (微亮黑灰，浅层) | 嵌套卡、代码块、输入区、参数区 | 深色值调整 |
| `--app-border` | `#e2e8f0` (Slate-200) | `rgba(255, 255, 255, 0.08)` | 1px 精细分界线，深色为极细微透白 | 深色值调整 |
| `--app-foreground` | `#0f172a` (Slate-900) | `#f4f4f5` (Zinc-100) | 正文前景 | 沿用 |
| `--app-muted` | `#475569` (Slate-600) | `#a1a1aa` (Zinc-400) | 次要说明文字 | 沿用 |
| `--app-header` | `rgba(248, 250, 252, 0.95)` | `rgba(9, 9, 11, 0.95)` | 顶栏半透明底，配 `backdrop-blur` | 沿用 |
| `--app-focus` | `#2563eb` (Blue-600) | `#3b82f6` (Blue-500) | 键盘焦点环 | 沿用 |

### 2.2 阴影与微光 Token（新增）

| Token / 类 | 浅色模式 | 深色模式 | 触发时机 |
| --- | --- | --- | --- |
| `--app-shadow-flat` | `0 1px 2px rgba(15, 23, 42, 0.04)` | `0 1px 2px rgba(0, 0, 0, 0.5)` | 默认贴地阴影 |
| `--app-shadow-lift` | `0 8px 24px rgba(15, 23, 42, 0.08)` | `0 8px 28px rgba(0, 0, 0, 0.7)` | 悬浮卡片微升（`hover:-translate-y-0.5`） |
| `.tech-border-glow` | `border-blue-200` + `shadow-[0_0_12px_rgba(37,99,235,0.06)]` | `border-blue-500/30` + `shadow-[0_0_15px_rgba(59,130,246,0.15)]` | 激活卡片、选中态、重点推荐卡（静态常驻） |
| hover 微光投影 | `0 4px 16px rgba(15, 23, 42, 0.06)` | `0 0 20px rgba(59, 130, 246, 0.12)` | 重点能力卡 Hover 瞬态光晕 |

微光纪律：科技微光只出现在 Hover 与激活重点卡，禁止全局常开；普通列表卡、表单卡不发光。

### 2.3 语义强调色

| 语义 | 用色 | 场景 |
| --- | --- | --- |
| 交互/科技强调 | 文字用 Blue-600（浅）/ Blue-500（深）；装饰图形可用 Blue-500 | Mono 标号、链接、CTA 等文字强调必须达 WCAG AA 4.5:1（浅色 Blue-600 = 5.17:1，深色 Blue-500 = 5.09:1，视觉走查第一轮收敛 2026-09-05）；焦点环、激活光晕等非文本元素 ≥ 3:1 |
| 就绪/成功 | Emerald-400 / Emerald-500 | Provider 就绪呼吸灯、进度条收尾色 |
| 降级/Mock | Amber-400 系列 | Provider 降级或 Mock 态、上下文不可用警示条 |
| 错误 | Red（沿用 `.app-status-error` 配色） | 执行失败、请求失败 |

---

## 3. 字阶与排版

**字体栈（离线安全，严禁外部 CDN）**：

- 无衬线 `--font-sans`：`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- 等宽 `--font-mono`：`ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace`

**字阶（正文 16px 为绝对红线，移动端同样不豁免）**：

| 层级 | 类 | 用途 |
| --- | --- | --- |
| 徽章/元信息 | `text-xs` (12px) | 仅限徽章、状态标签、Mono 工程标号、时间与计数元信息、管理降级区导航项 |
| 控件文本 | `text-sm` (14px) | 按钮、输入框、下拉、导航一级项 |
| 正文 | `text-base` (16px) | 所有普通正文与说明文字（body 默认，`line-height: 1.65`） |
| 阅读正文 | `text-lg` (18px) | `.reading-area`（`line-height: 1.8`） |
| 标题 | `text-xl` / `text-2xl` | 页面与区块标题 |

**Mono 排版规则**：编号、指标数字、代码、路径一律 `font-mono`；工程标号格式为 `两位数字 + " // " + 大写英文短语`，类组合 `font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500`（浅色 5.17:1 / 深色 5.09:1，达 WCAG AA；走查第一轮收敛裁决，2026-09-05）（例：`01 // UNDERSTAND`、`02 // PRACTICE`、`03 // REVIEW`）。中文标题另起一行，用 `text-base font-semibold`，不塞进标号。

---

## 4. 间距与 4px/8px 网格

1. 间距基数为 4px，常用阶梯：4 / 8 / 12 / 16 / 20 / 24；禁止任意奇数像素值。
2. 页面容器：内容区水平内距 `px-4`，`md:px-6`，`lg:px-8`；主内容最大宽度 `max-w-7xl` 居中。
3. 区块间距：主工作台各大区（Resume Hero / 能力闭环 / Action Hub）之间 `gap-6`（24px）；同区卡片之间 `gap-4`。
4. 卡片内距：标准 `p-5` 或 `p-6`；紧凑卡（嵌套、列表行）`p-3` 或 `p-4`。
5. 圆角阶梯（Tailwind 4 主题新增）：

| Token | 值 | 用途 |
| --- | --- | --- |
| `rounded-card`（`--radius-card: 1rem`） | 16px | 大卡片模块、抽屉面板 |
| `rounded-control`（`--radius-control: 0.625rem`） | 10px | 按钮、输入框、标签页、导航项 |
| `rounded-full` | — | 圆点、胶囊徽章 |

存量组件已使用的 `rounded-lg` / `rounded-xl` 在对应组件被 PR 触及时顺带迁移到新阶梯，不做全局批量替换。

---

## 5. 海拔、阴影与科技微光

海拔从低到高：画布（surface + 点阵）→ 平铺卡（flat）→ 悬浮卡（lift）→ 发光卡（tech-border-glow）。

1. 默认卡片：`--app-shadow-flat`，贴地、安静。
2. 可点击卡片：`transition-all duration-200`，Hover 时 `hover:-translate-y-0.5` + `--app-shadow-lift`；`ease-out`（浅色）/ `cubic-bezier(0.16, 1, 0.3, 1)` 柔和回弹（深色科技微动效）。
3. 激活/重点卡：叠加 `.tech-border-glow`（见 2.2）。
4. 动效约束：时长统一 `duration-200`；`prefers-reduced-motion` 下关闭 `animate-ping` / `animate-pulse`（`motion-reduce:animate-none`）；阅读区（`.reading-area`）不做任何动效。
5. 侧边栏、顶栏、抽屉阴影沿用现值（`shadow-xs` / `shadow-2xl`），不额外发光。

---

## 6. 核心组件规范

### 6.1 卡片 `app-card` / `app-card-subtle`

- 标准工作卡：`.app-card` + `rounded-card` + `p-5`/`p-6`；标题 `text-base font-semibold`，描述 `text-base text-[var(--app-muted)]`。
- 嵌套容器（代码块、输入区、参数区、骨架屏）：`.app-card-subtle`，禁止再嵌套一层 subtle。
- 可点击卡追加 `transition-all duration-200 hover:-translate-y-0.5` 与 lift 阴影；激活/重点推荐卡叠加 `.tech-border-glow`。

### 6.2 按钮与输入

- `.app-button-primary` / `.app-button-secondary` / `.app-input`：沿用 `globals.css` 既有类；组合 `rounded-control px-4 py-2 text-sm font-semibold`；Hover 提亮 `bg` 一档；禁用 `opacity-50 cursor-not-allowed`。
- 危险操作不用红色主按钮，用 secondary + `.app-status-error` 提示结果。

### 6.3 双层雷达呼吸状态灯 `.tech-pulse-dot`

```html
<span class="relative inline-flex h-2.5 w-2.5" role="status" aria-label="Provider 就绪">
  <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/80 motion-reduce:animate-none"></span>
  <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400"></span>
</span>
```

1. 颜色语义：`emerald` = 就绪（浅色外环 `/75`、内芯 `bg-emerald-500`；深色外环 `/80`、内芯 `bg-emerald-400`）；`amber` = 降级/Mock；`red` = 失败/离线。
2. 必须伴随文字标签（如 `LLM Ready`），不得仅用颜色传达状态。
3. 用于顶栏 Provider 状态与系统连通性提示，不用于普通列表行。

### 6.4 渐变能量进度条

```html
<div class="h-1.5 w-full overflow-hidden rounded-full border border-[var(--app-border)] bg-[var(--app-card-subtle)]">
  <div class="h-full rounded-full bg-gradient-to-r from-blue-600 via-indigo-500 to-emerald-400" style="width: 75%"></div>
</div>
```

用于掌握度、题集进度；进度数值必须以文字（Mono 数字）同时标示，不依赖颜色与长度传达。

### 6.5 点阵底纹

- 深色画布用 `.bg-grid-pattern`，浅色画布用 `.bg-grid-pattern-light`（两者已存在于 `globals.css`）。
- 只用于主工作台等大面积画布区域，禁止用于卡片内部与阅读区。

### 6.6 统一顶栏与侧边栏

- 顶栏职责「我在哪、我是谁」：品牌 + 面包屑（Workspace/Task 上下文，接管 `WorkspaceContextBar`）+ Provider 呼吸灯 + `AuthNav` 个人面板。**顶栏零路由项**，不与侧边栏重复。
- 侧边栏职责「去哪里」：全量一级/二级导航，结构与降级规则见附录 A。
- 导航激活态沿用现反色样式（浅色 `bg-slate-950 text-white`，深色 `bg-white text-zinc-950`）并配 `aria-current="page"`；管理降级区 `text-xs`。

---

## 7. 状态规范

| 状态 | 规范 |
| --- | --- |
| Hover | 可点击卡 lift（`-translate-y-0.5` + lift 阴影）；列表行 `bg-[var(--app-card-subtle)]`；重点能力卡附加微光投影（2.2） |
| Focus | 全局已有 `:focus-visible` 焦点环（`2px var(--app-focus)` + `offset 2px`），不得移除或覆盖 |
| 选中/激活 | 导航项反色 + `aria-current`；卡片用 `.tech-border-glow` |
| Loading | 骨架屏用 `.app-card-subtle` + `animate-pulse`；按钮内 `Loader2` 旋转；容器加 `role="status" aria-live="polite"`；加载中不得渲染为空态 |
| Empty | 每个数据区必须提供引导空态（如「快速启航：完成首次概念测验」），含至少一个主动作按钮；新用户主页绝不白屏；空与加载失败必须可区分 |
| Error | 用 `.app-status-error`；Workspace 上下文失效用 amber 警示条 + 重试/返回入口（沿用 `WorkspaceContextBar` 模式）；只显示安全公开信息；网络错误不得伪装成空结果或成功 |
| Disabled | `opacity-50` + `cursor-not-allowed`，并保留 `aria-disabled` 语义 |

---

## 8. 响应式与 390×844 移动降级

**断点**：`<768px` 为移动，`≥768px` (md) 启用桌面布局。桌面验收基准 1440×900，移动验收基准 390×844。

**桌面端**：固定侧边栏 `w-64`；统一顶栏高 `h-16`，含面包屑（`truncate` 截断）+ Provider 呼吸灯 + 个人面板。

**移动端**：

1. 顶栏折叠为紧凑型 `h-12`（现状 `h-14` 需调整），仅保留汉堡按钮、品牌、精简 AuthNav；面包屑截断。
2. 侧边栏抽屉：`w-72 max-w-[85vw]` 左滑出，`fixed inset-0 z-50` + 半透明遮罩（`bg-slate-950/60`）点击关闭，提供 X 按钮，导航点击后自动关闭；`role="dialog" aria-modal="true"`。
3. 科研端四阶段进度条：移动端用纯 CSS（`hidden sm:inline` 类）折叠次要文字，仅留指示圆点；**禁止触碰其内部状态与交互**。
4. 全站 0 横向溢出：主容器 `min-w-0` + `flex` 收缩，长文本 `truncate`，表格与代码块容器内滚动。
5. 正文字号红线移动端不豁免：正文仍 `text-base`，仅徽章/元信息/管理降级区允许 `text-xs`。

---

## 9. Do's & Don'ts

**Do**

- 优先使用语义 Token（CSS 变量）与既有 `app-*` 组件类，其次才是带成对 `dark:` 变体的 Tailwind 色类；
- 每写一个颜色，同时给出浅色与深色两种表现；
- uiverse 灵感控件用 Tailwind 原生类重写，结构明显借鉴时头部保留一行 MIT 来源注释；
- 新 Token 统一落在 `app/globals.css` 的 `:root` / `@theme` / `@layer components`；
- 组件被 PR 触及时顺带迁移到 `rounded-card` / `rounded-control` / flat-lift 阴影阶梯。

**Don't**

- 不引入 UI 组件库、外部字体 CDN 或新增 NPM 依赖；
- 不写硬编码单模态色（无 `dark:` 成对变体的色类）；
- 不把正文压到 16px 以下（移动端同样适用）；
- 不修改 `/research` 内部组件代码；
- 不新增后端端点，不绕开 `frontend/lib/api/` 直连后端；
- 不删除或弱化 `/practice`、`/portrait` 等旧路由 redirect；
- 不在大面积背景使用纯黑 `#000`（画布恒为 `#09090b`），不给普通卡片常驻发光。

---

## 附录 A：已拍板信息架构（Issue #99 Q1–Q4 裁决）

### A.1 侧边栏（管「去哪里」）

| 分组 | 条目（路由） | 说明 |
| --- | --- | --- |
| 学习闭环 | 理解与检查 (`/learning`)、动手实践 (`/learning/practice`)、**项目代码 (`/learning/projects`，新增入口)**、知识复盘 (`/learning/portrait`)、学习笔记 (`/learning/notebook`) | 核心闭环，一级分组 |
| 科研专区 | 科研引导 (`/research`) | 独立专区 |
| 组织管理（视觉降级） | 班级 (`/classes`)、账户 (`/account`) | 下沉至底部次级分区，字号 `text-xs`，弱化存在感 |

> 已裁决（2026-09-05 终审通过）：**「工作台」(`/`) 必须保留为侧边栏导航树首项**。拍板 ASCII 未绘制该项不构成移除依据：现行 `AppShell` 结构与 `docs/architecture/frontend.md` 全局入口均以工作台为顶层首选，且「品牌 Logo + 侧边栏工作台项」双通道回跳是最稳健的工程惯例。

### A.2 顶栏（管「我在哪、我是谁」，零路由项）

品牌 `[CN] Code Navi` + 面包屑（如 `算法实训营 / Task: 动态规划填空与空间优化`，接管 `WorkspaceContextBar`）｜右侧：`[● LLM Ready]` Provider 呼吸灯 + `AuthNav` 个人面板。

### A.3 工作台主页三区架构（`frontend/app/page.tsx`）

1. **继续上次（Resume Hero）**：基于 `GET /api/v1/portraits/overview`（research 块）与本地 `flow-store`，显示最近未完结练习集、学习会话或科研对话；空态展示「快速启航」新手引导卡，新用户绝不白屏。
2. **三大能力闭环（Core Capability Loop）**：`01 理解与探索` → `02 动手实践` → `03 知识复盘` 横向闭环流向卡，右上角 Mono 编号与微光悬浮态；右侧/底部配 `04 科研引导` 特色卡。
3. **待办与智能推荐（Action Hub）**：左侧为 `knowledge_gaps` 薄弱项诊断摘要 + 「一键组卷练习」（直连既有 `POST /api/v1/practice/sets/generate-from-learning`）；右侧为活跃工作区与 Task 折叠列表。

### A.4 移动端（390×844）

抽屉化侧边栏（见 §8.2）+ 紧凑顶栏 + 科研四阶段纯 CSS 折叠（见 §8.3）。

---

## 附录 B：高保真布局参考（拍板 ASCII）

### B.1 桌面端（1440×900）

```
+-------------------------------------------------------------------------------------------------------------------------+
| [CN] Code Navi    │ ◫ 算法实训营 / ◈ Task: 动态规划填空与空间优化           [● LLM Ready]          [ Alice (个人中心) v ]|
+───────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────+
|  [学习闭环]       │                                                                                                     |
|  • 理解与检查     │ ┌─ [继续上次 · RESUME HERO] ───────────────────────────────────────────────────────────────────────┐ │
|  • 动手实践       │ │ ⚡ 上次停留在：【动手实践】二叉树前序遍历 (填空题集)                                               │ │
|  • 项目代码 [新]  │ │    进度: 2/4 题 | 掌握度: 75% | 10分钟前活跃                                      [ 继续练习 -> ] │ │
|  • 知识复盘       │ └───────────────────────────────────────────────────────────────────────────────────────────────────┘ │
|  • 学习笔记       │                                                                                                     |
|                   │ ┌─ [三大能力闭环 · CAPABILITY LOOP] ────────────────────────────────────────────────────────────────┐ │
|  [科研专区]       │ │ ┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐    ┌────────────────────┐ │ │
|  • 科研引导       │ │ │ 01 // 理解与探索  │    │ 02 // 动手实践    │    │ 03 // 知识复盘    │    │ 04 // 科研引导     │ │ │
|                   │ │ │ 概念解析/代码问答 │ ─> │ 填空判题/实操验证 │ ─> │ 技能雷达/薄弱分析 │    │ 论文研读/四阶段引导│ │ │
|  [组织管理] (降级)│ │ │ [进入学习 ->]     │    │ [进入实践 ->]     │    │ [查看画像 ->]     │    │ [进入科研 ->]      │ │ │
|  • 班级成员       │ │ └───────────────────┘    └───────────────────┘    └───────────────────┘    └────────────────────┘ │ │
|  • 账户设置       │ └───────────────────────────────────────────────────────────────────────────────────────────────────┘ │
|                   │                                                                                                     │
|                   │ ┌─ [待办与智能推荐 · ACTION HUB] ────────────────────┐ ┌─ [活跃工作区与任务快速直达] ───────────────┐ │
|                   │ │ 🎯 诊断发现 2 项薄弱知识点: [递归边界] [指针空处理] │ │ • 算法训练营 (5 个进行中任务)               │ │
|                   │ │ [ 针对薄弱项一键组卷练习 (直连 POST 端点) ]        │ │ • 毕业设计代码分析 (2 个活跃任务)           │ │
|                   │ └────────────────────────────────────────────────────┘ └─────────────────────────────────────────────┘ │
+-------------------------------------------------------------------------------------------------------------------------+
```

### B.2 移动端（390×844，含抽屉化侧边栏）

```
[ 侧边栏抽屉呼出态 ]                          [ 移动端主界面 ]
+──────────────────────────+                +───────────────────────────────────+
| [CN] Code Navi       [X] |                | [三] Code Navi   [算法实训]   [U] |
| ──────────────────────── |                +───────────────────────────────────+
| 学习闭环                 |                | [继续上次]                        |
| • 01 理解与检查          |                | 二叉树填空 (2/4题)        [继续]  |
| • 02 动手实践            |                +───────────────────────────────────+
| • 03 项目代码 [新增入口] |                | [能力闭环]                        |
| • 04 知识复盘            |                | 01 理解与探索  ───────────────>   |
| • 05 学习笔记            |                | 02 动手实践    ───────────────>   |
| ──────────────────────── |                | 03 知识复盘    ───────────────>   |
| 科研专区                 |                | 04 科研引导    ───────────────>   |
| • 科研引导               |                +───────────────────────────────────+
| ──────────────────────── |                | [薄弱项推荐]                      |
| 班级 / 账户设置          |                | 发现 2 项薄弱点      [一键练习]   |
+──────────────────────────+                +───────────────────────────────────+
```

---

## 附录 C：Token 相对当前 `app/globals.css` 的落地差异清单（PR-1/PR-2 执行对照）

| # | 项 | 现状 | 拍板目标 | 动作 |
| --- | --- | --- | --- | --- |
| 1 | 深色 `--app-card` | `#18181b` | `#121215` | 调整（与 subtle 互换，刻意为之：主卡更沉、嵌套层更亮） |
| 2 | 深色 `--app-card-subtle` | `#121215` | `#18181b` | 调整（同上） |
| 3 | 深色 `--app-border` | `#27272a` | `rgba(255, 255, 255, 0.08)` | 调整为透白边界 |
| 4 | `--app-shadow-flat` / `--app-shadow-lift` | 不存在 | 见 §2.2 | 新增；`.app-card` 切换到 flat 后移除旧 `--app-shadow` 引用（过渡期保留别名） |
| 5 | `rounded-card` / `rounded-control` | 不存在 | 16px / 10px | `@theme` 新增 radius token |
| 6 | `.tech-border-glow` / `.tech-pulse-dot` | 不存在 | 见 §2.2 / §6.3 | `@layer components` 新增 |
| 7 | `.bg-grid-pattern` / `.bg-grid-pattern-light` | 已存在 | 同规范 | 无需新增，按 §6.5 约束使用 |
| 8 | 统一顶栏 | `WorkspaceContextBar` 独立条 | 合并进 AppShell 顶栏 | PR-1 内聚 |
| 9 | 移动顶栏高度 | `h-14` | `h-12` | PR-1 调整 |
| 10 | 侧边栏 `项目代码` 入口 / 管理降级区 | 无 / 无降级 | `/learning/projects`；班级、账户 `text-xs` 下沉 | PR-1 调整 |
| 11 | 数值分歧裁决 | — | hover 微光深色取 `0 0 20px rgba(59,130,246,0.12)`；`.tech-border-glow` 深色取 `0 0 15px rgba(59,130,246,0.15)` | 以两份拍板材料的 Token 表为准，摘要正文中的 18px 写法废弃 |

## 附录 D：实施顺序（已拍板路线图）

阶段 0：本 DESIGN.md（用户/Gemini 终审）→ **PR-1** `feat/d5-nav-shell`（侧边栏 IA 收敛 + 统一顶栏 + 移动抽屉）→ **PR-2** `feat/d5-workbench-home`（主页三区架构 + 科技质感注入）→ **PR-3** `docs/d5-entrypoints-table`（`docs/architecture/frontend.md` 增补入口清点表，PR 描述写明 `Closes #99`）。

质量门禁：`npm run lint`、`npx --no-install tsc --noEmit`、`npm run build`（frontend 目录）；`.venv/Scripts/python.exe -m pytest tests/ -q -k frontend`、`tests/test_learning_frontend_practice_context.py`、`tests/test_research_frontend_copy.py`；`.venv/Scripts/python.exe -m ruff check .`。
