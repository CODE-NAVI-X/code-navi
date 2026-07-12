# S4 Tools and Permissions Design

Status: **EXPLANATORY DESIGN RECORD** (2026-07-12)

Normative S4 v1 decisions are frozen in `docs/S4_TOOLS_DECISIONS.md`.

This document does not amend the frozen S1, S2, or S3 contracts. Chinese is used
for the detailed explanation; public names and wire formats remain English.

## 0. 一句话结论

推荐把 S4 实现为两层：

1. 长生命周期的 `ToolRegistry` 只保存显式注册的工具定义与 handler；
2. 每次 `run` 新建一个短生命周期的 `RunToolDispatcher`，它持有本次运行的
   `PermissionGrant`、workspace 边界和执行环境，并在 S3 唯一的
   `dispatch(call)` 边界完成查找、校验、授权、执行和错误归一化。

这样既不把确认 UI 放进 kernel，也不会把授权保存成全局默认值，更不会绕开
S3 已冻结的唯一工具执行入口。

## 1. Gate 结论与已有约束

### 1.1 Gate 已通过的部分

- `docs/INVARIANTS.md` 存在。deny-by-default 的依据是 **I4**：每个工具调用
  在执行前都必须通过显式注册、schema validation 和 permission checks。
- `kernel/core/types.py` 已有 `ToolPermission`，采用 7 个可组合标记；权限不由
  模型在 `ToolCall` 中自行声明，而由可信的 `ToolSpec` 声明。这是兼容字段设计，
  也避免模型通过降低自己声明的权限来提权。
- `kernel/core/loop.py` 只有一个执行点：
  `tool_dispatcher.dispatch(call)`。
- S3 D28 已明确 dispatcher 负责 registry lookup、schema validation、
  permission checks、execution 和普通异常归一化。

### 1.2 当前存在的契约冲突

通用 S4 模板与本仓库的冻结合同并不完全一致，不能静默覆盖：

| 议题 | 通用 S4 模板 | 本仓库冻结合同 | 本设计处理 |
|---|---|---|---|
| 权限模型 | 恰好 3 层：READ/WRITE/DESTRUCTIVE | S2 D3：7 个可组合 flag | 推荐保留 7 flags；三层版仅作迁移候选 |
| 拒绝事件 | 新增 `tool_denied` | S2 D4、S3 D8：事件集合封闭，S3 不新增事件 | 推荐用结构化 `tool_returned` 表达；新增事件仅作候选 |
| dispatcher 事件 | 拒绝时由权限层发事件 | S3 D29：只有 loop 发事件 | dispatcher 返回 `ToolResult`，仍由 loop 统一发事件 |
| readonly bash | 可作为 READ | S2 D3：任何命令/脚本执行都要 EXECUTE | 若保留 7 flags，则至少 READ+EXECUTE |

在用户显式决定修改冻结合同之前，S4 实现不得破坏右侧约束。

## 2. 目标与非目标

### 2.1 S4 必须保证

- 未注册工具绝不执行。
- 参数不符合 JSON Schema 时，handler 绝不被调用。
- 权限不足时，handler 绝不被调用，run 不崩溃，模型收到可修复的结构化错误。
- 权限是每次 run 的值，不能变成 registry、配置文件或进程级永久默认值。
- 所有真实工具都经过同一个 dispatcher。
- 工具名、schema、权限和 handler 都显式注册；无 decorator 导入副作用、无扫描目录、
  无自动发现。
- 模糊风险向更高风险分类。
- WRITE 只能落在声明的 workspace root 内。
- 能删文件、任意执行、对外发送、部署或消费资金的能力默认拒绝。

### 2.2 S4 不负责

- 不负责 CLI/Web 的确认按钮和提示文案；host 只负责把用户决定转换成 grant。
- 不负责 provider-specific tool schema 转换；adapter 在 S7 完成转换。
- 不负责截断超大工具结果；这是 S5 context policy。
- 不负责事件持久化、回放界面和 trace CLI；这是 S5/S6。
- 不把业务审批流、角色体系或组织权限塞入 core。
- 不声称“路径检查”等价于 OS 级强沙箱。

## 3. 推荐架构

