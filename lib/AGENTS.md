# AGENTS.md — lib 环境配置库

版本化环境配置与基础点文件模板，用于向异构机器（工作站、笔记本、macOS、HPC 集群、GPU/NPU 节点、Docker 容器、云端）部署 ZhangXin 的 shell 环境。

`requirements/` 保存 `apt_install.sh` 与 `pip_install.sh` 消费的功能输入清单，不放入
`docs/`；清单采用一行一个包，`#` 起始行或行尾注释由安装脚本按各自规则处理。

## 目录组织

### 稳定入口与基础模板（`_` 前缀）

`_` 前缀承担两类职责：

1. 由初始化脚本部署到 `$HOME` 的源文件或运行时目录。
2. 面向用户的操作说明、安装脚本、资源和稳定入口，不随登录自动部署。

部署源：

| 目录 | 部署到 | 用途 |
|---|---|---|
| `_bashrc` | `~/.bashrc` | Bash 配置（交互检测/历史/PS1 含窗口标题+dircolors/补全/函数；末尾存在才 source env.sh） |
| `_zshrc` | `~/.zshrc` | Zsh 配置（oh-my-zsh + p10k instant prompt；存在才 source env.sh；`DISABLE_UNTRACKED_FILES_DIRTY` 勿启用，未跟踪文件需显示 ✗） |
| `_vimrc` | `~/.vimrc` | Vim 配置 |
| `_vim/` | `~/.vim/` | Vim 运行时（autoload、colors、运行目录；plugged 为未配置 `.gitmodules` 的 gitlink） |
| `_oh-my-zsh/` | `~/.oh-my-zsh/` | 完整 oh-my-zsh 安装（含 custom 插件/主题） |

稳定操作入口：

| 目录 | 用途 |
|---|---|
| `_agent/` | `cl/cls/op/ops/co/cos` 配置分层、密钥、派发、运行状态 |
| `_clash/` | Clash 离线归档、解压检查和代理启用边界 |
| `_claude-code/` | Claude Code / cc-switch 安装、配置、离线下载和卸载 |
| `_codex/` | Codex CLI 安装、配置、provider 协议与认证 |
| `_commands/` | `bin/` 用户命令总索引及跨主题风险说明 |
| `_deepseek/` | DeepSeek 的 Claude Code、Codex 与桌面端配置 |
| `_docker/` | Docker Desktop、GPU、镜像和容器生命周期 |
| `_env/` | 环境入口、机器版本快照、本机覆盖和自动恢复边界 |
| `_font/` | Linux/Windows 字体安装、授权和刷新 |
| `_git/` | Git 身份、别名、忽略模板和辅助命令风险 |
| `_linux/` | Linux 包、Swap、调频、电源和系统入口 |
| `_mac/` | macOS 更新、Gatekeeper、Keychain 与维护脚本 |
| `_opencode/` | OpenCode 安装、V1/V2 配置分流与插件 |
| `_package/` | APT/Python 清单和随库可执行资源 |
| `_shell/` | Bash/Zsh/oh-my-zsh 部署、启动链和本机覆盖 |
| `_slurm/` | Slurm 用户命令与 DCU 作业模板 |
| `_snsc/` | SNSC 集群 VS Code Server sysroot 兼容 |
| `_ssh/` | SSH 密钥、agent、主机别名与快捷入口 |
| `_vim/` | Vim 部署、gitlink 插件状态、验证和回滚 |
| `_vscode/` | VS Code Remote Server 清理与兼容入口 |
| `_windows/` | Windows 批处理、PowerShell、PATH 与安装前提 |
| `_zerotier/` | ZeroTier 安装、授权、验证和固定网络参数 |

其他稳定入口：

- `_gitignore` 是符号链接，指向仓库根 `.gitignore`；模板包含语言、系统、编辑器、密钥和本仓库历史规则。
- `_ohmyzsh_install.sh` 保留上游安装流程，用于离线目录不可用时的替代安装。
- `_claude-code/` 与 `claude-code-v20260706/` 的脚本文件当前都是真实副本；修改脚本行为时应先改版本化维护源，再同步稳定目录。稳定目录 `setup.md` 已完成文档重构，版本化目录中的历史说明保留原状。

操作文档只描述现有脚本和模板，不改变其行为。涉及删除、硬重置、系统升级、重启、密钥覆盖或凭据删除时，文档必须明确风险，执行仍由用户单独确认。

### 版本化环境配置（`{name}-v{YYYYMMDD}/`）

每个目录对应一个**具体运行环境**，核心文件为 `env.sh`（被 source 以设置该环境）。部分目录含 `setup.sh`（一次性安装命令）、`setup.md`（参考文档）、本地点文件或 Slurm 辅助脚本。

**版本规则**：需要更新配置时**新建**当天日期的目录，旧目录保留作历史参考。

## env.sh 分节约定

- `@SECTION@`（单@）— 激活块；`@@SECTION@@`（双@）— 注释掉的备选块
- 常见分节：`@MODULE@`（module load）、`@EXPORT@`（PATH/LD_LIBRARY_PATH/PYTHONPATH）、`@CONDA@`、`@ENV@`、`@ALIAS@`、`@SOURCE@`
- 安装命令（wget/tar/configure/make/pip）首跑后保留为**注释**，只留生效的 export，保证可复现
