# Git 配置操作

## 目标

配置 Git 用户名与邮箱，接入 SSH 认证，启用统一别名和忽略规则，并区分安全辅助命令与破坏性快捷命令。

## 身份配置

推荐直接设置最小必要项：

```bash
git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"
git config --global init.defaultBranch main
git config --global --get-regexp '^(user|init)\.'
```

`bin/git_init.sh` 会完成身份设置、生成 `~/.ssh/id_ed25519` 并打印公钥，但存在两个限制：

1. 身份值写死在脚本中，不适用于其他用户或邮箱。
2. `ssh-keygen` 不是幂等操作；已有同名密钥时会再次交互询问是否覆盖。

已有可用密钥时不要运行该脚本，直接按 [`../_ssh/setup.md`](../_ssh/setup.md) 验证和加载。

## 别名

`env.sh` 会加载 `lib/_git_aliases.sh`，提供 oh-my-zsh 风格的 Git 别名和 Bash 兜底函数。

```bash
source ~/configure/env.sh
alias gst
alias gco
type git_current_branch
type git_main_branch
```

常用别名：

| 别名 | 等价操作 |
|---|---|
| `gst` | `git status` |
| `gss` | `git status --short` |
| `gd` | `git diff` |
| `gco` | `git checkout` |
| `gsw` | `git switch` |
| `glo` | `git log --oneline --decorate` |
| `gp` | `git push` |
| `gl` | `git pull` |

## 忽略模板

`lib/_gitignore` 是指向仓库根 `.gitignore` 的符号链接。模板包含语言、系统、编辑器、密钥和本仓库历史规则。

将模板逐行精确补入当前仓库：

```bash
cd /path/to/repository
bash ~/configure/bin/gadd-ignore.sh
git diff -- .gitignore
git check-ignore -v <路径>
```

行为说明：

1. 只对完全相同的整行去重，不做语义去重。
2. 会连注释和分节标题一起追加。
3. 不删除现有规则。
4. 模板包含 `*build`、`*dist`、`*Makefile`、`*.c` 等覆盖范围较宽的仓库专属规则，复制到其他项目前必须逐条审核。

## 辅助命令风险分级

| 命令 | 行为 | 建议 |
|---|---|---|
| `gpull.sh` | fetch 后对当前分支执行 `pull --rebase --autostash origin <branch>`；旧版 Git 回退到兼容 stash 流程；detached HEAD 仅在提交已包含于唯一可判定的远端默认分支时恢复为跟踪分支，否则明确失败 | 可用于日常同步并保留 tracked 工作区改动；建议先检查 `git status --short --branch` |
| `gpush.sh` | `git add -A`、无信息校验地以时间戳提交、推送当前分支和全部标签 | 仅用于个人快照仓库，不用于需要审查的提交 |
| `gback.sh` | fetch 时使用 `--prune-tags --force`，随后硬重置到 upstream、执行 `git clean -fdx`，并删除远程已不存在的本地分支 | 破坏性操作；会删除本地独有标签并覆盖同名冲突标签，执行前自行备份 |
| `gpristine` 别名 | `git reset --hard && git clean -force -dfx` | 会删除未跟踪和忽略文件 |
| `gwipe` 别名 | `git reset --hard && git clean -force -df` | 会删除未跟踪文件，但保留忽略文件 |

`gback.sh` 删除的未跟踪文件通常无法通过 Git 恢复。`git reflog` 只能帮助恢复已提交对象，不能恢复被 `clean` 删除的文件。

## 推荐日常流程

```bash
git status --short --branch
git diff --check
git diff
git add path/to/file
git diff --cached
git commit
git push
```

需要同步远端时优先显式执行：

```bash
git fetch --all --prune
git pull --rebase
```

## 验证

```bash
bash -n bin/git_init.sh
bash -n bin/gadd-ignore.sh
bash -n bin/gpush.sh
bash -n bin/gpull.sh
bash -n bin/gback.sh
bash -n lib/_git_aliases.sh
git config --global --get user.name
git config --global --get user.email
```

SSH 连通性验证见 [`../_ssh/setup.md`](../_ssh/setup.md)。
