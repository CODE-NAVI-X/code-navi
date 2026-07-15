# 开发规范

## 1. 环境与安装

- Python 最低版本为 3.11；开发者应使用独立虚拟环境。
- GitHub Git 凭据必须能够读取私有 `code-navi-kernel` 仓库；本机可使用 `gh auth setup-git` 配置。
- 依赖只在 `pyproject.toml` 声明，不提交虚拟环境、构建产物或本地密钥。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 2. 代码与目录

- 生产代码放在 `src/code_navi/`，测试放在 `tests/`，可运行示例放在 `examples/`。
- 新模块使用类型标注；公开接口提供简短 docstring；优先使用小而明确的函数和不可变数据。
- 行宽为 100；导入、基础错误和常见 Python 反模式由 Ruff 检查。
- 领域代码只描述业务角色、输入输出和允许的工具，不持有平台 SDK 或密钥。
- 只通过 kernel 公开接口集成，禁止从本仓库复制 `kernel/` 源码或绕过 `AgentRuntime`。
- 不在日志、Event metadata、测试样例或文档中提交令牌、个人信息和未脱敏业务数据。

## 3. 测试与本地质量门

每个行为变更至少包含一个能够在修改前失败、修改后通过的测试。测试默认离线、确定且不访问真实模型；外部服务测试必须显式标记并由独立流程运行。

提交前执行：

```bash
ruff check .
pytest
python -m build
```

开发依赖已经包含构建工具。文档-only 改动至少检查链接、命令和当前状态是否一致。

测试分层：

- 单元测试：领域声明、解析、校验和纯业务规则；
- 集成测试：应用层经 `AgentRuntime` 与 MockProvider/假工具完成一次运行；
- 在线冒烟测试：真实 Provider 或外部系统，仅在明确配置凭据后手动/CI 触发。

## 4. Git 分支与提交

### 4.1 先了解三个位置

Git 新手可以先记住：文件修改通常会依次经过下面三个位置。

1. 工作区：正在编辑、但还没有暂存的文件；
2. 暂存区：已经通过 `git add` 选中、准备放入下一次提交的修改；
3. 本地仓库：已经通过 `git commit` 保存的提交。

`git push` 才会把本地提交上传到远端仓库。**`git add`、`git commit` 和 `git push` 是三个不同的动作，完成前一步并不代表修改已经上传。**

### 4.2 分支命名

`main` 保持可安装、可测试，不直接堆叠未完成工作。分支使用 `<type>/<short-topic>`：

- `feat/`：新能力；
- `fix/`：缺陷修复；
- `docs/`：文档；
- `refactor/`：不改变外部行为的重构；
- `test/`：测试；
- `chore/`：依赖或工程维护。

分支名使用简短的英文小写单词并以连字符分隔，例如 `feat/exercise-planner`、`fix/login-timeout`、`docs/git-workflow`。**不要使用自己的名字、`test`、`new` 等无法说明工作内容的名称。**

### 4.3 开始开发：更新 `main` 并创建新分支

