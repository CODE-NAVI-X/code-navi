# 高风险能力边界

本文件只定义能力是否启用、允许的动作、权限和确认点。Mock、隔离环境与真实资源的测试顺序见 [testing.md](testing.md)。

## 1. 在线 Provider

1. 公共配置默认使用离线 Mock；OpenAI 或 DeepSeek 应显式配置 Provider、模型和凭据。
2. 学习 API 当前在未设置 `CODE_NAVI_PROVIDER`、但检测到 `DEEPSEEK_API_KEY` 时会自动选择 DeepSeek。这是现有兼容行为，新入口不得复制；生产化前应改为显式选择。
3. 本机配置可以写入已忽略的 `.code-navi/provider.env`；状态接口不返回密钥，浏览器也不持久化密钥。
4. `PUT /api/v1/research/provider/configuration` 与 `POST /api/v1/research/provider/test` 默认禁用，只有显式设置 `CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG=true` 且请求来自 loopback 时可用；公开部署不得启用。
5. 发送敏感内容或费用边界不清楚时，调用前取得用户确认。
6. 科研难点、实验方案和代码草案个性化不得随创建、发送消息或恢复会话自动调用；只接受独立的显式确认请求，并记录 Runtime Event。模型不得替换服务端维护的可执行代码模板。

模型调用的 Runtime 与审计边界统一见 [系统架构](../architecture/system.md)，本文件不重复。

## 2. 学术资料检索

当前科研模块只启用用户显式触发的 `academic_search`，单次调用权限为 `READ + NETWORK`，来源限制为 OpenAlex、Crossref 和 arXiv，结果仅覆盖元数据与摘要。每个来源可用 `CODE_NAVI_ACADEMIC_<SOURCE>_ENABLED` 单独关闭，缓存默认一小时，可由 `CODE_NAVI_ACADEMIC_CACHE_TTL_SECONDS` 调整。

新增资料源时必须定义允许域、发送数据、速率限制、超时和来源失败语义。没有全文时不得描述为已读取或核验全文；检索失败不得由模型补写证据。

## 3. 代码执行

当前练习原型通过 `src/code_navi/online_compiler/` 调用独立 Piston 服务，不使用 Kernel Bash 工具。只支持固定 Python 3.12 runtime，源代码与标准输入默认各限制 64 KiB，墙钟和 CPU 时间各 2 秒，内存 128 MiB，输出 64 KiB。执行、服务端判题、规则分类和可选模型建议分别返回；模型不能改变执行器结果或测试判定。

当前边界：

1. `compose.yaml` 将 Piston API 只绑定到宿主 loopback；Piston 按官方 Isolate 运行方式使用 `privileged: true`，同时显式关闭作业网络并限制进程、文件、输出、并发和容器总资源；
2. 服务端请求限制已有 Mock/适配器测试，`tests/online_compiler/test_piston_live.py` 提供真实 Piston 的网络、工作区清理、仓库隔离和进程/文件限制检查；该显式测试取得通过结果后才满足真实执行隔离的合并准入；
3. Piston runtime 安装需要访问其包源，属于显式部署联网动作；
4. 练习记录使用浏览器 UUID 和独立 SQLite，只保存代码哈希与摘要，不保存原始代码或标准输入，但没有应用身份授权、迁移和删除流程；
5. `compose.web.yaml` 尚未接入 Piston，当前 Web 容器部署不提供练习执行服务。

在扩大运行范围或公开服务前必须具备：

1. 独立执行服务或等价隔离边界；
2. CPU、内存、时间、进程、网络、文件系统和输出限制；
3. 临时工作区与进程清理；
4. 编译错误、运行错误、超时、资源超限和系统错误的结构化结果；
5. 对 Provider、数据库和仓库凭据的隔离；
6. 由执行器结果产生的运行与测试状态。

`src/kernel/tools/bash.py` 的存在仍不表示产品可以绕过 Piston 执行学生代码。新增语言、开放 Piston API、取消 loopback 限制或改变 privileged 状态时，必须重新验证上述边界。

## 4. 远程仓库写入

当前未启用远程仓库写入。接入时必须：

1. 明确平台、仓库、分支和支持的动作；
2. 使用独立、可撤销的最小权限凭据；
3. 在真实写入前展示目标和动作并取得确认；
4. 返回部分完成、冲突和权限失败，提供相应恢复或回滚方式；
5. 不把凭据放入模型上下文、Event、日志、配置样例或前端持久化状态。

## 5. 准入

高风险能力达到合并就绪，必须同时具备明确的目标与权限、真实副作用前确认、凭据边界和 [testing.md](testing.md) 要求的验证。生产可用还需满足 [生产准入](../deployment/production.md) 的部署、监控、数据和回滚要求。
