# 编程语言练习扩展方案

## 1. 目标与范围

在保留现有 Python 练习、题目判定、学习记录、AI 反馈和 API 兼容性的前提下，把可练习语言抽象为“语言包（Language Package）”。后续新增语言只增加语言包和对应运行时适配，不复制一套编译器业务流程。

本阶段只确定需求、边界和实施路径，不改变现有运行逻辑。语言范围采用“能力可用即启用”的策略：目标覆盖当前常用语言，但不会把“所有语言”作为一次性发布条件，也不会启用运行时镜像中未经过隔离验证的语言。

## 2. 当前基线

- 在线编译器位于 `src/code_navi/online_compiler/`，当前应用层只接受 `language=python`。
- Piston 是独立执行服务；服务端固定 Python 3.12 版本，并由服务端持有源码、输入、时间、CPU、内存和输出限制。
- 题目版本当前强制 `language=python`，题目包含 starter source、公开/隐藏测试和精确归一化比较。
- 前端练习页和 `frontend/lib/api/compiler.ts` 目前直接面向 Python；默认行为必须保持不变。
- 当前 Piston 本地原型使用 privileged 容器，生产代码执行服务仍需独立完成隔离验证；新增语言不能放宽这一安全边界。

## 3. Phase 0 决策冻结

以下决策在进入编码阶段前固定；后续若改变 SQL 方言、批次或稳定语言 ID，需要先更新本文档并重新评估兼容性和隔离边界。

- **SQL 执行后端**：SQLite。使用 Python 标准库 `sqlite3`，不新增 DuckDB 依赖；每次请求使用隔离的内存或临时数据库，禁止连接 Code Navi 业务数据库。
- **首批语言**：Python、C、C++、Java、JavaScript。
- **第二批语言**：Go、Rust、C#、Kotlin、PHP、Ruby、Swift、TypeScript。第二批只表示产品顺序，不表示 runtime 已安装或通过隔离验收。
- **目标环境**：Windows 本地开发宿主 + Docker 本地原型。Piston 继续由 Docker Desktop/Compose 提供；`compose.web.yaml` 当前不接入 Piston，本阶段不把多语言执行描述为 Web 容器或生产能力。
- **稳定语言 ID**：`python`、`c`、`cpp`、`java`、`javascript`、`go`、`rust`、`sql`。其中 `cpp` 映射到 Piston runtime `c++`；浏览器只提交稳定 ID，不能提交 Piston ID、别名、版本或源文件名。

### 3.1 Piston 核验状态

仓库固定 Piston 镜像为 `ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a`。runtime 不随镜像预装，而是由部署流程安装到 `code-navi-piston-packages` volume；因此镜像 digest 本身不能证明某个 runtime 已安装。

