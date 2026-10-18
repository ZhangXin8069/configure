# Claude Code 安装与配置

## 目录职责

`lib/_claude-code/` 是稳定入口。脚本行为的维护源是 `lib/claude-code-v20260706/`，两边的脚本文件当前都是真实副本，不是目录链接。本文是针对稳定入口重新整理的操作文档，版本化目录中的历史 `setup.md` 未改写。

| 文件 | 用途 |
|---|---|
| `install.sh` | Linux/macOS 安装或检查 |
| `config.sh` | 合并 `~/.claude/settings.json` |
| `cc-v20260706.ps1` | Windows 安装脚本 |
| `download_all.sh` | 下载 Claude Code、cc-switch CLI 和 GUI 离线包 |
| `uninstall_cc-v20260812.sh/.bat` | 卸载 Claude Code |
| `uninstall_ccswitch-v20260813.sh` | 卸载 cc-switch |

离线二进制与 GUI 包默认不随 Git 仓库存在。脚本设计目标是在自身目录下生成：

```text
claude-code/
cc-switch-cli/
cc-switch/
```

## 前置依赖

```bash
command -v python3 curl tar
command -v node npm 2>/dev/null || true
```

`install.sh` 需要 `python3` 合并 `~/.claude.json`。联网安装还需要 `curl` 和 `tar`；npm 模式需要 Node.js/npm。

## Linux / macOS 安装

只读检查：

```bash
bash lib/_claude-code/install.sh --check
```

安装脚本默认版本：

```bash
bash lib/_claude-code/install.sh
```

指定版本：

```bash
bash lib/_claude-code/install.sh 2.1.210
```

安装最新版：

```bash
bash lib/_claude-code/install.sh --new
```

使用 npm：

```bash
bash lib/_claude-code/install.sh --npm 2.1.210
```

原生布局：

```text
~/.local/bin/claude-<version>
~/.local/bin/claude -> claude-<version>
~/.claude.json
```

脚本会幂等合并 `~/.claude.json` 中的 `installMethod` 与自动更新字段，保留其他已有键。若文件不是合法 JSON，脚本会停止，不会擅自覆盖。

## 离线安装

下载全部 Linux x64 资源：

```bash
cd lib/_claude-code
bash download_all.sh
```

按组件下载：

```bash
cd lib/_claude-code
bash download_all.sh --claude-code
bash download_all.sh --cc-switch-cli
bash download_all.sh --cc-switch
```

下载已有非空文件时会跳过，适合断点续跑。

当前脚本的 Claude Code 下载使用脚本目录 `$BASE`，但 cc-switch 两段 Python 代码读取的是未导出的 `SCRIPT_DIR` 环境变量，缺失时会回退到当前工作目录。因此必须先从 `lib/_claude-code` 执行；如果在仓库根直接运行，cc-switch 内容可能落到根目录下的 `cc-switch-cli/` 与 `cc-switch/`。

Claude Code 离线目录使用 `claude-code/<version>/claude` 与 `manifest.json`。指定版本时，`install.sh` 优先使用本地包，缺失时才联网。

安装后应校验：

```bash
cat lib/_claude-code/claude-code/<version>/manifest.json
shasum -a 256 lib/_claude-code/claude-code/<version>/claude
```

不要只根据文件大小判断完整性。`download_all.sh` 会把零字节或失败下载删除，但仍应使用上游 manifest 中的 SHA-256 校验。

## cc-switch

`download_all.sh --cc-switch-cli` 下载 CLI tar 包和上游 `install.sh`。按对应版本目录中的上游说明安装：

```bash
cd lib/_claude-code/cc-switch-cli/<version>
cat install.sh
sh install.sh
```

GUI 包可能是 AppImage、deb 或 rpm。安装前确认包名和版本：

```bash
find lib/_claude-code/cc-switch -maxdepth 2 -type f -print | sort
```

AppImage 可直接运行，但需要可执行权限；deb/rpm 使用系统包管理器。不要在不相关发行版上强行安装包格式。

## 配置

`config.sh` 只处理 `~/.claude/settings.json`，不修改 `~/.claude.json` 的安装与登录字段。

```bash
bash lib/_claude-code/config.sh --check
bash lib/_claude-code/config.sh \
  --model <模型> \
  --theme dark \
  --permission-deny WebFetch \
  --env DISABLE_AUTOUPDATER=1
```

默认 dry-run。确认后：

```bash
bash lib/_claude-code/config.sh --apply --theme dark
```

写盘前会创建 `settings.json.bak.<时间戳>`。

macOS 默认 Bash 3.2 执行 `config.sh --help` 时，帮助文本中的非 ASCII 标点会让未加花括号的变量名解析失败；应使用 Bash 4+，只读状态检查可继续使用 `--check`。

当前 `config.sh` 会把 `--permission-allow`/`--permission-deny` 的值拼成字符串后按空白拆分。包含空格的规则（例如 `Bash(rm -rf:*)`）会被拆成多条无效规则。修复脚本前只应传入不含空白的单 token 规则，复杂权限规则应直接编辑 `settings.json` 并先用 dry-run/JSON 校验确认。

统一启动器 `cl` 会额外注入 provider、认证、模型、推理强度和状态栏设置，并覆盖旧的用户/项目级冲突项。需要供应商切换时优先使用：

```bash
cl pay
cl go
cl zen
```

详细配置见 [`../_agent/setup.md`](../_agent/setup.md)。

## Windows

```powershell
pwsh -NoProfile -File .\lib\_claude-code\cc-v20260706.ps1
```

Windows 安装脚本使用 `ConvertFrom-Json -AsHashtable`，需要 PowerShell 7+ 的 `pwsh`，不能假定 Windows 自带 PowerShell 5.1 可用。脚本同样会写入原生安装布局与 `~/.claude.json`。运行前先阅读脚本参数和各平台资产命名。

## 卸载

先 dry-run：

```bash
bash lib/_claude-code/uninstall_cc-v20260812.sh --dry-run
bash lib/_claude-code/uninstall_ccswitch-v20260813.sh --dry-run
```

标准卸载默认保留用户数据：

```bash
bash lib/_claude-code/uninstall_cc-v20260812.sh
```

`--purge` 会删除 `~/.claude.json` 与 `~/.claude/`，其中包含登录凭据、设置和会话数据：

```bash
bash lib/_claude-code/uninstall_cc-v20260812.sh --purge
```

该操作不可由普通备份流程替代。执行前应单独确认，并明确是否需要保留登录状态。

## 密钥

不要运行 `claude-code-deepseek-env.sh` 的未修改模板，也不要将 API key 写入 `settings.json`、`.claude.json` 或仓库。统一启动器从本机环境变量读取密钥，见 [`../_deepseek/setup.md`](../_deepseek/setup.md)。

## 验证

```bash
bash -n lib/_claude-code/install.sh
bash -n lib/_claude-code/config.sh
bash -n lib/_claude-code/download_all.sh
bash -n lib/_claude-code/uninstall_cc-v20260812.sh
bash -n lib/_claude-code/uninstall_ccswitch-v20260813.sh
bash lib/_claude-code/install.sh --check
bash lib/_claude-code/config.sh --check
claude --version
```

离线下载和真实安装需要网络或完整离线包；验证时应记录实际执行到哪一层。