每一项新任务都从最新的 `main` 创建独立分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c docs/git-workflow
```

请把示例中的 `docs/git-workflow` 换成自己的分支名。`git switch -c` 会同时创建并切换到新分支。执行后可以确认当前分支：

```bash
git branch --show-current
git status
```

**开始修改前一定要确认自己不在 `main` 分支。不要直接在 `main` 上开发或提交。** 如果切换分支时 Git 提示本地修改会被覆盖，不要强行执行；先提交当前修改，或使用 `git stash` 临时保存，并确认这些修改属于哪一项任务。

### 4.4 开发完成：检查、暂存并提交

先运行第 3 节中的质量检查，再查看有哪些文件被修改：

```bash
git status
git diff
```

确认修改正确后，**优先按文件暂存**，避免把临时文件、密钥或其他任务的修改一起提交：

```bash
git add docs/DEVELOPMENT.md
git diff --staged
git status
```

`git diff --staged` 显示的内容就是下一次提交将包含的内容。确认无误后创建提交：

```bash
git commit -m "docs: explain git workflow for beginners"
```

提交信息遵循 Conventional Commits，例如 `feat(student): add exercise planner`、`fix: handle empty response`、`docs: clarify git workflow`。信息应说明“这次提交做了什么”，避免使用 `update`、`change`、`fix bug` 等含糊描述。一次提交只解决一个可解释的问题，不混入无关格式化或生成文件。

**提交前必须检查 `git diff --staged`，确认没有密码、令牌、个人信息、调试输出和无关文件。** 如果暂存了错误文件，可以用 `git restore --staged <文件路径>` 将它移出暂存区；这个命令不会删除文件中的修改。

### 4.5 推送到远端

第一次推送新分支时执行：

```bash
git push -u origin docs/git-workflow
```

`-u` 会建立本地分支与远端分支的关联。之后在同一分支继续提交，只需执行：

```bash
git push
```

**推送前再次用 `git status` 和 `git branch --show-current` 确认分支。不要把功能分支误推送到远端 `main`，也不要对共享分支使用 `git push --force`。**

### 4.6 开发期间把最新 `main` 合并到当前分支

如果其他人的修改已经合入 `main`，或者 PR 提示分支落后，可以把最新 `main` 合并到自己的分支。先确认当前修改已经提交，然后执行：

```bash
git fetch origin
git branch --show-current
git merge origin/main
```

这里的 `git fetch origin` 只下载远端最新状态，不会改动当前文件；`git merge origin/main` 会把远端 `main` 的最新提交合入当前分支。**运行 `git merge` 前必须确认当前是自己的功能分支，而不是 `main`。** 合并成功并完成测试后，再执行 `git push` 更新远端分支。

如果出现冲突，Git 会列出冲突文件。打开文件，找到 `<<<<<<<`、`=======`、`>>>>>>>` 标记，与相关开发者确认应保留的内容，删除标记并重新测试，然后执行：

```bash
git add <已解决的文件路径>
git commit -m "chore: merge main into docs/git-workflow"
git push
```

**不确定如何解决冲突时不要猜，也不要删除整个文件来“消除”冲突。** 可以用 `git merge --abort` 放弃本次合并，回到合并前的状态，再寻求帮助。

## 5. Pull Request

### 5.1 创建并检查 PR

功能分支推送后，在 GitHub 上创建从该分支到 `main` 的 Pull Request（PR）。PR 描述至少包含：问题与范围、实现摘要、验证命令与结果、风险/回滚方式、涉及的文档。

**默认通过 PR 和代码评审合并到 `main`，不要在本地直接向 `main` 提交或推送。** 创建 PR 后继续修改时，仍在原功能分支提交并执行 `git push`，PR 会自动更新。

满足以下条件才能合并：

- 测试和 Ruff 通过；
- 新行为有测试，用户可见变化有文档；
- 未破坏 [INVARIANTS.md](INVARIANTS.md)；
- 没有未说明的 kernel 升级、权限扩大或外部副作用；
- 评审者能从 PR 中区分已完成能力和后续计划。

### 5.2 将分支合并到 `main`

评审通过且自动检查全部通过后，使用 GitHub PR 页面提供的合并按钮。**合并前再次确认 PR 的目标分支是 `main`、来源分支是自己的功能分支，并确认没有误带无关提交。** 仓库要求使用哪一种合并方式（Merge、Squash 或 Rebase）时，以仓库设置和维护者要求为准；新手不要为了整理历史而自行执行交互式 rebase 或强制推送。

PR 合并后，在本地同步最新 `main`：

```bash
git switch main
git pull --ff-only origin main
```

如果 `git pull --ff-only` 失败，通常表示本地 `main` 有远端不存在的提交。**不要改用强制推送，也不要在不理解影响时重置分支；先运行 `git status` 和 `git log --oneline --decorate -10` 查看情况并寻求帮助。**

确认工作已经合入后，可以删除本地分支：

```bash
git branch -d docs/git-workflow
```

远端分支可在 GitHub PR 页面删除，或执行 `git push origin --delete docs/git-workflow`。如果 PR 使用 Squash 合并，`git branch -d` 可能仍提示分支“未完全合并”；只有在 GitHub 上确认 PR 已合并、提交已进入 `main` 且分支不再需要后，才可以改用 `git branch -D docs/git-workflow`。**不要使用 `git branch -D` 强制删除尚未合并或状态不确定的工作。**

### 5.3 一套完整流程速查

下面的命令概括了一项普通任务从开始到结束的过程：

```bash
# 1. 从最新 main 创建任务分支
git switch main
git pull --ff-only origin main
git switch -c docs/git-workflow

# 2. 修改和测试后，检查并提交
git status
git diff
git add docs/DEVELOPMENT.md
git diff --staged
git commit -m "docs: explain git workflow for beginners"

# 3. 第一次推送并创建 PR
git push -u origin docs/git-workflow

# 4. PR 合并后，同步本地 main 并删除本地任务分支
git switch main
git pull --ff-only origin main
git branch -d docs/git-workflow
```

命令中的分支名、文件路径和提交信息都只是示例，使用时必须替换为当前任务的实际内容。

## 6. 依赖与 Kernel 升级

- 生产依赖必须固定兼容范围；私有 kernel 在形成版本发布前固定到完整提交 SHA。
- 升级 kernel 单独提交，并按照 [KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md)执行回归验证。
- 新依赖应说明用途、维护状态、许可证/安全影响和不使用它的代价；能用标准库清晰实现时不新增依赖。

## 7. 完成定义

一项工作只有在代码、测试、文档、配置和验收说明彼此一致时才算完成。未实现、未验证或只在本机成立的能力必须明确标注，不能写入“已完成”列表。
