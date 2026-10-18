# Shell 配置操作

## 适用场景

在 Linux、macOS、HPC 集群、容器或 Termux 中部署本仓库维护的 Bash/Zsh 配置。该操作只修改当前用户的点文件，不需要 root。

## 文件关系

| 仓库文件 | 部署目标 | 作用 |
|---|---|---|
| `lib/_bashrc` | `~/.bashrc` | Bash 交互配置、历史、提示符、补全与本地扩展 |
| `lib/_zshrc` | `~/.zshrc` | Zsh、oh-my-zsh、主题、插件与提示符 |
| `lib/_oh-my-zsh/` | `~/.oh-my-zsh/` | 完整 oh-my-zsh 运行时 |
| `env.sh` | 不复制，被点文件 source | PATH、库路径、locale、Git 与通用别名 |

`env.sh` 必须被 `source`，不能直接执行。

## 前置检查

```bash
bash --version | head -1
zsh --version 2>/dev/null || true
git --version
printf 'HOME=%s\nSHELL=%s\n' "$HOME" "${SHELL:-}"
```

Zsh 默认部署需要系统已经安装 `zsh`。缺少 `git` 时，oh-my-zsh 自带插件不会完整工作。

本仓库部分 Bash 辅助脚本使用 Bash 4+ 特性。macOS 默认 Bash 3.2 可以执行基础配置，但 `save-env.sh`、部分 agent 状态栏和结构审计工具可能失败；需要完整功能时建议安装 Bash 5，并明确调用对应解释器。

## 部署

```bash
# 默认：部署 .zshrc 和 oh-my-zsh
bash bin/sh_init.sh

# 只部署 .bashrc
bash bin/sh_init.sh -b

# 部署 Bash、Zsh 与 oh-my-zsh
bash bin/sh_init.sh -a
```

部署逻辑具有以下行为：

1. 目标已存在时，先移动为 `<目标>.<YYYY-MM-DD-HH-MM-SS>.bak`。
2. 随后从仓库复制新文件或目录。
3. 重复执行不会“原地更新”，而是继续生成带时间戳的备份。
4. 默认模式 `-z` 不部署 `.bashrc`。
5. `zsh` 不存在时会跳过 `.zshrc`；`lib/_oh-my-zsh` 缺失时会跳过 oh-my-zsh，两个检查彼此独立。

## 启动链

```text
~/.bashrc 或 ~/.zshrc
  -> ~/configure/env.sh
  -> bin/ 与 ~/.local/bin 进入 PATH
  -> lib/_git_aliases.sh
  -> 通用别名与环境变量
```

两个点文件还会按以下顺序 source 本机文件：

```text
~/configure/env.sh
~/env-key.sh
~/env.sh
```

后加载的文件可以覆盖前面的变量。API key、令牌和其他敏感值只应放在权限受控的 `~/env-key.sh`，不要写入仓库。

需要从已有环境恢复时，`lib/set-env.sh` 会按 `.bashrc`、`~/.env.sh`、仓库 `env.sh`、`~/env.sh` 的顺序加载。该脚本必须 source，并且自动生成环境快照时可能包含密钥；完整边界见 [`../_env/setup.md`](../_env/setup.md)。

## 本机扩展

| 需求 | 推荐位置 |
|---|---|
| Bash 私有别名 | `~/.bash_aliases`，`_bashrc` 会自动加载 |
| Shell 密钥与令牌 | `~/env-key.sh`，建议权限 `600` |
| 机器专属环境变量 | `~/env.sh`，由版本化 `env.sh` 复制或手工维护 |
| 可跨机器复用的别名和函数 | 仓库 `env.sh`、`lib/_bashrc`、`lib/_zshrc` |
| Git 别名 | `lib/_git_aliases.sh` |

当前没有自动加载 `~/.zshrc.local` 的钩子。需要 Zsh 私有配置时，应在 `lib/_zshrc` 中增加明确的 source 行，然后重新部署。

## 环境快照

`bin/save-env.sh` 可把当前环境导出为可 source 的文件：

```bash
umask 077
bash bin/save-env.sh ./env.local.sh TERM DISPLAY
```

该脚本会导出大部分环境变量，输出文件可能包含 API key、令牌和代理凭据。执行前应设置 `umask 077`，生成后检查内容，禁止提交真实密钥。

兼容性限制：脚本使用 `mapfile` 和 `env -0 | sort -z`，需要 Bash 4+ 与 GNU `sort`。macOS 默认 Bash 3.2 和 BSD `sort` 不满足要求，会失败或产生不完整结果；应改用 Bash 5 + GNU coreutils，或手工维护最小环境文件。

## 验证

```bash
bash -n bin/sh_init.sh
bash -n env.sh
bash -n lib/_git_aliases.sh
env -i HOME="$HOME" PATH="$PATH" bash --noprofile --norc -c \
  'source ./env.sh && command -v git && printf "%s\n" "$PATH"'
```

交互验证：

```bash
bash -ic 'type ll; type grep; command -v gpush.sh'
zsh -ic 'type ll; type history; command -v co' 2>/dev/null || true
```

## 回滚

查看备份并按时间恢复：

```bash
ls -1dt ~/.bashrc.*.bak ~/.zshrc.*.bak ~/.oh-my-zsh.*.bak 2>/dev/null
mv ~/.zshrc ~/.zshrc.failed
mv ~/.zshrc.<时间戳>.bak ~/.zshrc
```

恢复后重新打开终端。不要删除唯一备份，确认新配置稳定后再手工清理旧备份。
