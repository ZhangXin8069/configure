# AGENTS.md — claude_code-v20260706

Claude Code 离线安装包 v2026-07-06（当前最新版，`../_claude_code/` 为其符号链接兼容目录）：

| 文件 | 说明 |
|---|---|
| `cc-v20260706.sh` / `cc-v20260706.ps1` | Claude Code 安装/升级脚本（Linux/macOS 与 Windows） |
| `cc_cli-v20260708.sh` | CLI 包装脚本（v2026-07-08） |
| `download_all.sh` | 下载全部安装文件 |
| `setup.md` | 安装指南 |
| `uninstall_cc-v20260812.sh` / `uninstall_cc-v20260812.bat` | 卸载脚本（v2026-08-12，agent 会话生成） |
| `.gitignore` | 忽略下载的二进制包 |

修改本目录文件时保持 `_claude_code/` 符号链接一致性（更新即生效，无需改链接）。校验 `bash -n <script>`。