```text
Host / CLI confirmation UI
          |
          | builds a fresh PermissionGrant
          v
ToolRegistry (long-lived, immutable after freeze)
  - ToolSpec
  - handler
          |
          | bind for one run
          v
RunToolDispatcher (short-lived, per run)
  - PermissionGrant
  - ToolExecutionContext
  - SchemaValidator
          |
          | dispatch(ToolCall) -- S3's only call site
          v
lookup -> validate args -> check grant/scope -> invoke handler -> ToolResult
   |            |                |                    |
 unknown     invalid_args      denied             success/error
   +------------+----------------+--------------------+
                              |
                              v
                  loop emits tool_returned + message_added
```

关键安全边界：模型只控制 `ToolCall.name` 和 `ToolCall.args`；模型不能控制
`ToolSpec.required_permissions`、grant、workspace roots、handler 或执行 context。

## 4. 核心类型设计

建议新建 `kernel/core/registry.py`，保持核心 registry/permission 代码约 250 行以内。

### 4.1 ToolSpec

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    args_schema: Mapping[str, Any]
    required_permissions: frozenset[ToolPermission]
```

约束：

- `name` 非空，建议匹配 `^[a-z][a-z0-9_.-]{0,63}$`。
- `description` 是给模型的公开说明，不应包含 secret。
- `args_schema` 必须是 JSON Schema Draft 2020-12 object schema。
- 根 schema 必须是 `type: object`。
- 默认要求 `additionalProperties: false`；若工具确实接受开放对象，必须显式写明。
- `required_permissions` 至少一个 flag；纯本地无副作用读取为 `{READ}`。
- spec 在注册时复制/深冻结或规范化，避免外部随后修改 schema。
- 同名重复注册直接抛 `DuplicateToolError`，在 host 启动阶段暴露配置错误。

不把以下内容放入 `ToolSpec`：context 截断策略、UI 文案、用户角色、永久授权、
provider 原生 schema、业务审批状态。

### 4.2 ToolHandler

```python
class ToolHandler(Protocol):
    def __call__(
        self,
        args: Mapping[str, Any],
        context: "ToolExecutionContext",
    ) -> Any: ...
```

- handler 收到的 args 已通过 schema validation。
- 返回值必须可 JSON 序列化；否则 dispatcher 归一化为 `invalid_tool_output`。
- handler 的普通 `Exception` 转成失败 `ToolResult`，不能逃逸到 loop。
- `KeyboardInterrupt`、`SystemExit` 等 `BaseException` 不吞掉。
- handler 不接收 `PermissionGrant`，避免工具自行解释或放宽授权。

### 4.3 PermissionGrant

```python
@dataclass(frozen=True, slots=True)
class PermissionGrant:
    allowed_permissions: frozenset[ToolPermission] = frozenset({ToolPermission.READ})
    workspace_roots: tuple[Path, ...] = ()
    destructive_tool_names: frozenset[str] = frozenset()
```

语义：

- grant 由 host 在每次 run 开始前构造。
- `READ` 是唯一可默认允许的权限；其余 flag 必须显式进入
  `allowed_permissions`。
- WRITE 除了 flag 允许外，还要求目标路径处于至少一个规范化 workspace root 内。
- DESTRUCTIVE 除了 flag 允许外，还要求工具名出现在
  `destructive_tool_names`，防止一次“允许删除”无意开放所有破坏性工具。
- `workspace_roots` 在构造时 `resolve(strict=False)` 并规范大小写；检查使用
  `Path.is_relative_to(root)`，不能用字符串前缀。
- grant 不序列化为全局配置，不挂到 registry，不跨 run 复用，不由模型创建。
- 若未来 resume，需要 host 再次提供 grant；Event history 不能自动恢复授权。

为什么同时需要 `allowed_permissions` 和 `destructive_tool_names`：前者表达能力类别，
后者缩小最危险能力的工具范围。例如允许 `delete_temp_file` 不代表也允许
`deploy_production`。

### 4.4 ToolExecutionContext

```python
@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    run_id: str
    workspace_roots: tuple[Path, ...]
    environment: Mapping[str, str]
    subprocess_runner: SubprocessRunner | None = None
