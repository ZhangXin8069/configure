# AGENTS.md — configure 仓库总览

个人 shell/点文件配置仓库（ZhangXin）。为多台机器（工作站、笔记本、HPC 集群、容器、云端）提供版本化 shell 配置、工具脚本与环境引导。

## 入口与加载链

`env.sh` 被 **source**（不可直接执行），由 `~/.zshrc` 与 `~/.bashrc` 引入（`[ -r ]` 存在才 source，避免缺失报错），负责：

1. 将 `bin/`、`~/.opencode/bin`、`~/.local/bin` 等前置到 `PATH`（**防重复**：已含仓库 `bin` 前缀则跳过，可安全多次 source）
2. 设置 `LD_LIBRARY_PATH`（仓库 `lib/` 优先，防重复规则同 PATH）
3. 检测 UTF-8 locale：`LANG` 已是 UTF-8 时跳过；否则单 `grep -im1` 查 `C.UTF-8`/`en_US.UTF-8`
4. source `lib/_git_aliases.sh`（git 别名；zsh 专有别名 `gk/gke/globurl/gtl/gup*` 按 `$ZSH_VERSION` 分支定义，bash 下自动补 `git_current_branch`/`git_main_branch`/`git_develop_branch` 与 `ggu` 函数兜底）
5. 定义两 shell 通用别名（导航/grep/ls 系/常用工具；`history=omz_history`、`which-command=whence` 仅 zsh 下定义，按 `$ZSH_VERSION` 分支）

点文件部署：`bin/sh_init.sh [-b|-z|-a]`——`-b` 仅部署 bashrc；`-z` 部署 zshrc 与 oh-my-zsh（默认）；`-a` 全部；旧文件备份带时间戳。

## 目录结构

| 路径 | 用途 |
|---|---|
| `env.sh` | 环境主入口（shell 启动时被 source）：PATH/LD_LIBRARY_PATH（防重复）、locale、git 别名、两 shell 通用别名 |
| `bin/` | 工具脚本，`env.sh` 将其加入 PATH 后直接按名调用；op 系列（OpenCode，`oopencode.sh`/`oopencode-snsc.sh`/`oopencode.bat`，支持 `-file`+`-time`）与 co 系列（Codex，`ccodex.sh`/`ccodex-snsc.sh`/`ccodex.bat`）支持无人值守驱动模式，详见 `bin/AGENTS.md` |
| `lib/` | 版本化环境配置与基础模板 |
| `lib/{name}-v{YYYYMMDD}/` | 带版本日期的环境配置 |
| `skills/` | agent 技能（init、tag、debug、optim、diff、auto、all、analy、make、plan、review、skill-creator、tdd、test、up、brainstorm），`{~skill-name}` 触发 |
| `docs/` | 参考文档、包清单、图片素材 |
| `hooks/` | Codex agent hook 适配层与独立 Git 质量门禁；不会自动修改 Codex 配置或 `core.hooksPath` |
| `plugins/` | Codex 插件推荐索引与显式安装器；不自动安装第三方插件 |
| `tools/` | 配置仓库维护工具与上游工具推荐信息 |
| `lib/_clash/` | Clash 代理环境安装包包装目录；`setup.sh --check` 仅检查，默认执行会解压覆盖子目录 |

## 外部组件边界

`lib/_clash/clash-for-linux` 是 Git 索引中的外来 gitlink，上游自身的实现细节不属于本仓库维护范围；本仓库只通过父目录的 `lib/_clash/setup.sh` 解压和检查它。父脚本使用 `BASH_SOURCE` 与 Git 根目录动态定位，检查入口为 `bash lib/_clash/setup.sh --check`；需要代理环境时由子目录的 `env.sh` 提供 `source env.sh --status` 检查。

## 版本化配置约定（lib/{name}-v{YYYYMMDD}/）

- 更新配置时**新建**带当天日期的目录，不改旧目录（旧版保留作历史参考）
- `env.sh` 用 `@SECTION@`（单@，激活块）/ `@@SECTION@@`（双@，注释块）标记分节
- 安装命令首次运行后保留为注释，只留生效的 export，保证可复现

## 命令

- 无构建/lint/测试框架（纯 shell 脚本），校验脚本语法用 `bash -n <script>`
- 提交前无强制检查；仓库内 `.agent.*.log` 为 opencode/Codex 运行日志，不入库
