# AGENTS.md — _codex

Codex CLI 跨平台安装与一键配置脚本（不部署到 `$HOME`，手动运行）：

- `install.sh` — Linux/macOS 安装脚本（GitHub releases 二进制 → `~/.local/bin`，
  musl 静态构建，PATH 防重复注入；参数 `[--new] [VERSION]`：默认 0.154.0，
  `--new` 取最新版，显式 VERSION 优先级最高；安装目录可用 `CODEX_INSTALL_DIR` 覆盖；
  同时尝试安装同版本 `codex-code-mode-host`，旧版本无此资产时警告并跳过）
- `install.bat` — Windows 安装脚本（npm 全局安装 `@openai/codex` → `%USERPROFILE%\.local\bin`，
  经 `npm install -g --prefix` 指定目录；仅按当前进程 PATH 判断是否写入
  `HKCU\Environment`，可能重复追加，执行后需检查用户 PATH；
  参数 `[--new] [VERSION]`（语义同 install.sh）与 `CODEX_INSTALL_DIR` 覆盖）
- `config.sh` — 一键配置脚本（幂等合并生成 `~/.codex/config.toml`，保留已有键与
  大部分注释；被更新的顶层行会丢失行尾注释；默认 dry-run，`--apply` 才写盘；支持 model/approval-policy/sandbox-mode/
  theme 与 model_providers 条目追加，含推荐 provider 清单）
- `setup.md` — 版本选择、配置合并、认证、Responses 协议限制与验证

认证由 `codex login` 完成，脚本不代做。由 `bin/agent.sh` co/cos 系列流程引用。
