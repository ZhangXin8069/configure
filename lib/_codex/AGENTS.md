# AGENTS.md — _codex

Codex CLI 跨平台安装与一键配置脚本（不部署到 `$HOME`，手动运行）：

- `install.sh` — Linux/macOS 安装脚本（GitHub releases 二进制 → `~/.codex/bin`，
  musl 静态构建，PATH 防重复注入；支持 `[VERSION]` 参数，默认 latest）
- `install.bat` — Windows 安装脚本（npm 全局安装 `@openai/codex`）
- `config.sh` — 一键配置脚本（幂等合并生成 `~/.codex/config.toml`，保留已有键与
  注释；默认 dry-run，`--apply` 才写盘；支持 model/approval-policy/sandbox-mode/
  theme 与 model_providers 条目追加，含推荐 provider 清单）

认证由 `codex login` 完成，脚本不代做。由 `bin/agent.sh` co/cos 系列流程引用。