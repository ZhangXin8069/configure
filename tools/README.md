# 推荐工具项目

本目录用于放置仓库维护工具。第三方工具只记录推荐来源，不把二进制或上游源码 vendoring 进配置仓库；实际安装由用户按机器和发行版自行决定。

## 本地项目

### `configure-check.sh`

只读检查当前配置仓库的四棵 agent 配置树（`skills/`、`tools/`、`hooks/`、`plugins/`）：检查技能 frontmatter、技能目录说明和技能表登记，检查 `skills/`、`tools/` 与 `hooks/` 中 Shell 脚本的语法和执行权限，以及已有 Codex 插件 manifest 的基本 JSON/name/version/path 完整性。

```bash
tools/configure-check.sh
tools/configure-check.sh --root /path/to/configure
tools/configure-check.sh --strict
```

退出码为 `0` 表示没有发现问题，`1` 表示发现结构或语法问题，`2` 表示命令行参数错误。`--strict` 将“没有可直接加载插件 manifest”等警告也提升为失败，适合 CI 门禁。工具不执行 hook、plugin 或安装命令；存在插件 manifest 时使用 Python 3 的标准库解析 JSON，并使用系统临时目录保存 NUL 路径清单后自动清理。

回归测试：

```bash
bash tools/configure-check.test.sh
```

### `coverage-report.sh`

只读汇总当前仓库四棵配置树的覆盖状况，输出 `skills/`、`tools/`、`hooks/`、`plugins/` 的摘要、`skills/` 与 `.opencode/skills/` 的镜像一致性线索，以及缺口提示。它复用 `configure-check.sh` 的发现思路，但不做门禁判定：数据缺口只会出现在报告里，不会把脚本本身变成失败入口。

```bash
tools/coverage-report.sh
tools/coverage-report.sh --root /path/to/configure
```

退出码为 `0` 表示报表成功生成，`2` 表示命令行参数错误。插件 manifest 仍会按 `configure-check.sh` 的规则做 JSON/路径诊断，因此需要 `python3` 可用；其余部分只依赖 Bash、`find`、`sort`、`cmp`、`grep` 和 `sed`。

回归测试：

```bash
bash tools/coverage-report.test.sh
```

### `task-scope.sh`

只读任务分流入口：把自然语言任务分类为合适的技能组合，并给出可并行拆分建议。它不读仓库、不改仓库，也不执行子技能，只输出分类、推荐技能链、拆分建议和依据。

```bash
tools/task-scope.sh "创建 coverage-report.sh、task-scope.sh，并更新 README"
printf '%s\n' "排查 coverage-report 在缺少 AGENTS.md 时的报错，并修复后回归测试" | tools/task-scope.sh
tools/task-scope.sh --task "先帮我评估这个分类器的可行性，再给出实现计划"
```

退出码为 `0` 表示成功分类，`2` 表示参数错误或缺少任务文本。脚本依赖 Bash、`sed`、`tr` 等基础命令，不依赖仓库状态。

回归测试：

```bash
bash tools/task-scope.test.sh
```

## 上游推荐

| 项目 | 来源 | 推荐用途 | 本库定位 |
|---|---|---|---|
| ripgrep (`rg`) | [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | 快速、可递归、默认尊重 ignore 规则的文本搜索；也是 `up` 流程优先使用的搜索器 | 基础依赖，缺失时按技能中的回退方案处理 |
| ShellCheck | [koalaman/shellcheck](https://github.com/koalaman/shellcheck) | shell 静态分析，补充 `bash -n` 只能发现语法错误的局限 | 推荐用于提交前人工检查，不作为脚本运行时硬依赖 |
| shfmt | [mvdan/sh](https://github.com/mvdan/sh) | 统一 POSIX shell、bash、mksh 等脚本格式 | 推荐用于格式化变更后的 shell 文件，不自动改写仓库 |
| fd | [sharkdp/fd](https://github.com/sharkdp/fd) | 更易读的文件查找，适合交互式定位配置文件 | 可选交互工具，不参与检查器正确性 |
| fzf | [junegunn/fzf](https://github.com/junegunn/fzf) | 交互式筛选日志、技能和配置路径 | 可选交互工具，不作为 agent 自动流程依赖 |
| Agent Skills 参考实现 | [agentskills/agentskills](https://github.com/agentskills/agentskills) | 需要对外发布标准 Agent Skills 时，核对规范和参考校验工具 | 参考工具；本库仍以本地 `skills/AGENTS.md` 约定为准 |

## 选择原则

优先采用发行版或上游正式发布的可验证版本；安装前核对许可证、架构、更新日期和来源校验。`configure-check.sh` 仍是本目录唯一的门禁入口；`coverage-report.sh` 和 `task-scope.sh` 是只读诊断/建议入口，第三方工具均为可选能力，不会被它们自动下载或调用。
