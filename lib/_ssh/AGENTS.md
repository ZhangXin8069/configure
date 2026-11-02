# AGENTS.md — _ssh

SSH 用户配置、密钥与主机快捷入口说明目录，不包含私钥。

- `setup.md`：密钥生成、ssh-agent、`~/.ssh/config`、主机验证和仓库内 SSH 快捷命令。
- 禁止把私钥、口令、一次性验证码或未经脱敏的主机清单写入本目录。
- `../../bin/ss.sh`、`ssnsc.sh`、`ssjtu.sh` 与 `xx99.sh` 的硬编码目标以源码为准。
- 仓库内交互式 SSH 入口统一使用 `ServerAliveInterval=30` 与 `ServerAliveCountMax=3`；Windows 入口还包括 `ss.ps1`、`ssnsc.bat`、`llingsheng.bat` 与 `kkunshan.bat`。
- 8 个交互式入口先直接建立 SSH，再在远端以本地 SSH 客户端主机名为默认名创建新的 UTF-8 screen；`-t` 与 `-S` 同名，禁止 `-r`/`-R` 自动进入旧会话，以支持同一客户端多次并行 SSH。`SSH_SCREEN_NAME` 可覆盖名称；`SSH_REMOTE_SHELL=posix|powershell` 选择远端脚本，默认 19 号 Windows 主机与 X99 使用 PowerShell、其余 POSIX。远端缺少 screen 时只输出 warning 后进入交互 shell，PowerShell 路径禁止混入 POSIX 条件或命令连接符。`env.sh` 另提供本地 `scn`、`scl`、`scr` 别名。