```

context 是可信依赖注入，不是模型参数。建议只提供最小能力：

- 只读工具不应获得 subprocess runner。
- 文件工具优先获得一个 workspace-scoped filesystem capability，而非裸 `os` 能力。
- environment 使用 allowlist（如 PATH、LANG、必要代理设置），不复制整个父进程环境。
- secret 按具体工具、具体 run 注入；没有 SENSITIVE 权限时 context 不含 secret。

### 4.5 ToolRegistry 与 RunToolDispatcher

```python
registry = ToolRegistry()
registry.register(spec, handler)
registry.freeze()

dispatcher = registry.bind(
    grant=grant,
    context=context,
    validator=Draft202012Validator,
)
run(provider, dispatcher, messages, config)
```

`ToolRegistry` API：

- `register(spec, handler) -> None`
- `freeze() -> None`
- `specs() -> tuple[ToolSpec, ...]`
- `bind(grant, context) -> RunToolDispatcher`

`freeze()` 后禁止注册，确保一个 run 期间工具集合不漂移。不要提供
`unregister()` 给正在使用的 registry；host 若需热更新，应构建新 registry 并用于新 run。

## 5. dispatch 的精确顺序

顺序不可交换：

```python
def dispatch(call: ToolCall) -> ToolResult:
    entry = registry.lookup(call.name)
    if entry is None:
        return failure("unknown_tool", ...)

    validation_errors = validator(entry.spec.args_schema).iter_errors(call.args)
    if validation_errors:
        return failure("invalid_arguments", ...)

    decision = permission_engine.check(entry.spec, call.args, grant, context)
    if not decision.allowed:
        return failure("permission_denied", ...)

    try:
        value = entry.handler(readonly_copy(call.args), context)
        ensure_json_serializable(value)
        return success(value, audit=decision.audit)
    except ToolUserError as exc:
        return failure("tool_error", safe_message(exc), ...)
    except Exception:
        return failure("tool_internal_error", "tool execution failed", ...)
