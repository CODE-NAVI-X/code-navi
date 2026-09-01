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

## 3. 开发前决策冻结

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

## 7. 四分支实施方案

本任务按可独立测试、独立启用和独立回滚的能力拆成四个分支。分支串行进入 `main`，后续分支从包含其前置能力的最新 `main` 创建，不建立长期堆叠分支。

| 顺序 | 分支 | 职责 | 不包含 |
| --- | --- | --- | --- |
| 1 | `feat/code-practice-foundation` | 与具体新增语言无关的后端基础、Python 等价迁移、能力接口和题库语言分区预留 | Java/JavaScript/C/C++/SQL 实际执行；任何新题目 |
| 2 | `feat/code-practice-java-javascript` | JavaScript 与 Java 执行、runtime 接线、能力启用和前端语言选择 | C/C++、SQL 和任何题目内容 |
| 3 | `feat/code-practice-c-cpp` | 共享 GCC package 的 C 与 C++ 执行、runtime 安装和隔离验证 | 其他语言和任何题目内容 |
| 4 | `feat/code-practice-sqlite` | 独立 SQLite 执行后端、能力启用和前端 SQL 运行体验 | SQL 题目、题库数据、Alembic 和业务数据库访问 |

### 7.1 `feat/code-practice-foundation`

该分支吸收当前设计文档和 Python 兼容基线测试，并完成所有跨语言共享准备：

1. 实现不可变语言包模型、注册表、稳定 ID、别名规范化、精确 runtime 匹配和能力状态。
2. 把现有 Python 配置映射为等价语言包；通用执行接口落地后保留 `execute_python()` 兼容包装器。
3. 实现只读 `GET /api/v1/compiler/languages`，保留现有 `/runtime`、`/execute`、`/submit` 行为和默认 Python。
4. 为学习记录和 AI 上下文预留语言/runtime 元数据；旧记录和旧 Python 响应继续可读。
5. 题库只建立语言分区契约：仓库键改为 `(language_id, problem_id, version)`，现有题目全部归入 `python`，旧请求缺少语言时默认 Python，禁止跨语言自动回退。
6. 当前题库是内存目录而非数据库表，因此先完成逻辑分区；同时预留未来持久化约束：题目变体的唯一键必须包含 `language_id + problem_id + version`，测试用例必须外键关联具体语言变体。
7. 为题库团队提供稳定的模型、repository 和 API 查询边界，但不创建其他语言题目、不改写题目内容、不提前建立新的题库数据库。

该分支完成时，产品仍只允许 Python 实际执行；其他语言最多以 `planned` 或 `unavailable` 出现在能力目录中。

### 7.2 `feat/code-practice-java-javascript`

在 foundation 合入 `main` 后创建。分支内按 JavaScript、Java、前端接线拆成独立提交：

1. JavaScript 固定 `javascript=20.11.1` 和 `main.js`，禁止 npm 安装与网络依赖。
2. Java 固定 `java=15.0.2` 和 `Main.java`，入口为受控的 `public class Main`，禁止 Maven/Gradle 与网络依赖。
3. 扩展 runtime setup、错误分类、能力状态和逐语言开关。
4. 前端从 `/languages` 读取 enabled 状态，增加 JavaScript/Java 编辑器模式和自由运行；不加载或创建对应题目。
5. 每种语言分别通过 mock 测试和显式 Piston live 隔离测试后才标记 `enabled`。

### 7.3 `feat/code-practice-c-cpp`

在 Java/JavaScript 分支合入后创建；如果 GCC 仍不可用，可以暂缓，不阻塞 SQLite 分支：

1. C 与 C++ 共享 `gcc=10.2.0` package，但分别匹配 runtime ID `c`、`c++`。
2. 固定 `main.c`、`main.cpp`、标准版本、编译入口和服务端资源限制。
3. GCC 安装必须幂等；安装失败时两种语言保持 `unavailable`，不得影响 Python、JavaScript 或 Java。
4. C 与 C++ 分别覆盖 payload、编译错误、运行错误、超时、输出超限和 live 隔离测试。
5. 不新增 C/C++ 题目；题库团队只消费 foundation 已提供的语言分区契约。

### 7.4 `feat/code-practice-sqlite`

该分支只依赖 foundation；若 C/C++ 受阻，可在 Java/JavaScript 后先行：

1. 使用 Python 标准库 `sqlite3` 建立每次请求隔离的内存或受控临时数据库。
2. 禁止 `ATTACH`、`DETACH`、扩展加载、外部文件、网络函数和真实业务数据库连接。
3. 固定语句数量、执行时间、返回行数和输出大小限制，并规范化列、行、NULL、浮点和错误结果。
4. 在 `/languages` 中独立报告 SQL 能力，在前端提供自由 SQL 运行和结果展示。
5. 不新增 SQL 题目，不修改题库数据，不创建 Alembic revision。

