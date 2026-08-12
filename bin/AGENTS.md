# AGENTS.md — bin 工具脚本

工具 shell 脚本目录。每个 `.sh` 文件被 `scripts/script_alias.sh` 自动发现并生成别名（`alias gpush.sh='bash /path/to/bin/gpush.sh'`），由 `tmp/scripts.sh` 在 shell 启动时加载。

## 脚本骨架约定

```bash
#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# ... 逻辑 ...
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
```

- 必须用 `${BASH_SOURCE[0]:-$0}`（不能用裸 `$0`，登录 shell 下 `$0` 为 `-bash` 会报错）
- 执行首尾打印带时间戳标记
- 严格模式 `set -euo pipefail` 仅部分新脚本使用

## 脚本分类

| 类别 | 脚本 |
|---|---|
| Git | `gpush.sh`（add -A + 时间戳提交 + push 分支与标签）、`gpull.sh`、`gback.sh`、`dgtag.sh`、`gls.sh`、`git_init.sh` |
| 跨仓库批量 | `zgALLpush/pull.sh`、`zgCONFIGUREpush/pull.sh`、`zgLATTICE-PDFpush/pull.sh`、`zgPYQCUpush/pull.sh`（相对路径 `../../repo-name`） |
| HPC/Slurm | `ssub.sh`（内嵌模板：gpu-debug 分区、2 GPU）、`ssqueue.sh`、`zsqueue.sh`、`ssrun.sh`、`sstop.sh`、`ssnake.sh`、`ssnsc.sh`、`ssjtu.sh` |
| 系统 | `cpupower.sh`（按 `$_NAME` 分发，`conservative/ondemand/performance/powersave.sh` 为符号链接）、`swap.sh`（64GB /var/swapfile）、`apt_install.sh`、`pip_install.sh`、`poweroff.sh`、`reboot.sh` |
| 启动器 | `cclaude.sh`（Claude Code）、`oopencode.sh`（opencode build agent，含固定中文 prompt）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 初始化 | `sh_init.sh`（引导 shell：备份旧点文件，部署 lib/_bashrc、_zshrc、_oh-my-zsh）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh` |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl` 与 `op` 为符号链接（→ cclaude.sh / oopencode.sh）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- 新增脚本后运行 `bash ../scripts/script_alias.sh` 再 source 新 shell；校验语法 `bash -n <script>`