```

原因：

1. lookup 先做，未知工具没有可信 schema 和权限定义；
2. schema validation 先于权限判断，避免 malformed args 进入 scope resolver；
3. 权限判断先于 handler，拒绝必须是零副作用；
4. handler 的预期失败是模型可见结果，而不是整个 run 的 fatal error。

registry 自身损坏、validator 初始化失败等 kernel invariant violation 可以抛出，让 S3
按 `fatal_tool_error` 终止；用户输入错误和权限拒绝不能抛出。

## 6. 结构化结果与错误合同

为了不修改已冻结的 `ToolResult` 字段，本方案使用其现有 `result` 字段承载统一 envelope，
并继续填充已有 `error` 字符串以兼容简单 adapter：

### 6.1 成功

```json
{
  "tool_call_id": "tc_123",
  "name": "read_file",
  "result": {
    "ok": true,
    "value": {"text": "..."},
    "audit": {
      "grant_check": "allowed",
      "required_permissions": ["READ"]
    }
  },
  "error": null,
  "permissions": ["READ"]
}
```

### 6.2 权限拒绝

```json
{
  "tool_call_id": "tc_123",
  "name": "bash",
  "result": {
    "ok": false,
    "error": {
      "code": "permission_denied",
      "message": "tool is not authorized for this run",
      "details": {
        "required_permissions": ["DESTRUCTIVE", "EXECUTE"],
        "missing_permissions": ["DESTRUCTIVE", "EXECUTE"],
        "destructive_tool_grant_missing": true
      },
      "retryable": true
    },
    "audit": {"grant_check": "denied"}
  },
  "error": "permission_denied: tool is not authorized for this run",
  "permissions": ["DESTRUCTIVE", "EXECUTE"]
}
```

`retryable: true` 表示模型可改用低权限工具或请求 host 在下一次 run 提供授权；它不表示
dispatcher 会自动重试，也不表示 kernel 能弹确认框。

### 6.3 错误 code

| code | 是否调用 handler | 模型可否修复 | 含义 |
|---|---:|---:|---|
| `unknown_tool` | 否 | 是 | 工具未注册或名称错误 |
| `invalid_arguments` | 否 | 是 | JSON Schema 不通过 |
| `permission_denied` | 否 | 是/需 host | flag、工具名或 workspace scope 不允许 |
| `tool_error` | 是 | 通常可 | handler 声明的业务/输入态失败 |
| `tool_internal_error` | 是 | 通常不可 | handler 非预期异常，向模型隐藏 traceback |
| `invalid_tool_output` | 是 | 不可 | handler 返回不可 JSON 序列化对象 |

错误 details 只放安全、确定、可操作的信息；不得回传 secret、完整环境变量、原始 traceback
或 workspace 外的敏感绝对路径。

## 7. 七个权限标记的精确定义与组合

本节遵守 S2 D3。

| Flag | 需要显式 grant | 典型例子 | 备注 |
|---|---:|---|---|
| READ | 否 | 读公开 workspace 文件 | 一旦涉及隐私，再加 SENSITIVE |
| WRITE | 是 | 在 workspace 新建文件 | 还要通过 workspace scope |
| DESTRUCTIVE | 是，且按工具名 | 删除、覆盖、reset、deploy | 模糊时向此标记提升 |
| EXECUTE | 是 | shell、脚本、测试、notebook | 即使命令“只读”也属于执行 |
| NETWORK | 是 | HTTP GET、搜索、远端 API | 与 PUBLISH 不等价 |
| SENSITIVE | 是 | secret、成绩、身份信息 | 与 READ 不等价 |
| PUBLISH | 是 | 发邮件、评论、通知、公开发布 | 只要产生外部可见动作就需要 |

组合示例：

- `read_file`: `{READ}`
- `read_private_file`: `{READ, SENSITIVE}`
- `write_file`: `{WRITE}`，且目标必须在 workspace 内；覆盖已有文件时提升为
  `{WRITE, DESTRUCTIVE}` 或拆成独立 `overwrite_file`。
- `http_get`: `{READ, NETWORK}`
- `send_email`: `{NETWORK, PUBLISH}`；若含私人数据，再加 `SENSITIVE`。
- `run_tests`: `{READ, EXECUTE}`；测试若可能写缓存，实际应至少 `{WRITE, EXECUTE}`。
- unrestricted `bash`: 按其能力上界标记，至少 `{DESTRUCTIVE, EXECUTE}`；如果允许网络和
  继承 secret 环境，还必须加 `{NETWORK, SENSITIVE, PUBLISH}`。推荐默认不给它网络和 secret。

不能依据 command 文本做“看起来安全”的降级授权。静态 `ToolSpec` 是可信分类；动态参数
检查只能进一步拒绝，不能降低 spec 的 required permissions。

## 8. WRITE 与路径边界

### 8.1 路径检查算法

所有文件类 WRITE 工具执行前：

1. 拒绝 NUL、设备路径和工具不支持的 URI scheme；
2. 相对路径相对于明确的 workspace root 解析，不相对于进程随机 cwd；
3. `resolve(strict=False)`，规范 `..`、`.`、盘符和大小写；
4. 检查 resolved path 是否位于允许 root 内；
5. 对已有父目录逐段检查 symlink/junction，避免跳出 root；
6. 打开文件时尽量使用不跟随 symlink 的 OS primitive；
7. 写入后记录实际目标，但不把敏感绝对路径暴露给模型。

仅做第 3/4 步仍存在 TOCTOU（检查后到使用前路径被替换）风险。高保证实现应使用
目录句柄相对打开、`O_NOFOLLOW` 或平台等价能力。Windows junction/reparse point 需要单独测试。

### 8.2 覆盖策略候选

| 候选 | 设计 | 好处 | 代价 |
|---|---|---|---|
| A（推荐） | `write_new_file` 与 `overwrite_file` 拆开 | 权限清晰；普通 WRITE 不会误覆盖 | 工具数量略多 |
| B | 一个 `write_file(overwrite: bool)` | API 少 | 权限是静态 spec，整个工具必须按 DESTRUCTIVE，过度授权 |
| C | 动态 permission resolver 提升权限 | 调用体验灵活 | 权限逻辑更复杂，审计和 adapter 展示更难 |

推荐 A。动态 resolver 可用于 scope 收窄，不应动态降低静态权限。

## 9. JSON Schema 校验方案

设计开始时环境尚未安装 `jsonschema`；S4 实现已按候选 A 将其声明为项目依赖。

### 候选 A：使用 `jsonschema` 库（推荐）

- 依赖：`jsonschema>=4.23,<5`，项目实现阶段需要补 `pyproject.toml`。
- 注册时用 metaschema 检查 schema 本身；dispatch 时使用预编译
  `Draft202012Validator`。
- 优点：标准完整、错误路径清晰、边界行为已有广泛测试。
- 缺点：增加一个运行时依赖，安装包更大。

### 候选 B：内建最小 validator

- 只支持 object/string/integer/number/boolean/array/null、required、enum、范围和
  `additionalProperties`。
- 优点：零依赖、代码可完全掌控。
- 缺点：非常容易出现标准偏差与绕过；要自己维护格式、组合 schema、引用和错误路径；
  很难在 250 行 registry 预算内同时做对。

### 候选 C：host 注入 validator

- core 只定义 `SchemaValidator` protocol。
- 优点：kernel 零依赖，宿主可选实现。
- 缺点：不同 host 可能产生不同安全语义，违反“kernel 保证 validation”的目标。

推荐 A。若强制零依赖，可用 C，但必须提供并指定一个 reference implementation，且 conformance
tests 必须保证所有 host 行为一致。不推荐 B。

校验错误最多返回前 8 个，按 JSON path 排序，例如：

```json
{
  "path": "$.timeout_seconds",
  "keyword": "maximum",
  "message": "must be less than or equal to 30"
}
```

不要把 Python repr、validator traceback 或整个大参数原样回显给模型。

## 10. Bash 工具设计

### 10.1 unrestricted bash

建议文件：`kernel/tools/bash.py`（而不是 `kernel/core`）。core 只知道 handler protocol。

参数 schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "command": {"type": "string", "minLength": 1, "maxLength": 16384},
    "cwd": {"type": ["string", "null"]},
    "timeout_seconds": {"type": "number", "minimum": 0.1, "maximum": 120}
  },
  "required": ["command"],
  "additionalProperties": false
}
```