Go、Rust、C#、Kotlin、PHP、Ruby、Swift、TypeScript 不属于本轮四分支实施范围；首批完成后再根据 runtime 可用性单独规划。题库内容始终由题库团队的独立分支负责。

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
| 题库未按语言查询 | Python 题目串入其他语言列表或同名版本冲突 | foundation 将仓库键改为 `(language_id, problem_id, version)`，默认 Python 且禁止跨语言回退 |
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

## 11. 当前文档阶段完成定义

当前阶段只要求：需求范围、语言包契约、SQLite 后端、稳定 ID、`/languages` 字段、四分支职责、题库团队边界、执行顺序、兼容性规则、风险和验收门槛明确；不改变 Python 代码路径或现有 API 行为。固定 digest 的本地 Piston 已启动；Python、Java、JavaScript 已安装并完成 package/runtime 元数据核验，GCC 安装超时使 C/C++ 保持 `unavailable`；代码执行和隔离 live 测试不在本阶段宣称完成。

## 12. 文件级开发清单

以下路径以当前仓库结构为准。foundation 先完成基础抽象、Python 等价迁移和题库语言分区预留，后续三个分支按同一契约增量开发。

### 12.1 需要修改的现有文件

| 文件 | 修改目的 | 修改方式与边界 |
| --- | --- | --- |
| `src/code_navi/online_compiler/application.py` | 让应用层按语言包选择执行器 | 将 `language == "python"` 的硬编码校验改为注册表查找；保留无语言请求默认 Python；执行、提交、runtime 状态继续返回现有字段，并新增可选语言元数据 |
| `src/code_navi/online_compiler/piston.py` | 从 Python 专用客户端扩展为通用 Piston 执行客户端 | 新增按 `LanguagePackage` 构造 payload 的通用方法；保留 `execute_python()` 兼容包装器；禁止客户端传入命令、版本和资源限制；统一编译/运行结果归一化 |
| `src/code_navi/online_compiler/judging.py` | 让服务端题目判定支持不同语言实现 | 将 `ExecutionRunner.execute_python()` 抽象为受控 `execute()`；保留旧调用适配；判题比较、隐藏测试脱敏和 verdict 优先级不变 |
| `src/code_navi/online_compiler/problems/models.py` | 解除题目版本只能是 Python 的限制 | 将 `language` 校验改为语言包 ID 校验；保持现有 Python `ProblemVersion` 可反序列化；不在模型中保存用户命令或 runtime 参数 |
| `src/code_navi/online_compiler/problems/repository.py` | 建立题库语言分区 | 将仓库键和查询接口改为 `(language_id, problem_id, version)`；旧调用默认 Python；未知语言或缺少对应版本时不得跨语言回退 |
| `src/code_navi/online_compiler/problems/catalog.py` | 将现有题目明确归入 Python | 保留全部现有题目内容和测试，仅通过新的 repository 契约注册到 `python`；本任务不新增其他语言题目 |
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

练习记录当前不属于共享 SQLAlchemy Base，`COMPILER_DATABASE_PATH` 指向由编译器模块自主管理的独立 SQLite。练习记录的 schema 由编译器模块执行幂等、向前兼容的本地升级，不直接使用 Alembic；因此本功能不新增 `migrations/` 或 Alembic revision。只有未来先通过单独架构决策把练习记录迁入共享业务数据库后，才适用共享 Alembic 流程；`dev-start.cmd` 的业务库迁移步骤不迁移练习记录。

### 12.3 需要新增的测试文件

| 文件 | 验证目的 |
| --- | --- |
| `tests/online_compiler/test_languages.py` | 语言包模型、别名、固定版本、能力状态和非法配置 |
| `tests/online_compiler/test_language_registry.py` | runtime 探测、注册表筛选、未知语言拒绝和 Python 默认兼容 |
| `tests/online_compiler/test_piston_languages.py` | 各分支已实现语言的 payload、文件名、编译/运行阶段和错误映射 |
| `tests/online_compiler/test_sql_adapter.py` | SQL 临时库、fixture、只读限制、结果归一化、超时和数据库隔离 |
| `tests/online_compiler/test_language_api.py` | `/languages` 能力接口、旧 `/runtime` 响应、旧执行请求和不支持语言的状态码 |
| `tests/online_compiler/test_learning_records_languages.py` | 旧独立 SQLite 记录读取、新记录语言字段和编译器自管 schema 升级兼容 |
| `tests/online_compiler/test_piston_live_languages.py` | 显式 live 环境逐语言执行和隔离边界；普通测试默认跳过 |
| `tests/online_compiler/test_problem_language_partition.py` | 现有题目归入 Python、复合唯一键、默认 Python 和禁止跨语言回退 |

