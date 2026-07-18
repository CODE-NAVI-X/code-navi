# CLI 使用说明

CLI 是项目初期验证通用助手、上下文装配和后续能力调用的宿主。用户围绕当前项目自然提问，不需要记忆内部 Skill 或 Tool 名称。

## 单次问答

```bash
code-navi ask "这个项目使用了什么架构？"
code-navi ask "解释这段代码" --attach src/app.py:20-60
Get-Content question.txt | code-navi ask
```

CLI 自动发现项目根目录，并将上下文回执写入 stderr、回答写入 stdout。脚本集成可以使用稳定的 JSON 输出：

```bash
code-navi ask "概括项目" --format json
```

默认 `mock` 只验证接线且不会生成真实回答。在线运行需要安装 `online` 可选依赖、设置 `OPENAI_API_KEY`，并通过 `--provider openai --model <模型名>` 显式启用。

## 交互 Shell

直接执行 `code-navi` 或 `code-navi shell`：

```text
[code-navi] > ? @last 解释上一条回答中的Runtime
[code-navi] > /branch Docker镜像和容器有什么区别？
[code-navi › Docker镜像和容器有什么区别？] > 数据卷又是什么？
[code-navi › Docker镜像和容器有什么区别？] > /back
```

| 输入 | 行为 |
| --- | --- |
| 普通文本 | 使用当前项目上下文回答 |
| `? <问题>` | 一次性快速提问 |
| `/branch <问题>` | 打开当前进程内可连续追问的问题分支 |
| `/back` | 返回主任务焦点 |
| `/context` | 查看当前上下文来源 |
| `/help` | 查看交互帮助 |
| `/exit` | 退出 |

`@last` 引用上一条回答；`@path:起始行-结束行` 引用项目内 UTF-8 文件片段。新问题分支会自动继承上一条回答作为起始参考，并最多向下一轮携带最近四组分支问答；所有内容继续受总字符预算限制。

## 上下文与安全

默认上下文优先级是：

1. 用户显式附加的文件片段；
2. 显式 `@last` 和当前问题分支历史；
3. `.code-navi/task.json`；
4. 项目 README 摘要。

CLI 不会自动读取整个仓库，也拒绝附加项目根目录以外的文件。`--no-project-context` 可以关闭任务元数据和 README 自动装配，但显式文件片段仍然有效。

当前通用助手不注册任何执行或写入工具。问题分支只在当前 CLI 进程内存在；`session_id` 只用于 Event 文件归类，不代表 kernel 已经恢复多轮对话。

## Event 日志

每次问题都是独立的 kernel run，Event 默认写入：

```text
<project>/var/runs/<session-id>/<run-id>.jsonl
```

可以用 `--events-dir` 和 `--session-id` 覆盖位置和标识。Event 是审计记录，不是长期聊天数据库。

## 退出码

| 退出码 | 含义 |
| ---: | --- |
| `0` | 完成 |
| `2` | 参数、问题或上下文错误 |
| `3` | Provider 配置错误 |
| `4` | 预算耗尽或运行中断 |
| `5` | Runtime 致命错误 |
| `130` | Ctrl+C 中断 |
