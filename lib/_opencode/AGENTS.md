# AGENTS.md — _opencode

opencode CLI 跨平台安装与一键配置脚本（不部署到 `$HOME`，手动运行）：

- `install.sh` — Linux/macOS 安装脚本
- `install.bat` — Windows 安装脚本
- `config.sh` — 一键配置脚本（幂等合并生成 `~/.config/opencode/opencode.json` 与
  `tui.json`，保留已有键；默认 dry-run，`--apply` 才写盘；含主题/插件推荐清单，
  参考 awesome-opencode 生态）

由 `bin/agent.sh`（op 分支）相关流程引用。