现有 `test_application.py`、`test_compiler_api.py`、`test_piston.py`、`test_submit.py` 不删除，继续增加 Python 回归断言。只有在通用接口稳定后，才把 Fake Gateway 从 `execute_python()` 迁移到同时支持两者的测试替身。

### 12.4 分支与文件归属

下表用于限制每个分支的主要修改范围。后续分支可以在已合入的公共文件上增量扩展，但不能提前实现其他分支的能力。

| 分支 | 主要新增或修改文件 |
| --- | --- |
| `feat/code-practice-foundation` | `languages/models.py`、`registry.py`、`builtin.py`、`manifest.py`；`application.py`、`piston.py`、`judging.py`、`router.py`、`config.py`、`learning_records.py`、`ai_evaluation.py`；`problems/models.py`、`repository.py`、`catalog.py`；对应离线测试 |
| `feat/code-practice-java-javascript` | `languages/builtin.py`、`piston_adapter.py`、`piston.py`、`application.py`、`evaluation.py`、`runtime_setup.py`、`config.py`、`compose.yaml`、`dev-start.cmd`；`frontend/lib/api/compiler.ts`、练习页面；对应 mock/live/前端测试和部署文档 |
| `feat/code-practice-c-cpp` | 在 Java/JavaScript 已合入的通用文件上增加 GCC、C、C++ 配置与适配；修改 `runtime_setup.py`、`compose.yaml`、`dev-start.cmd` 和前端能力展示；对应 mock/live 测试和部署文档 |
| `feat/code-practice-sqlite` | `languages/sql_adapter.py`、`languages/builtin.py`、`application.py`、`router.py`、`config.py`；前端 API 与练习页面；SQL 隔离测试和安全文档；不修改 `problems/catalog.py` 或题库数据 |

## 13. 可直接执行的工作流

### 13.1 开始前清理与基线检查

曾阻塞 Git 扫描的两个 pytest 临时目录已可恢复地隔离到仓库外的
`D:\competition\wjj\code-navi-local-quarantine`。恢复时先确认仓库根目录没有同名目录，再使用
`Move-Item -LiteralPath` 将对应目录移回；不得覆盖现有目录或改用永久删除命令。随后执行：

```powershell
git status --short --branch
git branch --show-current
git log --oneline --decorate --graph main..HEAD
```

完成信号是 `git status` 不再出现 permission denied，工作区没有未提交或未跟踪修改。不得使用 `git reset --hard`、强制推送或直接删除目录。

### 13.2 从当前规划分支建立 foundation

当前 `feat/code-practice-languages` 包含设计文档和 Python 基线测试，可直接作为 foundation 的历史来源。工作区干净后执行：

```powershell
git add docs/product/code-practice-languages.md
git diff --staged --check
git diff --staged
git commit -m "docs(online-compiler): define four-branch language workflow"
git status --short --branch
git branch feat/code-practice-foundation feat/code-practice-languages
git switch feat/code-practice-foundation
git branch --show-current
git status
```

上述提交只允许包含本设计文档。先保留原 `feat/code-practice-languages` 作为本地备份，不删除、不上传。foundation 开发完成并确认历史与范围正确后，再由用户决定是否保留该备份分支。

### 13.3 foundation 分支开发顺序

按以下提交顺序实施，每个提交都先增加对应测试：

```text
feat(online-compiler): add language package registry
feat(online-compiler): add language capability api
refactor(online-compiler): generalize piston execution
feat(online-compiler): partition problems by language
feat(online-compiler): add language record metadata
docs(online-compiler): document language foundation
```

具体约束：

1. 前三个提交只让 Python 走新抽象，比较冻结的 Python 基线响应，不启用新语言。
2. 题库分区提交只修改模型、repository、查询和测试，现有七个题目的内容保持不变并全部归入 `python`。
3. 题库查询使用 `(language_id, problem_id, version)`；旧 `/submit` 未带语言时默认 Python；其他语言没有题目时明确失败，不回退 Python。
4. 语言记录采用独立 SQLite 的幂等 additive schema 升级，不新增 Alembic revision。
5. 每个提交前检查 `git diff`，按文件暂存并检查 `git diff --staged`。

foundation 最小验证：

```powershell
.venv\Scripts\python.exe -m pytest tests\online_compiler -q
.venv\Scripts\python.exe -m ruff check src\code_navi\online_compiler tests\online_compiler
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m build
git diff --check
```

foundation 合并条件：Python 基线全部通过，`/languages` 契约稳定，现有题目只从 Python 分区可见，未启用任何新语言。

### 13.4 创建并开发 Java/JavaScript 分支

