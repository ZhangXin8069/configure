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

## 忽略规则生成与历史清理

仓库根 `.gitignore` 是唯一权威规则。`give_git_ignore.sh`
扫描当前工作区已有的跟踪文件和未忽略文件，生成“默认忽略、保留现有无后缀文件与扩展名、
忽略隐藏项并保留常用配置”的白名单式规则。它同时生成 `data/.gitignore`、`logs/.gitignore` 和
`docs/.gitignore`，分别落实运行时数据、日志和文档子目录边界。

先预览，再写入并复查：

```bash
cd /path/to/repository
bash ~/configure/bin/give_git_ignore.sh -n
bash ~/configure/bin/give_git_ignore.sh
git diff -- .gitignore data/.gitignore logs/.gitignore docs/.gitignore
git check-ignore -v <路径>
```

未加 `-f` 时会备份已有规则；`-sub` 只更新三个子目录规则，`-k` 可追加精确保留模式。
生成结果依赖当前工作区中已经存在的扩展名和无后缀入口，引入新文件类型后应重新生成并审查，
不能把一次生成结果视为永久语言模板。

`grm-ignore.sh` 不是“移出当前索引”命令。它依据仓库内全部 `.gitignore` 规则，通过
`git filter-repo` 永久重写所有分支、标签和远程跟踪分支，默认还会 force push 并 GC。
仅在明确要求清理已提交的忽略内容时使用，并要求全新 clone、`-n` 预览、备份和破坏性授权：

```bash
bash ~/configure/bin/grm-ignore.sh -n
```

需要 `git-filter-repo`。协作者必须重新 clone；普通 `git pull` 无法兼容重写后的历史。

## 辅助命令风险分级

| 命令 | 行为 | 建议 |
|---|---|---|
| `gpull.sh` | 自动识别 `origin` 为 HTTPS、SSH 或本地路径；fetch 后仅允许 fast-forward，旧版 Git 回退到兼容 stash 流程；分叉历史在 stash/rebase 前停止；detached HEAD 仅在提交已包含于唯一可判定的远端默认分支时恢复为跟踪分支 | 可用于日常同步并保留 tracked 工作区改动；建议先检查 `git status --short --branch` |
| `gpush.sh` | 仓库包含 `data/` 时先运行数据边界检查；随后 `git add -A`、无信息校验地以时间戳提交、推送当前分支和全部标签 | 仅用于个人快照仓库，不用于需要审查的提交；data 检查失败会阻止暂存、提交和推送 |
| `give_git_ignore.sh` | 按当前工作区生成根和子目录 `.gitignore`，保留已有点文件、扩展名与精确入口 | 先用 `-n` 预览；默认会备份，`-f` 才直接覆盖 |
| `grm-ignore.sh` | 从全部 Git 历史永久删除被忽略文件，默认覆盖远程并 GC | 仅限明确授权的新 clone；普通 `git pull` 无法恢复协作 |
| `gback.sh` | fetch 最新 upstream；先 stash 本地提交与工作区，保存已注册子模块指针；子模块内部有未提交状态时中止；确认 stash 后才 `reset --hard` 并 `clean -fdx` | 强制对齐但保留 stash；未注册 gitlink 不参与子模块遍历，不会自动 pop |
| `gpristine` 别名 | `git reset --hard && git clean -force -dfx` | 会删除未跟踪和忽略文件 |
| `gwipe` 别名 | `git reset --hard && git clean -force -df` | 会删除未跟踪文件，但保留忽略文件 |

`gback.sh` 会把当前分支的本地分叉和全部工作区状态放入新的 `stash@{0}`，然后才清理工作区。若 stash 失败或 stash 后仍有残留文件，脚本会中止 reset。恢复时可查看 `git stash show --include-untracked -p stash@{0}`，或用 `git stash branch <new-branch> stash@{0}` 重建原分支。其他本地分支和标签不会被删除。

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

需要同步远端时优先执行：

```bash
gpull.sh
```

`gpull.sh` 不自动 rebase 或 merge 分叉历史。若提示本地分支与 `origin/<branch>` 分叉，先检查两侧提交；确定要 rebase 时再配置 `user.name`/`user.email` 并手动执行。

## 验证

```bash
bash -n bin/git_init.sh
bash -n bin/give_git_ignore.sh
bash -n bin/grm-ignore.sh
bash -n bin/gpush.sh
bash -n bin/gpull.sh
bash -n bin/gback.sh
bash -n bin/gback.test.sh
bash bin/gback.test.sh
bash -n lib/_git_aliases.sh
git config --global --get user.name
git config --global --get user.email
```

SSH 连通性验证见 [`../_ssh/setup.md`](../_ssh/setup.md)。
