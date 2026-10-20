# 条件式自动提交、推送与标签

本规则是用户明确授予的常驻交付策略。只有全部前置闸门都通过时，agent 才能不再次询问而提交、推送和创建
非破坏性标签。任何未知项按失败处理。

## 1. 授权边界

允许：

- 按本任务明确路径暂存和提交；
- 向当前分支的正常 upstream 执行 fast-forward push；
- 创建并推送本次新建的 `dev/stab/bug/test` 注释标签；
- 将 `log` 技能生成的阶段/最终日志随任务一并提交。

不允许：

- `git add -A`、`git add .` 或提交未核对文件；
- force push、删除远端分支、改写或删除已推送标签；
- 覆盖其他用户或 agent 的改动；
- 提交敏感信息、凭据、超限文件或不应入库的生成物；
- 在测试失败、验收不明或远程分叉时“先提交再说”；
- 把本授权扩展到系统配置、仓库外路径或用户明确禁止的动作。

## 2. 交付闸门

| 闸门 | 通过条件 | 证据 |
|---|---|---|
| 阶段完成 | 阶段目标和验收标准全部达成 | 本次测试、检查或运行输出 |
| 正确性 | 相关回归、语法、lint/typecheck 均通过 | 命令、退出码、关键输出 |
| 范围 | 只包含本阶段文件 | `git status --short`、逐文件 diff |
| 完整性 | 无冲突标记、调试残留、意外二进制或重命名问题 | `git diff --check`、定向审查 |
| 安全 | 无密钥、令牌、密码、Cookie、私有环境变量原值 | 暂存 diff、仓库安全扫描器（可用时） |
| 大小 | 每个暂存文件小于 `10,000,000` 字节 | `form-large-files-check.sh` |
| 日志 | 阶段/最终日志已由 `log` 写入并含完整报告 | `logs/` 文件和索引 |
| Git 状态 | 无 merge/rebase/bisect/cherry-pick 未完成状态 | `git status`、Git 元数据 |
| 远程状态 | 目标远程分支是当前 `HEAD` 的祖先，可 fast-forward | `git fetch`、`merge-base --is-ancestor` |
| 并发安全 | 无其他用户/agent 正在同一文件或同一交付线写入 | 工作树状态、隔离记录 |
| 可恢复性 | 提交只增加历史，不删除或重写已有提交 | 分支关系和 push 类型 |

## 3. 执行顺序

```bash
repo_root=$(git rev-parse --show-toplevel)
branch=$(git -C "$repo_root" branch --show-current)

test -n "$branch"
git -C "$repo_root" diff --check
git -C "$repo_root" status --short
git -C "$repo_root" fetch --prune origin
git -C "$repo_root" merge-base --is-ancestor "refs/remotes/origin/$branch" HEAD

# 逐个列出本任务文件；不得使用 -A 或 .
git -C "$repo_root" add -- path/to/file-a path/to/file-b
git -C "$repo_root" diff --cached --check
git -C "$repo_root" diff --cached --stat
git -C "$repo_root" diff --cached --name-status
"$RULE_SKILL_DIR/../form/scripts/form-large-files-check.sh" --root "$repo_root"

git -C "$repo_root" commit -m '<type(scope): concise verified outcome>'
git -C "$repo_root" push origin "$branch"
```

提交前人工核对 `git diff --cached`，确认没有:

- `.env`、私钥、token、认证头、Cookie 或完整环境变量；
- 临时日志、缓存、大型数据、模型权重或生成目录；
- 其他任务和用户的改动；
- 冲突标记、调试打印、临时禁用测试或跳过验证；
- 与提交消息不一致的文件。

## 4. 远程分支策略

`merge-base --is-ancestor` 通过表示当前 `HEAD` 已包含远程分支最新提交，push 可 fast-forward。失败时：

1. 不提交前自动 pull/rebase/reset；
2. 检查远程新提交是否触碰本任务文件；
3. 仅在不覆盖改动且可安全整合时使用 `git pull --ff-only` 或单独的非破坏性整合方案；
4. 重新运行完整验证；
5. 仍无法安全 fast-forward 时停止自动推送并报告分叉。

禁止用 force push 解决分叉，禁止把其他人的改动“收拾”进本任务提交。

## 5. 标签策略

标签使用 `tag` 技能的类型推断、历史链自检和消息格式，并遵守以下边界：

| 阶段 | 标签 | 条件 |
|---|---|---|
| 进行中检查点 | `dev` | 提交可复用且后续可能从该点继续 |
| 稳定里程碑 | `stab` | 阶段完整、稳定、验收通过 |
| 已修复缺陷 | `bug` | 原失败路径回归通过 |
| 测试里程碑 | `test` | 测试体系或关键回归完成并验证 |

类型明确、历史链自检通过且当前提交为期望目标时，可创建并推送本次新标签。出现以下任一情况时不打标签：

- 类型存在歧义；
- 历史链断链或存在无法自动判断的修复；
- 目标提交和验收提交不一致；
- 远程已有同名标签或对象漂移；
- 需要删除、移动或改写已有标签。

## 6. 失败处理

- 验证失败：不暂存、不提交；进入 `debug` 和 `test`。
- 范围混杂：只保留本任务路径，其他改动原样不动；无法分离则停止。
- 大文件：立即停止该批提交和推送；不自动删除用户文件。
- 敏感信息：停止提交，清理并轮换已暴露凭据（按用户授权范围执行）。
- 远程分叉：停止 push，报告本地提交和远程差异。
- push 失败：本地提交保留，报告认证、网络或保护规则问题。
- 标签失败：不影响已验证提交；报告标签未创建或未推送。

无论失败还是成功，终端摘要都必须明确本地提交、远程 push、标签和日志的真实状态，不把“已提交”写成“已推送”。