安全默认：

- spec 至少要求 `{DESTRUCTIVE, EXECUTE}`，且工具名必须显式列在 destructive grant。
- 使用固定 executable（POSIX `/bin/bash`，Windows 可显式配置 Git Bash/WSL adapter），不能让
  模型指定 shell executable。
- cwd 必须是 workspace 内已存在目录。
- 不使用父进程完整环境；采用 allowlisted env。
- 默认不注入 credentials，不开放网络；若运行环境无法技术上阻断网络，则 spec 必须再加
  `NETWORK`，不能只靠提示词承诺。
- timeout 后终止整个 process group/job object，避免遗留子进程。
- stdout/stderr 分开捕获，并设字节上限；完整大输出留给 S5 artifact/context 策略。
- 返回 exit code、截断后的 stdout/stderr、timed_out 和 truncated 标记。
- command 不写入日志时也不能假装可审计；应记录经过 secret redaction 的摘要或 hash。

重要：permission grant 是“允许执行”，不是“命令已经安全”。unrestricted shell 不能通过字符串
黑名单变成可靠沙箱。

### 10.2 readonly 命令候选

若要演示低风险执行，推荐不要接受 command string，而是接受枚举化操作：

```json
{
  "operation": "git_status | git_diff | list_files | search_text",
  "args": ["...受约束的参数..."]
}
```

实现使用 `subprocess(..., shell=False)` 和固定 executable/flag allowlist，拒绝：

- `-c`、`--exec`、output path、config alias、pager、external diff、hook；
- 任意环境变量覆盖；
- workspace 外 cwd；
- 可触发网络、插件、子命令或文件写入的参数。

在当前 7-flag 合同下，它仍是 `{READ, EXECUTE}`，所以需要 EXECUTE grant。若希望它完全免授权，
更好的做法是提供原生 Python `list_files`/`search_text` READ 工具，而不是把 shell 错标为 READ。

### 10.3 Canary 测试的跨平台处理

- POSIX CI：创建真实临时文件，通过 `bash -lc 'rm -- ...'` 调用；无 grant 时文件必须保留，
  有 grant 时文件必须删除。
- Windows CI：若没有 Bash，测试标记为 capability skip，并增加 PowerShell/平台 runner 的等价真实
  文件测试；不能用 mock 代替安全 canary。
- canary 路径必须来自测试临时目录，测试前后验证它位于该目录，不能拼接任意删除目标。

## 11. 事件与可审计性候选

### 候选 A：保持 S2/S3 事件冻结（当前推荐）