foundation 通过评审并合入 `main` 后：

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/code-practice-java-javascript
git status --short --branch
```

建议提交顺序：

```text
feat(online-compiler): add javascript execution
feat(online-compiler): add java execution
feat(practice): add java and javascript selection
docs(online-compiler): document java and javascript support
```

每种语言分别完成：离线 payload/错误测试 → runtime 精确匹配 → 显式 live 成功、失败和隔离测试 → capability 标记 `enabled`。前端只提供自由运行，不提供题目列表或题目内容。除后端质量门外，运行：

```powershell
Set-Location frontend
npm run lint
npm run build
Set-Location ..
```

### 13.5 创建并开发 C/C++ 分支

从包含 foundation 的最新 `main` 创建；正常顺序是在 Java/JavaScript 合并后：

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/code-practice-c-cpp
git status --short --branch
```

建议提交顺序：

```text
feat(online-compiler): configure gcc runtime
feat(online-compiler): add c and cpp execution
feat(practice): add c and cpp selection
docs(online-compiler): document c and cpp availability
```

GCC 未精确安装并完成 C、C++ 分别的 live 隔离测试前，两种语言保持 `unavailable`。如果外部安装持续超时，停止启用工作并报告阻塞，不修改版本、不使用 `latest`、不让失败影响其他语言。

### 13.6 创建并开发 SQLite 分支

SQLite 只依赖 foundation。若 C/C++ 阻塞，可在 Java/JavaScript 合并后直接创建：

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/code-practice-sqlite
git status --short --branch
```

建议提交顺序：

```text
feat(online-compiler): add isolated sqlite execution
feat(online-compiler): expose sqlite capability
feat(practice): add sqlite editor and results
docs(online-compiler): document sqlite safety boundaries
```

测试必须覆盖请求间隔离、危险语句、超时、结果行数、输出大小和业务数据库不可访问。禁止在该分支增加 SQL 题目、题库 fixture、Alembic revision 或外部数据库依赖。

### 13.7 每个分支统一交付流程

每个分支在上传前执行：

```powershell
git branch --show-current
git status
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m build
git diff --check
git log --oneline main..HEAD
```

涉及前端时追加 `npm run lint` 和 `npm run build`；涉及真实 Piston 时追加明确标记的 live 测试。检查通过后才能按用户明确授权执行：

```powershell
git push -u origin <当前分支名>
```

默认通过目标为 `main` 的 PR 串行合并。PR 必须说明范围、实际启用语言、未启用语言、验证结果、安全边界、回滚方式和题库不在本任务范围。禁止 force push、直接推送 `main` 或在前置分支未合并时建立长期依赖链。

## 14. 兼容风险分级

| 等级 | 风险 | 合并门槛 |
| --- | --- | --- |
| P0 | Python 默认请求、现有题目判定、隐藏测试或学习记录被破坏 | 立即停止合并，先恢复 Python 回归 |
| P0 | 新语言可访问宿主文件、网络、凭据或真实数据库 | 禁止启用，必须修复并完成 live 隔离验证 |
| P1 | 新语言 runtime 缺失、版本漂移或编译命令不一致 | 该语言保持 unavailable，不影响其他语言 |
| P1 | 前后端能力字段不一致、旧客户端无法解析响应 | 保持旧字段，新增字段可选，并补 API 契约测试 |
| P2 | 模板体验、错误文案或语言编辑器模式不完整 | 不影响服务端安全和判题时可分阶段修复 |

## 15. 进入 foundation 编码的最终检查

只有以下条件全部满足，才从文档阶段进入 foundation 编码：

1. 启动目标固定 digest 的本地 Piston 后，只读 `/api/v2/packages` 能列出第 3.2 节全部精确 package；本阶段已核验 Python、Java、JavaScript 的 runtime ID、精确版本和 aliases，GCC 安装超时使 C/C++ 的 runtime 核验待补，逐语言执行隔离仍需 live 测试。
2. SQL 方言和执行后端已固定为 Python 标准库 SQLite，且没有任何真实数据库访问需求。
3. `/languages` 的响应字段、旧 `/runtime` 兼容策略和 `language` ID 命名已确定。
4. Python 回归门禁、live 隔离门禁和新增语言独立开关已写成测试要求。
5. Docker runtime 安装耗时、磁盘预算和失败回退策略已确认。
6. 当前大分支按第 13 节建立 `feat/code-practice-foundation`，原分支保留为本地备份，不改写 `main`、不强制推送。
7. 题库团队职责已经隔离：本任务只提供语言分区键和查询契约，不新增、迁移或扩充其他语言题目。
8. 每个实现提交只包含一个可验证阶段，避免把语言目录、执行器、前端和部署一次性混成不可回滚的大提交。
