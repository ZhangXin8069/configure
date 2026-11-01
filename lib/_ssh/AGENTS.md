# AGENTS.md — _ssh

SSH 用户配置、密钥与主机快捷入口说明目录，不包含私钥。

- `setup.md`：密钥生成、ssh-agent、`~/.ssh/config`、主机验证和仓库内 SSH 快捷命令。
- 禁止把私钥、口令、一次性验证码或未经脱敏的主机清单写入本目录。
- `../../bin/ss.sh`、`ssnsc.sh`、`ssjtu.sh` 与 `xx99.sh` 的硬编码目标以源码为准。
- 仓库内交互式 SSH 入口统一使用 `ServerAliveInterval=30` 与 `ServerAliveCountMax=3`；Windows 入口还包括 `ss.ps1`、`ssnsc.bat`、`llingsheng.bat` 与 `kkunshan.bat`。
- 8 个交互式入口在 screen 可用时以客户端名创建或重连会话，`-t` 与 `-S` 同名并按 `$STY` 更新为 `<pid>.<sockname>`；screen 缺失时输出各 Unix/类 Unix 安装与使用指南后继续直接 SSH。`env.sh` 提供 `scn`、`scl`、`scr` 别名。
