# 用户命令总索引

`bin/` 由 `env.sh` 加入 `PATH`。本文覆盖配置类文档之外的用户命令，避免把“可定制操作”限制在安装和点文件。

## 日常入口

| 场景 | 命令 | 说明 |
|---|---|---|
| Shell 部署 | `sh_init.sh` | 见 `../_shell/setup.md` |
| 环境恢复 | `lib/set-env.sh` | 见 `../_env/setup.md`，必须 source |
| Vim 部署 | `vim_init.sh` | 见 `../_vim/setup.md` |
| Git 初始化 | `git_init.sh` | 见 `../_git/setup.md` 与 `../_ssh/setup.md` |
| Git 同步 | `gpull.sh`、`gpush.sh`、`gback.sh` | 见 `../_git/setup.md`，其中 `gback.sh` 为破坏性操作 |
| SSH | `ss.sh`、`ssnsc.sh`、`ssjtu.sh`、`xx99.sh` | 见 `../_ssh/setup.md` |
| Slurm | `ssub.sh`、`ssrun.sh`、`ssqueue.sh`、`zsqueue.sh`、`sstop.sh` | 见 `../_slurm/setup.md` |
| Docker | `ddocker.sh`、`ddocker.bat` | 见 `../_docker/setup.md` |
| Agent | `cl/cls/op/ops/co/cos` | 见 `../_agent/setup.md` |
| ZeroTier | `zerotier_init.sh` | 见 `../_zerotier/setup.md` |
| 包管理 | `apt_install.sh`、`pip_install.sh`、`apt_up.sh` | 见 `../_package/setup.md` |
| VS Code Remote | `vscode_unset.sh` | 见 `../_vscode/setup.md` |
| macOS quarantine | `xxattr.sh` | 见 `../_mac/setup.md` |

## Git 附加命令

```bash
gls.sh [路径]
grm-cache.sh --dry-run
dgtag.sh
```

| 命令 | 行为 | 风险 |
|---|---|---|
| `gls.sh` | 统计当前仓库跟踪文件总行数 | 参数直接交给 `git ls-files` |
| `grm-cache.sh` | 按 `_gitignore` 将已跟踪文件执行 `git rm --cached` | 先使用 `--dry-run`，确认索引变更 |
| `dgtag.sh` | 删除当前仓库全部本地标签 | 不会删除远程标签，但本地标签全部丢失 |

`dgtag.sh` 不应与“清理一个旧标签”混用。删除前记录：

```bash
git tag --list
git show-ref --tags
```

`grm-cache.sh` 当前把规则源固定为 `$HOME/configure/lib/_gitignore`，因此只适用于该部署路径。移动仓库后应先调整调用方式或改用标准 `git rm --cached`。

## 文件与目录

```bash
ddu.sh [目录] [深度]
cp-small.sh SOURCE... DEST
mv-small.sh SOURCE... DEST
```

`ddu.sh` 使用 `du -h -d <深度>` 并按人类可读大小排序。`cp-small.sh` 与 `mv-small.sh` 跳过大于 1 MiB 的文件，并写入：

```text
DEST/.too-large-files.<时间戳>.list
```

跳过的大文件不会复制或移动。`mv-small.sh` 会保留大文件在原位置，并删除已移动空的目录。

这些工具当前使用 GNU `find -printf` 和 `stat -c`，在 macOS/BSD 上可能失败。执行移动前先使用 `cp-small.sh` 或普通 `cp` 验证目标。

## 日志与监视

```bash
llog.sh <命令> [参数...]
zlog.sh <命令> [参数...]
wwa.sh <命令> [参数...]
```

| 命令 | 行为 |
|---|---|
| `llog.sh` | 后台运行命令，stdout/stderr 写入当前目录 `.log.txt` |
| `zlog.sh` | 同上，并用 `watch tail .log.txt` 显示日志 |
| `wwa.sh` | 用 `watch` 重复运行命令 |

三个脚本对参数展开和命令执行缺少严格引用，不应传入不受信任的字符串。运行前确认当前目录的 `.log.txt` 可以被覆盖。

## 搜索

```bash
zsearch.sh <目录> <模式>
```

示例：

```bash
zsearch.sh . 'error'
zsearch.sh /var/log '[Ee]rror.*'
```

