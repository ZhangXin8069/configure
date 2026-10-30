# configure form 治理记录（2026-10-31）

## 目标与范围

本轮 form 治理只处理 `configure` Git 仓库：核验目录与命名、文档/日志/数据边界、测试入口、
form 快照、`skills/` 与 `.opencode/skills/` 镜像一致性，以及 `refer/git-rep` 参考子库基线。
不修改仓库外全局 agent 配置，不执行 force push、不删除或改写历史标签。

## 初始证据

- 起始分支与提交：`main`，`b9b0fbedd3f633259c6d6af41ddf830daa0a1991`。
- 起始工作树与暂存区均为空，未跟踪文件为零。
- 起始版本标签基线：`stab84`，peeled commit `93c1974`。
- `form-audit.sh --strict --quiet` 在排除镜像重复副本后仅命中 `logs/.gitignore` 的旧扩展名规则；
  未发现单数 `AGENT.md`、`data/` 跟踪越界或参考 submodule/gitlink 元数据错误。
- `form-snapshot-verify.sh --quiet` 复现 `configure-main symlink inventory mismatch`：清单要求
  15 个软链接，权威快照目录实际只有 9 个，缺少 `cl/cls/co/cos/op/ops`。
- `tools/configure-check.sh --strict` 复现 5 个 form 镜像错误：4 个旧文件内容漂移和
  `form-data-tracking-check.sh` 缺失；修复首轮镜像后，普通模式为 0 error、1 个预期插件索引 warning。

## 根因与整改

| 对象 | 根因 | 整改 |
|---|---|---|
| `skills/form` 与 `.opencode/skills/form` | 权威技能更新后未完整同步镜像 | 从 `skills/form/` 全量复制，`configure-check.sh` 核对一致 |
| `configure-main` 快照软链接 | `.gitignore` 的全局后缀白名单未放行 6 个无后缀 vendored 入口 | 恢复 6 个软链接，并在 `give_git_ignore.sh` 中精确保留源/镜像路径 |
| `logs/.gitignore` | 生成器写成 `!.txt`，只匹配字面 `.txt`，不能放行普通日志文件 | 改为 `!*.txt`，回归测试验证时间戳日志不被忽略 |
| form 审计重复扫描 | `.opencode/**` 是权威技能镜像，原审计将其当作第二业务源 | form 审计显式跳过镜像副本，继续由 `configure-check.sh` 检查一致性 |
| form 审计目录契约 | `docs/.gitignore` 与 `logs/.gitignore` 是生成控制文件，原规则未登记 | 在本地 form 规则和审计脚本中登记最小例外 |
| 镜像软链接检查 | `configure-check.sh` 只枚举普通文件，软链接目标漂移不可见 | 同时枚举软链接、比较目标，并增加漂移回归用例 |
| 子 agent 默认 prompt | `agent-dispatch.sh` 继承了父运行的内部 `AGENT_DISPATCH_MINIMAL=0` | 将 `--full` 限定为单次派发选项，默认始终使用最小 prompt |
| 核心 agent 入口 | `.gitignore` 未保留无后缀启动器，新克隆缺失 `cl/cls/co/cos/op/ops` | 恢复 6 个软链接，并在 `give_git_ignore.sh` 及回归测试中精确放行 |
| JSON hook 超时输出 | 秒级预算边界耗尽时，事件写入未启动且 detail/超时原因丢失 | 在返回 124 前输出已捕获 detail 和明确硬超时消息 |
| 测试父环境隔离 | 测试继承父 agent 的 auto-resume、dispatch 与 TUI 状态 | 在测试入口清除内部变量，按用例显式启用恢复 |
| 工具缓存暴露 | 目录再包含规则位于 `.cache/` 忽略前，`.json` 等白名单把缓存重新放行 | 在任何后缀例外之后忽略 `.cache/` 与 `__pycache__/`，并增加回归 |

## 功能验证

以下命令均以有限 `timeout` 运行并返回 0：

```bash
bash -n bin/give_git_ignore.sh bin/give_git_ignore.test.sh \
  tools/configure-check.sh tools/configure-check.test.sh \
  skills/form/scripts/form-audit.sh skills/form/scripts/form-scripts.test.sh
bash bin/give_git_ignore.test.sh
bash tools/configure-check.test.sh
bash skills/form/scripts/form-scripts.test.sh
bash skills/form/scripts/form-snapshot-verify.sh --quiet
bash skills/form/scripts/form-audit.sh --root . --strict --quiet
bash tools/configure-check.sh
bash hooks/hooks.test.sh
bash bin/agent.test.sh
python3 tools/agent-tui-watch.test.py
git diff --check
```

全量回归覆盖 `bin/`、`hooks/`、`plugins/`、`skills/`、`tools/` 与 `lib/_opencode/` 的测试入口；
维护脚本静态检查覆盖 181 个 Bash 文件和 21 个 Python 文件。`hooks/hooks.test.sh` 的 JSON 事件
超时路径在修复后连续 5 次通过。PowerShell Parser 因本机无 `powershell.exe`/`pwsh.exe` 跳过。

`tools/configure-check.sh --strict` 仍会因“`plugins/` 只有推荐索引、没有本地可加载 manifest”的
预期 warning 返回非零；普通门禁已确认该 warning 不计为 error。该 warning 不通过删除推荐索引规避。

## 恢复方式

- `skills/` 是唯一权威源；`.opencode/skills/` 存在时可由 `cp -a skills/form/. .opencode/skills/form/`
  重建，不存在时无需创建。
- init 已清理仓库内 `.opencode/`，`lib/_deepseek/.codex/` 是安装模板并明确保留。
- `.gitignore` 由 `bin/give_git_ignore.sh -f` 可重建；其 form 快照软链接例外和 `logs` 规则由脚本
  与回归测试共同保证。
- 文档与日志均为普通 Git 文件，可通过验收提交或 `git show <revision>:<path>` 恢复。

## 后续阶段

第二次 `~diff` 与 `~debug` 已完成；本记录完成后继续归档 `~log`、fast-forward push 和
`dev` 注释标签交付。最终提交、推送与回读结果以任务终态报告为准。
