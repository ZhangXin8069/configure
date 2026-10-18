# Windows 配置操作

## 执行环境

| 入口 | 适用 Shell |
|---|---|
| `*.bat` | `cmd.exe`，也可从 PowerShell 调用 |
| `*.ps1` | 取决于脚本；不能统一下调为 PowerShell 5.1 |
| `agent.bat` | cmd/PowerShell 通用入口 |
| Git Bash 脚本 | 只用于兼容 Unix 的命令，不替代原生 Windows 安装器 |

特别地，`lib/_claude-code/cc-v20260706.ps1` 使用 `ConvertFrom-Json -AsHashtable`，要求 PowerShell 7+ 的 `pwsh`。其他 PowerShell 脚本应按各自语法和测试结果单独确认版本。

PowerShell 脚本建议只对当前进程放行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\script.ps1
```

不建议执行 `Set-ExecutionPolicy Unrestricted` 或永久关闭 Defender。

## Agent 入口

`bin\agent.bat` 的实现支持以下调用名：

```text
cl.bat   -> Claude Code
cls.bat  -> Claude Code secure
op.bat   -> OpenCode
ops.bat  -> OpenCode secure
co.bat   -> Codex
cos.bat  -> Codex secure
```

当前仓库只跟踪 `cl.bat`、`op.bat`、`co.bat` 三个符号链接。`cls.bat`、`ops.bat`、`cos.bat` 尚未入库，需要 secure 入口时手工创建。

Git for Windows 默认可能不创建这些符号链接。若它们被检出为普通文本占位文件，先确认内容仅指向 `agent.bat`，再自行重命名或移除占位文件；缺失时可在仓库 `bin` 目录用管理员 cmd 重建硬链接：

```bat
mklink /H cl.bat agent.bat
mklink /H cls.bat agent.bat
mklink /H op.bat agent.bat
mklink /H ops.bat agent.bat
mklink /H co.bat agent.bat
mklink /H cos.bat agent.bat
```

安装命令：

```bat
lib\_codex\install.bat
lib\_opencode\install.bat
```

Claude Code 使用 `lib\_claude-code\cc-v20260706.ps1`。DeepSeek Codex 配置管理器使用 `lib\_deepseek\codex-deepseek-setup.ps1`。

安装完成后打开新终端：

```powershell
Get-Command codex, opencode, claude -ErrorAction SilentlyContinue
codex --version
opencode --version
```

API key 放在 Windows 用户环境变量中，禁止写入脚本或提交：

```powershell
[Environment]::SetEnvironmentVariable('DEEPSEEK_PAY_API_KEY', '<真实密钥>', 'User')
```

## SSH

Windows OpenSSH 通常位于：

```text
%WINDIR%\System32\OpenSSH\ssh.exe
```

检查：

```powershell
Get-Command ssh, ssh-keygen, ssh-agent
Get-Service ssh-agent
```

私钥默认位于 `$HOME\.ssh`。服务启用：

```powershell
Set-Service ssh-agent -StartupType Manual
Start-Service ssh-agent
ssh-add $HOME\.ssh\id_ed25519
```

`Set-Service` 和管理 ssh-agent 服务通常需要管理员 PowerShell；只把密钥加载到当前用户的 agent 时，可使用系统现有的按用户启动方式。

详细密钥和主机配置见 [`../_ssh/setup.md`](../_ssh/setup.md)。

## Docker

`bin\ddocker.bat` 会查找并启动 Docker Desktop，选择最近创建的容器，再尝试进入 `zsh` 或基础 shell。安装和使用说明见 [`../_docker/setup.md`](../_docker/setup.md)。

前置检查：

```powershell
docker version
docker info
wsl --status
```

## 字体和可执行资源

字体安装见 [`../_font/setup.md`](../_font/setup.md)。`lib/_package/win/*.exe` 是未在本仓库重新签名的二进制文件，运行前应检查哈希和 Authenticode 签名。

## 桌面快捷入口

`bin` 下提供 `ccloudmusic.bat`、`ccloudmusic.ps1`、`ddocker.bat`、`ddocker.ps1`、`aaliyundrive.bat`、`bbilibili.bat`、`ddeepseek.bat`、`ggitee.bat`、`oopencode-usage.bat`、`ss.bat`、`ssnsc.bat` 等入口。它们依赖本机已安装的对应软件、网络位置或 SSH 目标。

## 验证边界

Unix 主机可检查文本和路径引用，但不能证明以下行为：

1. `HKCU\Environment` 的 PATH 写入。
2. `setx` 或用户环境变量传播。
3. Docker Desktop 启动流程。
4. Windows OpenSSH 服务和密钥权限。
5. `.exe` 的 Defender/SmartScreen 行为。

这些项目必须在目标 Windows 机器上验证，并在测试记录中注明 Windows 版本。
