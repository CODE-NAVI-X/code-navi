# Code Navi 文档

本目录是仓库规范与设计事实的唯一入口。根目录 README 只保留项目介绍和快速开始；详细规则在此维护。

| 文档 | 用途 | 何时更新 |
| --- | --- | --- |
| [CLI.md](CLI.md) | CLI 问答、上下文、问题分支和退出码 | 命令或交互协议变化时 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 仓库边界、分层与依赖方向 | 新增层、入口或跨层依赖时 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 环境、编码、测试、分支、提交和 PR 规范 | 开发流程或质量门变化时 |
| [KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md) | 内置 kernel 的来源和运行时接入约束 | 修改 kernel 或改变接入方式时 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker 构建、配置、运行和持久化 | 修改交付方式时 |
| [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | 阶段范围与验收标准 | 阶段开始、验收或调整时 |
| [INVARIANTS.md](INVARIANTS.md) | 不能被普通功能改动破坏的应用约束 | 经架构评审确认后 |
| [NON_GOALS.md](NON_GOALS.md) | 当前明确不做的事项 | 产品范围改变时 |
| [DECISIONS.md](DECISIONS.md) | 架构决策记录规则和索引 | 作出不可轻易逆转的决策时 |

文档应描述已经存在或已批准的事实。计划中的能力必须明确标为“计划”或“未实现”，不得用将来设计替代当前状态。