脚本先对文件内容执行递归 `grep`，再按文件名执行 `find -name`。模式同时作为正则和文件名通配模式使用，复杂模式应分别使用 `grep`/`find`。

## Python 与 Jupyter

```bash
zipython.sh
zjulab.sh
```

`zipython.sh` 执行 `clear && ipython`。`zjulab.sh` 在后台启动 `jupyter-lab --allow-root`。

`--allow-root` 只应在隔离容器或明确接受风险的远程环境中使用。普通工作站不要以 root 启动 Jupyter。

## 桌面与媒体入口

| 命令 | 行为 |
|---|---|
| `aaliyundrive.sh` / `.bat` | 打开阿里云盘网页 |
| `bbilibili.sh` / `.bat` | 打开哔哩哔哩 |
| `ddeepseek.sh` / `.bat` | 打开 DeepSeek 用量页 |
| `ccloudmusic.sh` / `.bat` | 启动或唤起网易云音乐 |
| `ggitee.sh` / `.bat` | 打开 Gitee 仓库页面 |

这些入口依赖桌面会话、浏览器或本机应用。无图形界面的 SSH/容器环境不会产生可见窗口。

## 娱乐入口

```bash
z2048.sh
ttetris.sh
ssnake.sh
zasciiquarium.sh
aaclock.sh
```

`z2048.sh` 期望存在编译后的 `lib/_package/linux/2048`，仓库默认只跟踪源码。先按 `../_package/setup.md` 编译。`zasciiquarium.sh` 通过明文 HTTP 获取在线动画，只应在允许该连接的环境使用。

游戏脚本使用终端控制序列和 `/tmp` 状态文件，不适合非交互自动化环境。

## 复合与批量入口

跨仓库 Git 命令：

```text
zg-all-pull.sh
zg-configure-pull.sh
zg-myqcd-pull.sh
zg-pyqcd-pull.sh
zg-pyqcu-pull.sh
gz-all-push.sh
gz-configure-push.sh
gz-myqcd-push.sh
gz-pyqcd-push.sh
gz-pyqcu-push.sh
```

这些脚本会进入相邻仓库并调用 `gpull.sh` 或 `gpush.sh`，因此继承自动提交、推送标签和清理工作区等行为。运行前逐个检查目标仓库状态。

`zg-*-pull.sh` 会进入目标仓库调用 `gpull.sh`。当前实现使用 `git pull --rebase --autostash` 保留 tracked 工作区改动；旧版 Git 缺少 `--autostash` 时回退到 stash 并在拉取成功后恢复。若拉取或恢复冲突，脚本返回非零并保留 stash，可检查：

```bash
git stash list
git stash show -p stash@{0}
```

未跟踪文件不在自动暂存范围内，可能继续留在工作区。detached HEAD 只有在其提交已包含于唯一可判定的 `origin` 默认分支时，才会自动恢复为该分支的跟踪分支；存在独立提交或候选分支不唯一时会拒绝切换并返回非零。脚本失败时检查 stash、分支和冲突状态。

## 其他系统与配置命令

| 命令 | 说明 |
|---|---|
| `save-env.sh` | 导出当前环境快照，可能含凭据，见 `../_shell/setup.md` |
| `gadd-ignore.sh` | 将 `_gitignore` 模板逐行补入当前仓库 |
| `grm-cache.sh` | 按模板将匹配的已跟踪文件移出索引，先使用 `--dry-run` |
| `swap.sh` | 关闭全部 Swap 后重建 64 GiB `/var/swapfile` |
| `cpupower.sh` 及其调用名链接 | 修改 CPU 调频和 C-state |
| `poweroff.sh` / `reboot.sh` | 立即关机或重启 |
| `xxattr.sh` | 清除 macOS quarantine 属性 |
| `vscode_unset.sh` | 备份并移走 VS Code Remote 状态目录 |

## 使用原则

1. 先读脚本注释和用法，不根据文件名猜参数。
2. 对修改文件、Git 索引、系统服务或电源状态的命令先执行只读检查。
3. 对包含 `eval`、未引用 `$@`、后台进程或覆盖固定文件名的脚本，不传入不可信输入。
4. 新增长期使用的稳定命令时，应在对应 `lib/_*` 目录补充操作说明。
