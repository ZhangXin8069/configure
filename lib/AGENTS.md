# AGENTS.md — lib 环境配置库

版本化环境配置与基础点文件模板，用于向异构机器（工作站、笔记本、macOS、HPC 集群、GPU/NPU 节点、Docker 容器、云端）部署 ZhangXin 的 shell 环境。

## 目录组织

### 基础模板（`_` 前缀）

由 `bin/sh_init.sh` / `bin/vim_init.sh` 部署到 `$HOME` 的源文件：

| 目录 | 部署到 | 用途 |
|---|---|---|
| `_bashrc` | `~/.bashrc` | Bash 配置（交互检测/历史/PS1 含窗口标题+dircolors/补全/函数；末尾存在才 source env.sh） |
| `_zshrc` | `~/.zshrc` | Zsh 配置（oh-my-zsh + p10k instant prompt；存在才 source env.sh；`DISABLE_UNTRACKED_FILES_DIRTY` 勿启用，未跟踪文件需显示 ✗） |
| `_vimrc` | `~/.vimrc` | Vim 配置 |
| `_vim/` | `~/.vim/` | 完整 vim 运行时（plugged 插件、colors、UltiSnips、spell） |
| `_oh-my-zsh/` | `~/.oh-my-zsh/` | 完整 oh-my-zsh 安装（含 custom 插件/主题） |

仅参考不部署：`_docker/`（Docker 开发环境指南）、`_snsc/`（NSC 集群共享配置）、`_clash/`（Clash 代理环境安装包与 `setup.sh` 检查入口）、`_claude_code/`（指向 claude_code-v20260706 的符号链接兼容目录）、`_mac/`（macOS 更新开关脚本）、`_gitignore`（符号链接→仓库根 `.gitignore`，通用忽略模板：16 编号分节，含 C++/Java/PHP 等语言分节与「全局规则→树级放行→运行时例外」三层护栏）。

### 版本化环境配置（`{name}-v{YYYYMMDD}/`）

每个目录对应一个**具体运行环境**，核心文件为 `env.sh`（被 source 以设置该环境）。部分目录含 `setup.sh`（一次性安装命令）、`setup.md`（参考文档）、本地点文件或 Slurm 辅助脚本。

**版本规则**：需要更新配置时**新建**当天日期的目录，旧目录保留作历史参考。

## env.sh 分节约定

- `@SECTION@`（单@）— 激活块；`@@SECTION@@`（双@）— 注释掉的备选块
- 常见分节：`@MODULE@`（module load）、`@EXPORT@`（PATH/LD_LIBRARY_PATH/PYTHONPATH）、`@CONDA@`、`@ENV@`、`@ALIAS@`、`@SOURCE@`
- 安装命令（wget/tar/configure/make/pip）首跑后保留为**注释**，只留生效的 export，保证可复现
