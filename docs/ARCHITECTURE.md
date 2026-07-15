# 架构说明

## 仓库边界

`code-navi` 是产品应用仓库，拥有领域 Agent、业务流程、应用入口、配置装配和交付代码。`code-navi-kernel` 是独立运行时仓库，拥有平台无关的执行循环、事件、工具权限、上下文和 Provider 契约。

本仓库不复制或修改 kernel 源码。需要运行时能力时，只通过 kernel 的公开 `kernel.runtime`、`kernel.providers` 等接口接入；kernel 自身的设计决策、回放和权限语义在 kernel 仓库评审。

## 分层与依赖方向

```text
入口与宿主（CLI / service / future UI）
                 ↓
应用流程（用例编排、人工确认、结果展示）
                 ↓
领域层（student / teacher / research Agent）
                 ↓
code-navi-kernel 公开运行时接口
                 ↓
Provider、工具与持久化适配器
```

依赖只能向下。领域层不得导入 CLI、Web 或消息平台代码；应用代码不得直接调用 `kernel.core.run()` 绕过 `AgentRuntime`；Provider 原生对象不得成为领域模型。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/code_navi/domains/` | 三个领域的 Agent 声明、提示和输出约定 |
| `src/code_navi/` | 后续应用流程、入口和配置装配 |
| `examples/` | 最小且可运行的接线示例，不承载生产逻辑 |
| `tests/` | 应用行为、领域契约和集成测试 |
| `docs/` | 架构、开发规范、路线图和决策记录 |

## 变更归属判断

- 改变单 Agent 的执行、事件、权限或 Provider 通用语义：在 kernel 仓库提出。
- 改变助学、助教或助研的提示、输出和业务规则：在本仓库领域层实现。
- 改变命令、界面、身份、人工确认或部署：在本仓库应用/宿主层实现。
- 只服务一个领域的工具：由本仓库显式注册，不进入 kernel core。

若一个需求需要反向依赖、复制 kernel 代码或把业务规则写入运行时，应先记录架构决策，而不是直接实现。