2026-08-09 先对 `http://127.0.0.1:2000/api/v2/packages` 和 `/api/v2/runtimes` 做了只读核验；随后按用户明确授权启动固定 digest 的 Piston，并保留既有 `code-navi-piston-packages` volume。`/packages` 提供首批所需的精确 package：`python=3.12.0`、`gcc=10.2.0`、`java=15.0.2`、`node=20.11.1`（目录见 [Piston 官方包目录](https://github.com/engineer-man/piston/tree/master/packages)）；`python=3.12.0` 在安装前已存在，`java=15.0.2` 与 `node=20.11.1` 安装成功并在 `/runtimes` 核验，`gcc=10.2.0` 的安装请求（含一次 600 秒等待）超时，当前仍未安装。未安装 GCC 导致 C/C++ 暂标记为 `unavailable`；本阶段未以真实执行样例替代 live 隔离验收。

### 3.2 首批 Piston runtime 矩阵

| 稳定 ID | Piston package | Piston runtime ID | 精确版本 | Piston runtime aliases | 服务端源文件名 | 本机状态 |
| --- | --- | --- | --- | --- | --- | --- |
| `python` | `python` | `python` | `3.12.0` | `py`、`py3`、`python3`、`python3.12` | `main.py` | 已安装并通过 ID/版本/别名核验 |
| `c` | `gcc` | `c` | `10.2.0` | `gcc`（目标 aliases，未因安装超时在本机核验） | `main.c` | package 可见；安装请求超时，runtime 未安装 |
| `cpp` | `gcc` | `c++` | `10.2.0` | `cpp`、`g++`（目标 aliases，未因安装超时在本机核验） | `main.cpp` | package 可见；安装请求超时，runtime 未安装 |
| `java` | `java` | `java` | `15.0.2` | 无（实测为空数组） | `Main.java` | 已安装并通过 ID/版本/别名核验 |
| `javascript` | `node` | `javascript` | `20.11.1` | `node-javascript`、`node-js`、`javascript`、`js` | `main.js` | 已安装并通过 ID/版本/别名核验 |

`sourceFile` 是 Code Navi 服务端语言包契约，不是浏览器可覆盖的 Piston 参数。C 与 C++ 共享 `gcc=10.2.0` package，但必须分别匹配 runtime ID `c` 与 `c++`；不得因为 package 已安装就假定两个 runtime 都通过隔离验收。

### 3.3 `GET /api/v1/compiler/languages` 响应契约

顶层最终只返回以下字段：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `schemaVersion` | string | 固定为 `compiler-languages.v1` |
| `defaultLanguageId` | string | 固定为 `python` |
| `languages` | array | 按产品顺序返回语言能力；未知字段按向前兼容方式忽略 |

每个 `languages[]` 条目最终只返回以下字段：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `id` | string | Code Navi 稳定语言 ID |
| `displayName` | string | UI 展示名 |
| `aliases` | string[] | 服务端接受的稳定产品别名，不直接透传或动态扩展 Piston aliases |
| `mode` | `piston` \| `sql` | 受控执行后端 |
| `status` | `enabled` \| `unavailable` \| `planned` | `enabled` 只由精确 runtime capability check 和语言开关共同产生 |
| `runtimeId` | string \| null | Piston runtime ID；SQL 和尚未固定 runtime 的 planned 语言为 `null` |
| `runtimeVersion` | string \| null | 精确版本；不得返回范围、`latest` 或自动选择结果 |
| `sourceFile` | string | 服务端固定源文件名 |
| `fileExtension` | string | 含前导点的文件扩展名 |
| `editorLanguage` | string | 前端编辑器模式标识，不是执行参数 |

该接口不返回或接受编译命令、运行命令、参数、入口路径、网络、CPU、内存、文件、进程和输出限制。现有 `GET /api/v1/compiler/runtime` 继续承担 Python 基线状态与服务端限制兼容响应；`/languages` 只做能力发现，不执行代码、不安装 runtime，也不因名称相近而替换版本。

## 4. 语言包契约

每个语言包由服务端注册，浏览器只能选择服务端返回的能力，不能提交编译命令、参数、runtime 版本或文件路径。内部至少包含：

| 字段 | 用途 |
| --- | --- |
| `id`、`displayName`、`aliases` | 稳定标识、展示名称和兼容旧别名 |
| `mode` | `piston`、`sql` 或后续受控执行后端 |
| `runtimeId`、`runtimeVersion` | Piston runtime 或专用引擎的固定版本 |
| `sourceFile`、`fileExtension`、`entrypoint` | 文件名、扩展名和入口约束 |
| `compile/run` 策略 | 由服务端内置，不能由用户覆盖 |
| `limits` | 源码、输入、墙钟、CPU、内存、进程、文件和输出限制 |
| `status` | `enabled`、`planned`、`unavailable`，用于能力发现 |
| starter/test adapter | 起始模板、输入输出约定和题目判题适配 |

语言包应是不可变配置或只读注册表；运行时探测只决定是否可用，不得自动选择相近版本或静默升级。

## 5. 目标语言矩阵

第一版按执行后端拆分，不把 SQL 强行当作普通 Piston 语言：

| 分组 | 语言 | 首选执行方式 | 主要约束 |
| --- | --- | --- | --- |
| 保持兼容 | Python | Piston `python=3.12.0` | 继续作为默认语言，现有请求和响应不变 |
| 首批编译型 | C、C++ | Piston `gcc=10.2.0` 提供的 `c`、`c++` runtime | 编译参数、标准版本和源文件名由语言包固定 |
| 首批编译/运行型 | Java | Piston `java=15.0.2` | 入口类名、文件名、classpath 和版本必须由适配器控制 |
| 首批解释型 | JavaScript | Piston `node=20.11.1` 提供的 `javascript` runtime | 禁止任意 npm 安装和网络依赖 |
| 第二批工具链型 | Go | 后续固定的 Piston runtime | 禁止外部模块下载；编译缓存和构建目录必须隔离 |
| 第二批 | Rust、C#、Kotlin、PHP、Ruby、Swift、TypeScript | 后续固定的 Piston runtime | 逐语言确定精确版本并通过隔离测试后才可启用；TypeScript 禁止任意 npm 安装 |
| 独立后端 | SQL | Python 标准库 SQLite 临时数据库 | 仅使用内存/临时库和服务端 fixture，禁止连接真实数据库 |

“所有当下常用语言”作为长期产品目标拆解为可审计的语言包清单。每次启用新语言都要记录 runtime、版本、命令策略、资源限制和测试结果；未满足条件的语言显示为未安装或规划中，而不是让用户看到一个必然失败的选项。

## 6. 目标架构与执行路径

1. **语言目录层**：新增语言包模型、别名规范化和能力目录；保留 `language` 字段，默认仍为 `python`。增加只读的语言能力接口，供前端和管理端发现已启用语言。
2. **应用层路由**：`CompilerApplication` 只负责校验公共请求、选择语言包、调用执行后端和生成稳定响应；不把用户输入拼接成 shell 命令。
3. **执行适配层**：把语言包转换成受控的 Piston payload。Piston 客户端从“只执行 Python”扩展为“按服务端语言包执行”，但继续统一返回编译错误、运行错误、超时、输出超限和服务错误。
4. **SQL 适配层**：使用 Python 标准库 `sqlite3` 创建单次请求临时数据库和服务端 fixture，执行只读或白名单 SQLite SQL；明确结果排序、NULL、浮点和错误信息的比较规则。SQL 不通过 Piston，也不连接应用数据库。
5. **题目模型层**：把题目描述、测试语义与语言实现分开。一个题目可关联多个语言版本，每个语言版本拥有 starter source、入口约定和相同语义的测试；旧 Python 题目数据继续可读。
6. **前端能力层**：语言选择器读取服务端能力目录，Python 作为默认值；编辑器语言模式、模板、提交 payload 和错误提示由语言包元数据驱动，不能继续散落硬编码。
7. **记录与反馈层**：在学习记录和 AI 上下文中以附加字段记录 `languageId`、runtime 和版本；既有记录和既有 Python 响应保持可读取。AI 只能解释执行事实，不能改变判题结果。

## 7. 分阶段实施

### Phase 0：需求基线（当前）

完成本文档，冻结兼容性规则、首批 runtime 安装目标、SQLite 后端、批次、稳定 ID 和目标环境；不修改现有代码。本机固定 digest 的 Piston 已启动，Python、Java、JavaScript 已安装并通过 `/packages`、`/runtimes` 的 ID/版本/别名核验；GCC 安装受外部包安装超时阻塞，C/C++ 保持 `unavailable`。逐语言执行与隔离 live 测试仍是进入编码阶段后的独立门禁。

### Phase 1：语言包基础设施

实现语言包模型、目录、别名规范化和 capability API；为 Python 建立等价语言包，先通过现有 Python 回归测试，再逐步切换内部调用。此阶段不得改变旧 API 的默认值和返回字段。

### Phase 2：通用 Piston 语言

优先接入 C、C++、Java、JavaScript。每种语言分别固定文件名、入口、编译/运行策略和 runtime 版本；完善 mock 测试后，再在显式 live 环境验证实际 runtime。

### Phase 3：扩展工具链

根据 Piston 的真实能力接入 Go、Rust、C#、Kotlin、PHP、Ruby、Swift、TypeScript。每种语言先单独固定 runtime 和版本，再使用独立开关、独立验收；某个 runtime 缺失不得影响其他语言或 Python。

### Phase 4：SQL 练习

使用已冻结的 SQLite 方言，增加临时库、fixture、查询结果归一化、资源限制和 SQL 注入/文件访问测试，再接入题库和前端。

### Phase 5：题库与产品体验

为每个语言包补充 starter source、基础题和隐藏测试；前端增加语言选择、模板切换和能力不可用提示；补充学习记录、筛选和运营所需的语言维度。

## 8. 向后兼容规则

- `POST /api/v1/compiler/execute` 继续接受未带语言或带 `language=python` 的旧请求。
- 旧客户端不需要升级即可继续运行 Python；Python 仍是默认语言和默认题库语言。
- 旧题目版本、隐藏测试、判题 verdict、记录查询和 AI 票据不改变语义。
- 新字段采用可选、追加方式；练习记录继续使用独立 SQLite，由编译器模块执行向前兼容的本地 schema 升级，不直接使用共享 Alembic。禁止删除或重命名现有字段。
- 客户端不能扩大 runtime、命令、参数、网络、文件、进程或资源限制。

## 9. 冲突风险与缓解

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| Piston runtime 不完整或版本漂移 | 某语言启动失败、不同环境结果不一致 | 固定 runtime 版本，启动时 capability check，未安装则禁用；不自动升级 |
| 编译型语言入口差异 | Java 类名、C/C++ 编译参数等导致模板或判题失败 | 每种语言独立 adapter 和契约测试，命令只存在服务端 |
| SQL 与程序语言执行模型不同 | 不能复用 stdin/stdout 或普通 Piston 逻辑 | 独立 SQL backend、明确方言和结果规范化，不触碰真实 DB |
| 安全边界扩大 | 编译器可访问网络、宿主文件或凭据 | 保持禁网、临时工作区、资源限制和最小权限；新增语言重新跑 live 隔离测试 |
| 前后端字段不一致 | 旧页面无法执行或错误展示 | 能力目录作为单一来源，保留旧字段，先做 API/前端契约测试 |
| 题目语义在不同语言中不一致 | 同一道题出现语言特有答案或误判 | 共享测试语义，语言包只负责模板/入口；必要时按语言声明输入输出适配器 |
| runtime 安装导致启动变慢或镜像膨胀 | 本地 Docker 启动失败、磁盘和缓存压力增加 | 分层镜像或按需安装但只允许固定清单；记录启动耗时和磁盘预算 |
| 失败归因错误 | 编译器故障被显示为学生代码错误 | 保留结构化执行状态，区分 compile/runtime/timeout/service_error，AI 不参与归因 |
| 多人同时改动现有 Python 链路 | 回归或合并冲突 | 先抽象契约，再逐语言增量提交；每个阶段保留 Python 回归门禁 |

## 10. 测试与验收门槛

- 单元测试：语言 ID/别名、版本选择、语言包校验、payload 生成、文件名和入口规则。
- 应用测试：Python 旧请求全量回归；不支持或未安装语言不得调用执行器；客户端字段不能覆盖服务端限制。
- Piston mock 测试：分别覆盖编译错误、运行错误、超时、输出超限、服务不可用和异常响应。
- Live 测试：每种已启用语言至少执行成功样例、编译失败样例、超时/输出限制样例，并验证禁网、工作区清理、仓库和凭据不可见。
- SQL 测试：临时库隔离、fixture 重置、只读/危险语句拦截、结果排序与 NULL 规则、超时和大结果集限制。
- 前端测试：能力列表、默认 Python、语言切换、不可用提示和旧练习流程。
- 发布前继续执行项目规定的 `ruff check .`、`pytest` 和构建检查；live 执行器测试必须显式启用，不让普通离线测试依赖 Docker。

## 11. 本阶段完成定义

本分支当前阶段只要求：需求范围、语言包契约、SQLite 后端、语言批次、稳定 ID、首批 runtime 安装目标、`/languages` 字段、目标环境、分阶段路径、兼容性规则、风险和验收门槛明确；不改变 Python 代码路径或现有 API 行为。固定 digest 的本地 Piston 已启动；Python、Java、JavaScript 已安装并完成 package/runtime 元数据核验，GCC 安装超时使 C/C++ 保持 `unavailable`；代码执行和隔离 live 测试不在本阶段宣称完成。

## 12. 文件级开发清单

以下路径以当前仓库结构为准。Phase 1 先完成基础抽象和 Python 等价迁移，后续语言按同一契约增量开发。

### 12.1 需要修改的现有文件

| 文件 | 修改目的 | 修改方式与边界 |
| --- | --- | --- |
| `src/code_navi/online_compiler/application.py` | 让应用层按语言包选择执行器 | 将 `language == "python"` 的硬编码校验改为注册表查找；保留无语言请求默认 Python；执行、提交、runtime 状态继续返回现有字段，并新增可选语言元数据 |
| `src/code_navi/online_compiler/piston.py` | 从 Python 专用客户端扩展为通用 Piston 执行客户端 | 新增按 `LanguagePackage` 构造 payload 的通用方法；保留 `execute_python()` 兼容包装器；禁止客户端传入命令、版本和资源限制；统一编译/运行结果归一化 |
| `src/code_navi/online_compiler/judging.py` | 让服务端题目判定支持不同语言实现 | 将 `ExecutionRunner.execute_python()` 抽象为受控 `execute()`；保留旧调用适配；判题比较、隐藏测试脱敏和 verdict 优先级不变 |
| `src/code_navi/online_compiler/problems/models.py` | 解除题目版本只能是 Python 的限制 | 将 `language` 校验改为语言包 ID 校验；保持现有 Python `ProblemVersion` 可反序列化；不在模型中保存用户命令或 runtime 参数 |
| `src/code_navi/online_compiler/problems/catalog.py` | 维护默认题目与语言实现的兼容关系 | 保留全部现有 Python 题目常量；新增语言版本时引用语言包模板，避免复制测试语义；首批语言题目单独增量加入 |
| `src/code_navi/online_compiler/router.py` | 暴露语言能力发现接口 | 增加只读 `GET /api/v1/compiler/languages`；保留 `/runtime`、`/execute`、`/submit` 等现有路径和状态码；路由只转发，不承载语言命令逻辑 |
| `src/code_navi/online_compiler/config.py` | 配置启用语言和固定 runtime | 增加启用语言清单、各语言固定版本、SQL 限制等服务端配置；环境变量只能选择已声明配置，不能动态注入任意 runtime |
| `src/code_navi/online_compiler/runtime_setup.py` | 部署阶段安装并验证固定 runtime | 将单一 Python 安装改为遍历受控 runtime 清单；逐项检查 package 可用性和精确版本；失败时只禁用对应语言，Python 基线失败仍按当前流程阻止启动 |
| `src/code_navi/online_compiler/learning_records.py` | 记录练习所用语言而不破坏历史记录 | 增加可空 `language_id`、`runtime_id`、`runtime_version` 字段；独立 SQLite 表由编译器模块执行幂等、向前兼容的 schema 升级并补默认值，不创建 Alembic revision；现有查询响应字段保留不变，新字段追加输出 |
| `src/code_navi/online_compiler/ai_evaluation.py` | 让反馈上下文识别语言 | 将固定 Python 元数据替换为执行结果中的语言包信息；保持 AI 不能修改执行结果、判题结果和隐藏测试；旧 Python 反馈格式不变 |
| `frontend/lib/api/compiler.ts` | 建立前端语言能力和通用执行 API | 增加 `CompilerLanguage`、`fetchCompilerLanguages()`、通用 `executeCode()`、`submitCode()`；保留 `executePython()`、`submitPython()` 作为旧页面和旧调用的兼容包装器 |
| `frontend/app/(student)/practice/page.tsx` | 让练习页面由语言能力驱动 | 增加语言列表加载、默认 Python、语言切换、模板切换和不可用提示；逐步移除执行流程中的 Python 硬编码；旧题目进入页面时仍选择 Python，不改变原有交互 |
| `compose.yaml` | 让本地 Piston 具备明确的语言 runtime | 只增加受控 runtime 安装变量或 setup 参数；保持 loopback、禁网、进程/文件/内存/输出限制；不能因扩展语言取消现有安全检查 |
| `dev-start.cmd` | 让 Windows 本地入口准备首批 runtime | 将“准备 Python runtime”改为调用统一 setup；输出每个语言的 enabled/unavailable 状态；Python 失败仍提示原有修复方式，其他语言失败不能误报整个服务不可用 |
| `docs/deployment/local.md` | 记录本地 runtime 安装与验证方式 | 明确首批语言、镜像缓存、启动耗时、磁盘需求和 live 测试命令；说明哪些语言因 runtime 未安装而不可用 |
| `docs/deployment/production.md`、`docs/development/high-risk-capabilities.md` | 更新生产安全准入条件 | 增加多语言执行必须逐语言验证的要求；继续禁止生产直接依赖 privileged 原型、网络访问、宿主文件和凭据读取 |

### 12.2 需要新增的核心文件

| 文件 | 新增目的 | 主要内容 |
| --- | --- | --- |
| `src/code_navi/online_compiler/languages/__init__.py` | 建立语言包边界 | 只导出公共模型、注册表和默认目录，不让上层依赖具体编译命令 |
| `src/code_navi/online_compiler/languages/models.py` | 定义不可变语言包契约 | `LanguagePackage`、`RuntimeRequirement`、`ExecutionMode`、入口/文件/限制/能力状态等类型和校验 |
| `src/code_navi/online_compiler/languages/registry.py` | 统一注册、别名规范化和能力筛选 | 根据稳定 ID 查找语言包；用 Piston runtime 列表计算 enabled/unavailable；拒绝未知别名和静默版本替换 |
| `src/code_navi/online_compiler/languages/piston_adapter.py` | 封装程序语言到 Piston 的转换 | 根据包元数据生成服务端 payload；处理文件名、编译入口和运行入口；不执行用户提供的 shell 字符串 |
| `src/code_navi/online_compiler/languages/sql_adapter.py` | 提供 SQL 独立执行后端 | 临时 SQLite、fixture 初始化、只读策略、结果归一化、超时和危险语句拦截；不连接 Code Navi 数据库 |
| `src/code_navi/online_compiler/languages/builtin.py` | 注册首批内置语言包 | Python、C、C++、Java、JavaScript 固定元数据；第二批语言另行增量声明，每个 runtime 版本显式声明 |
| `src/code_navi/online_compiler/languages/manifest.py` | 为部署和审计提供机器可读清单 | 输出语言 ID、runtime、版本、模式和启用状态；作为 runtime setup、API 和前端能力数据的共同来源 |
| `src/code_navi/online_compiler/problems/language_versions.py` | 存放跨语言题目实现 | 将题目语义与各语言 starter source、入口约定分开，避免继续扩大 `catalog.py` 的单文件体积 |

练习记录当前不属于共享 SQLAlchemy Base，`COMPILER_DATABASE_PATH` 指向由编译器模块自主管理的独立 SQLite。练习记录的 schema 由编译器模块执行幂等、向前兼容的本地升级，不直接使用 Alembic；因此本功能不新增 `migrations/` 或 Alembic revision。只有未来先通过单独架构决策把练习记录迁入共享业务数据库后，才适用共享 Alembic 流程；`dev-start.cmd` 的业务库迁移步骤不迁移练习记录。

### 12.3 需要新增的测试文件

| 文件 | 验证目的 |
| --- | --- |
| `tests/online_compiler/test_languages.py` | 语言包模型、别名、固定版本、能力状态和非法配置 |
| `tests/online_compiler/test_language_registry.py` | runtime 探测、注册表筛选、未知语言拒绝和 Python 默认兼容 |
| `tests/online_compiler/test_piston_languages.py` | C/C++/Java/JavaScript/Go/Rust payload、文件名、编译/运行阶段和错误映射 |
| `tests/online_compiler/test_sql_adapter.py` | SQL 临时库、fixture、只读限制、结果归一化、超时和数据库隔离 |
| `tests/online_compiler/test_language_api.py` | `/languages` 能力接口、旧 `/runtime` 响应、旧执行请求和不支持语言的状态码 |
| `tests/online_compiler/test_learning_records_languages.py` | 旧独立 SQLite 记录读取、新记录语言字段和编译器自管 schema 升级兼容 |
| `tests/online_compiler/test_piston_live_languages.py` | 显式 live 环境逐语言执行和隔离边界；普通测试默认跳过 |

现有 `test_application.py`、`test_compiler_api.py`、`test_piston.py`、`test_submit.py` 不删除，继续增加 Python 回归断言。只有在通用接口稳定后，才把 Fake Gateway 从 `execute_python()` 迁移到同时支持两者的测试替身。

## 13. 具体修改顺序

### 第 0 步：基线冻结

1. 在 `feat/code-practice-languages` 上确认当前工作区干净且不在 `main`。
2. 记录当前 Python API 示例、`/runtime` 响应、题目 verdict、学习记录结构和本地 Piston runtime。
3. 固定 SQL 使用 Python 标准库 SQLite，不引入 DuckDB。
4. 固定首批为 Python、C、C++、Java、JavaScript；第二批为 Go、Rust、C#、Kotlin、PHP、Ruby、Swift、TypeScript，未验收语言标记 `unavailable` 或 `planned`。

### 第 1 步：先建契约，不切换旧流程

1. 新增 `languages/models.py`、`registry.py`、`builtin.py` 和对应单元测试。
2. 把 Python 现有配置映射成一个等价语言包，但暂时不改变 `CompilerApplication` 的真实执行路径。
3. 新增 `/languages` 的 mock API 测试，只读返回能力，不影响 `/runtime`。
4. 通过 `ruff check .` 和语言包单元测试后再继续。

### 第 2 步：抽象 Piston，同时保留 Python 包装器

1. 在 `piston.py` 增加通用 `execute()` 和按包构造 payload 的函数。
2. 保留 `execute_python()`，内部调用通用逻辑；现有测试替身和旧调用先不改。
3. 在 `judging.py` 增加通用 runner 调用，但保留 Python 兼容入口。
4. 先只让 Python 走新路径，比较新旧响应和异常分类；回归通过后再开放 C/C++。

### 第 3 步：接入 C/C++/Java/JavaScript

每种语言都按同一小循环实施：新增语言包 → mock payload 测试 → runtime setup 清单 → Piston live 成功/失败/限制测试 → API 能力开启 → 前端模板接入。任何一种语言失败只回退该语言状态，不回退 Python 或关闭整个编译器。

Java 额外先统一入口类名和 `main` 文件名；C/C++ 先固定标准版本和无网络编译参数；JavaScript 禁止 npm 下载；这些规则在 adapter 测试中固化。

### 第 4 步：扩展题目模型和判题

1. 先让 `ProblemVersion.language` 接受已注册语言 ID。
2. 为一条现有简单题新增 C/C++/Java 版本，使用相同输入输出测试语义。
3. 验证公开测试输出、隐藏测试脱敏、错误分类和 verdict 与 Python 语义一致。
4. 再把语言实现移入 `problems/language_versions.py`，避免一次性重写既有目录。

### 第 5 步：接入 SQL

1. 先完成 SQL adapter 的单元测试和临时数据库清理。
2. 只开放 SQLite 方言，定义列名、排序、NULL 和浮点比较规则。
3. 不复用 Piston 的源码文件和命令字段，不允许 `ATTACH`、扩展加载、外部文件、网络函数或真实数据库连接。
4. 先提供独立 SQL 题目，再考虑与程序语言题目共享题目 ID；SQL 失败不影响 Piston 语言。

### 第 6 步：迁移前端和记录

1. `compiler.ts` 新增通用 API，同时保留 Python wrapper。
2. 练习页先加载 `/languages`，加载失败时按当前行为显示 Python runtime 错误，不伪造语言列表。
3. 语言切换只改变编辑器模式、模板和请求中的 `language`，不会改变服务端限制。
4. 语言记录字段采用编译器模块自管的 additive SQLite schema 升级；先验证旧库读取和幂等升级，再写入新字段，不创建 Alembic revision。

### 第 7 步：部署、回归与发布

1. 更新 `runtime_setup.py`、`compose.yaml` 和 `dev-start.cmd`，按固定清单安装并验证 runtime。
2. 本地执行离线单元/API 测试，再启动 Piston 执行显式 live 测试。
3. 运行 `ruff check .`、`pytest`、前端 lint/build 和 `python -m build`。
4. 检查 Docker 日志、runtime 列表、API 能力列表、旧 Python 题目和新语言样例。
5. 每一阶段单独提交；代码审核通过后再决定是否 push，当前不自动上传或创建 PR。

## 14. 兼容风险分级

| 等级 | 风险 | 合并门槛 |
| --- | --- | --- |
| P0 | Python 默认请求、现有题目判定、隐藏测试或学习记录被破坏 | 立即停止合并，先恢复 Python 回归 |
| P0 | 新语言可访问宿主文件、网络、凭据或真实数据库 | 禁止启用，必须修复并完成 live 隔离验证 |
| P1 | 新语言 runtime 缺失、版本漂移或编译命令不一致 | 该语言保持 unavailable，不影响其他语言 |
| P1 | 前后端能力字段不一致、旧客户端无法解析响应 | 保持旧字段，新增字段可选，并补 API 契约测试 |
| P2 | 模板体验、错误文案或语言编辑器模式不完整 | 不影响服务端安全和判题时可分阶段修复 |

## 15. 进入编码阶段的最终检查

只有以下条件全部满足，才从文档阶段进入 Phase 1 编码：

1. 启动目标固定 digest 的本地 Piston 后，只读 `/api/v2/packages` 能列出第 3.2 节全部精确 package；本阶段已核验 Python、Java、JavaScript 的 runtime ID、精确版本和 aliases，GCC 安装超时使 C/C++ 的 runtime 核验待补，逐语言执行隔离仍需 live 测试。
2. SQL 方言和执行后端已固定为 Python 标准库 SQLite，且没有任何真实数据库访问需求。
3. `/languages` 的响应字段、旧 `/runtime` 兼容策略和 `language` ID 命名已确定。
4. Python 回归门禁、live 隔离门禁和新增语言独立开关已写成测试要求。
5. Docker runtime 安装耗时、磁盘预算和失败回退策略已确认。
6. 每个实现提交只包含一个可验证阶段，避免把语言目录、题库、前端和部署一次性混成不可回滚的大提交。