- 拒绝返回 `ToolResult(error=..., result={ok:false,...})`。
- loop 按现有逻辑发 `tool_returned` 和 `message_added`。
- `ToolResult.permissions` + result.audit 证明进行了 grant check。
- 好处：零冻结合同变更；run 继续；resume/replay 不受影响。
- 代价：查询“所有拒绝”要过滤 `tool_returned` payload，语义不如独立事件直观。

### 候选 B：显式修订 S2/S3，新增 `tool_denied`

- loop 需要识别 dispatcher decision 或扩展返回类型，再发 `tool_denied`。
- 好处：审计查询、告警和指标最清晰；与通用 S4 模板一致。
- 代价：要显式解冻并修订 S2 D4、S3 D8/D29/D30、Event validation、AgentState fold、
  round-trip/resume tests；不是局部 S4 代码改动。

### 候选 C：新增通用 `permission_checked`

- 成功和拒绝都记录决策。
- 好处：审计最完整。
- 代价：Event volume 更大，且同样需要改冻结合同；S6 前可能过早设计。

本轮推荐 A。若“独立 denial event”是硬需求，应由用户明确选择 B 并批准合同修订。

## 12. 三层权限与七标记权限候选

### 候选 A：保留 7 个可组合 flag（当前推荐）

优点：

- 已冻结，不产生迁移成本；
- 能区分 NETWORK 与 PUBLISH、READ 与 SENSITIVE；
- 更适合真实 agent 工具的组合风险。

缺点：

- host 确认 UI 和测试矩阵更复杂；
- 与通用 S4 “恰好三层”验收文字不一致。

### 候选 B：迁移为 READ/WRITE/DESTRUCTIVE 三层

优点：

- 简单、容易解释；
- 与通用 S4 模板完全一致。

缺点：

- 无法准确表达“联网但不写”“读取敏感信息”“外部发布”；
- 必须显式解冻 S1 I5、S2 D3、README 和相关类型/测试；
- 容易把所有网络工具粗暴放进 DESTRUCTIVE，授权过宽。

### 候选 C：三层 risk + 七个 capability

优点：UI 可展示简单 risk level，同时执行层保留细粒度能力。

缺点：形成两套权限真相，组合规则、冲突解析和测试量显著增加；违反当前“一个冻结权限词汇”的
简洁边界。

推荐 A，不推荐 C。只有用户明确更看重模板一致性而非细粒度控制时才选 B。

## 13. 文件布局与职责

推荐实现布局：

```text
kernel/
  core/
    types.py                 # 复用 ToolPermission/ToolCall/ToolResult
    registry.py              # ToolSpec, PermissionGrant, registry, dispatcher
  tools/
    __init__.py
    bash.py                  # 真实 bash handler，不进入 core
tests/
  kernel/
    core/
      test_registry.py
      test_permissions.py
    tools/
      test_bash.py
docs/
  S4_TOOLS_DESIGN.md         # 本文，评审后再决定是否冻结为 decisions
```

如果核心实现超过约 250 行，优先把 JSON Schema adapter 放到
`kernel/core/schema_validation.py`，不要把权限模型拆散到多个互相绕过的 dispatcher。

## 14. 测试设计

### 14.1 Registry tests

- 注册成功，`specs()` 稳定排序或保持显式注册顺序。
- 重名注册失败。
- 非法名字、空 description、非 object schema、非法 metaschema 注册失败。
- freeze 后注册失败。
- 未知工具返回 `unknown_tool`，不抛异常。
- registry 无 auto-discovery/import-time side effect。

### 14.2 Schema tests

- missing required、wrong type、extra property、boundary value、nested array/object。
- malformed args 永远不调用 handler，用 spy counter 证明。
- 确定性生成一组 JSON 边界值：`null`、布尔、超大整数、NaN/Infinity 拒绝策略、深嵌套、
  超长字符串、Unicode、空 key。
- 可选 Hypothesis/property tests；保留固定 seed/golden cases 便于复现。
- schema 自身错误在 register 阶段失败，不延迟到调用时。

### 14.3 Permission matrix

至少参数化覆盖：

- READ 默认允许。
- 每个非 READ flag 缺失时拒绝，存在时允许。
- 多 flag 工具要求全部满足，不能 any-of。
- DESTRUCTIVE flag 已允许但工具名未列出时仍拒绝。
- destructive tool name 已列出但 DESTRUCTIVE flag 缺失时仍拒绝。
- WRITE 在 root 内允许，root 外、`..` escape、symlink/junction escape 拒绝。
- grant A 不能泄露给下一次使用 grant B 的 run。
- 模型在 args 中伪造 `permissions` 字段因 `additionalProperties:false` 被拒绝。

