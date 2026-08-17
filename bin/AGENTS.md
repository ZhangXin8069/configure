# AGENTS.md — bin 工具脚本

工具 shell 脚本目录。`bin/` 由 `env.sh` 前置到 `PATH`，所有 `.sh`（含 `cl`/`op` 等符号链接）可直接按名调用（`gpush.sh`、`ssub.sh`）。脚本必须可执行且带 shebang。

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
- **所有 `.sh` 脚本必须有可执行权限**（新建/编辑脚本后执行 `chmod +x <script>`）

## 脚本分类

| 类别 | 脚本 |
|---|---|
| Git | `gpush.sh`（add -A + 时间戳提交 + push 分支与标签）、`gpull.sh`、`gback.sh`、`dgtag.sh`、`gls.sh`、`git_init.sh` |
| 跨仓库批量 | `zgALLpush/pull.sh`、`zgCONFIGUREpush/pull.sh`、`zgPyQCDpush/pull.sh`、`zgPYQCUpush/pull.sh`（相对路径 `../../repo-name`） |
| HPC/Slurm | `ssub.sh`（内嵌模板：gpu-debug 分区、2 GPU）、`ssqueue.sh`、`zsqueue.sh`、`ssrun.sh`、`sstop.sh`、`ssnake.sh`、`ssnsc.sh`、`ssjtu.sh` |
| 系统 | `cpupower.sh`（按 `$_NAME` 分发，`conservative/ondemand/performance/powersave.sh` 为符号链接）、`swap.sh`（64GB /var/swapfile）、`apt_install.sh`、`pip_install.sh`、`poweroff.sh`、`reboot.sh` |
| 启动器 | `cclaude.sh`（Claude Code）、`oopencode.sh`（opencode build agent，prompt 取自同目录 `oopencode-prompt.txt` 单一来源；每次会话生成 `.agent.<TS>.log` 运行日志与 `.agent.<TS>.list` 用户输入清单；`-h/-p/-f/-q/-k/-g` 选模型，默认 `-h`=Hy3 high）、`oopencode.bat`（Windows 对应版，同一 prompt 模板）、`oopencode-snsc.sh`（HPC/snsc 变体：自动收集工作目录 AGENTS.md/.opencode 项目上下文注入 prompt，硬编码调用 vscode-server 内手动部署的 debug 二进制；经 `ops` 软链接调用，模型选项同 `oopencode.sh`）、`ddocker.sh`、`ccloudmusic.sh`、`zipython.sh`、`zjulab.sh`、`vscode_unset.sh` |
| 初始化 | `sh_init.sh`（引导 shell：`-b` 仅部署 _bashrc，`-z` 部署 _zshrc+_oh-my-zsh（默认），`-a` 全部；备份旧点文件带时间戳；zsh/oh-my-zsh 缺失时警告）、`vim_init.sh`、`zerotier_init.sh` |
| 工具 | `wwa.sh`、`ddu.sh`、`llog.sh`、`zsearch.sh`、`zlog.sh`、`cp-small.sh`（cp 包装：跳过 >1MB 文件并记录清单到目标目录）、`mv-small.sh`（mv 包装，同规则） |
| 平台 | `xxattr.sh`（macOS）、`xx99.sh`（X99 工作站） |
| 游戏 | `ttetris.sh`、`ssnake.sh`、`z2048.sh`、`zasciiquarium.sh`、`aaclock.sh` |

`cl`、`op` 与 `ops` 为符号链接（→ cclaude.sh / oopencode.sh / oopencode-snsc.sh）。

## 平台与注意事项

- `.bat`/`.ps1` 为 Windows 对应版，**不**被别名生成器扫描（只扫 `.sh`）
- `oopencode-prompt.txt` 为 op 系列（`oopencode.sh`/`oopencode.bat`）的 **prompt 单一来源**（保留 `${HOME}`/`${_PWD}`/`${LIST_FILE}` 占位符，运行时替换）：`oopencode.sh` 经 bash 参数展开替换、`oopencode.bat` 经 PowerShell 替换；**修改 prompt 只改此文件**，勿在脚本内再内嵌
- `cctag` 二进制与 `claude_code-skill4git-tag.md` 已删除，git 标签管理技能移至 `../skills/tag/`
- `.agent.*.log`（opencode 运行日志）与 `.agent.*.list`（会话用户输入清单）为运行产物，不入库
- 新增脚本后 `chmod +x <script>` 并在新 shell（或 `source ~/.zshrc`）中直接按名调用；校验语法 `bash -n <script>`
