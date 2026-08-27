# 推荐工具项目

本目录用于放置仓库维护工具。第三方工具只记录推荐来源，不把二进制或上游源码 vendoring 进配置仓库；实际安装由用户按机器和发行版自行决定。

## 本地项目

### `configure-check.sh`

只读检查当前配置仓库的四棵 agent 配置树（`skills/`、`tools/`、`hooks/`、`plugins/`）：检查技能 frontmatter、技能目录说明，检查 `tools/` 与 `hooks/` 中 Shell 脚本的语法和执行权限，以及已有 Codex 插件 manifest 的基本 JSON/name/version/path 完整性。

```bash
tools/configure-check.sh
tools/configure-check.sh --root /path/to/configure
```

退出码为 `0` 表示没有发现问题，`1` 表示发现结构或语法问题，`2` 表示命令行参数错误。工具不执行 hook、plugin 或安装命令；存在插件 manifest 时使用 Python 3 的标准库解析 JSON。

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

优先采用发行版或上游正式发布的可验证版本；安装前核对许可证、架构、更新日期和来源校验。`configure-check.sh` 是本目录唯一的本地运行入口，第三方工具均为可选能力，不会被它自动下载或调用。