### 14.4 Loop integration

- denial 后出现 `tool_called -> budget_updated -> tool_returned -> message_added`，run 继续到下一次
  provider call。
- denial 计入 tool-call budget，因为 S3 D23 统计 attempted dispatch。
- unknown/invalid/denied 都不是 fatal run error。
- registry invariant failure 才走现有 `fatal_tool_error`。
- provider 在收到结构化错误后可修正参数并再次调用。

### 14.5 真实 canary

```text
create real temp file
-> call bash rm without grant
-> ToolResult permission_denied
-> assert file exists
-> new dispatcher with per-run explicit grant for bash
-> call the same bash rm
-> assert success and file does not exist
```

测试必须真实触发文件系统，不得 mock handler；删除目标必须是测试自己的 temp directory。

## 15. 实施顺序

### Phase 1：合同评审

1. 确认采用 7 flags 还是解冻迁移到 3 tiers。
2. 确认 denial 暂用 `tool_returned` 还是解冻新增 `tool_denied`。
3. 确认 JSON Schema dependency 方案。

### Phase 2：最小 core

1. 增加 `ToolSpec`、`PermissionGrant`、`ToolRegistry`、`RunToolDispatcher`。
2. 注册时校验 schema，调用时校验 args。
3. 实现统一成功/错误 envelope。
4. 不修改 S3 loop 的 dispatch call site。

### Phase 3：权限与 scope

1. 完成 7 flags all-of 检查。
2. 完成 destructive tool-name 二次授权。
3. 完成 workspace root 规范化和文件 scope helper。
4. 加入 symlink/junction 与跨盘测试。

### Phase 4：真实工具

1. 先实现一个原生 READ 工具证明 grant-free 路径。
2. 实现 unrestricted bash，默认高风险、显式授权。
3. 可选实现固定操作的 inspect 工具，不构造通用 shell policy framework。

### Phase 5：验收与冻结

1. 跑全部 S2/S3 regression tests。
2. 跑 S4 registry/permission/canary tests。
3. 静态检查 core 无 subprocess/provider/UI imports。
4. 评审通过后把最终决定提炼到 `docs/S4_TOOLS_DECISIONS.md` 并冻结。
5. 更新 README 状态与验证数字。

## 16. 验收标准（适配当前冻结合同）

- I4 顺序被代码和测试证明：explicit registration -> schema validation -> permission check
  -> handler。
- 未授权破坏性调用返回结构化拒绝，handler 零调用，run 继续。
- 同一调用在新的 per-run grant 明确允许 flag 和工具名后成功。
- malformed args 永不进入 handler，并有 deterministic + property-style coverage。
- 未注册工具永不执行。
- 真实 canary 文件无授权时保留、有授权时删除。
- registry/permission 核心约 250 行以内。
- 只有一个 S3 dispatch call site。
- grant 不持久化、不进入 registry、不从 Event history 自动恢复。
- 若保留当前合同，权限 flag 恰好仍为 7 个；不得偷偷新增 ADMIN/SUDO 等。
- 若采用三层迁移，必须先显式修订冻结合同，再把验收改为恰好 3 tiers。

## 17. 推荐决策摘要

当前最稳妥、最少破坏且足以实现 S4 的组合是：

1. **保留 7 个可组合权限 flag**；
2. **拒绝通过结构化 `ToolResult` 表达**，暂不新增 Event type；
3. **使用 `jsonschema` Draft 2020-12 reference implementation**；
4. **长期 registry + 每 run dispatcher/grant**；
5. **READ 默认允许，其余显式允许，DESTRUCTIVE 再按工具名收窄**；
6. **WRITE 拆分 create 与 overwrite 工具**；
7. **unrestricted bash 永远按高风险能力上界授权，不做命令字符串“安全猜测”**；
8. **真正免授权的读取能力用原生 READ 工具实现，不把 shell 错标成 READ**。

该组合保持 S1-S3 冻结合同不变，并为后续 S5 的 context policy、S6 的审计与 replay、
S7 的 provider tool schema adapter 留出清晰边界。
