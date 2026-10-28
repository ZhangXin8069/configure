# AGENTS.md — _opencode

OpenCode 跨平台安装与一键配置脚本（不部署到 `$HOME`，手动运行；按二进制主版本分流 V1/V2 配置）：

- `install.sh` / `install.bat` — Linux/macOS 与 Windows 安装脚本，从
  `https://opencode.ai/files/bin/<version>/` 下载官方二进制；默认安装固定版本
  2.2.0（`--new` 取上游最新版，也可显式传入 VERSION）；默认安装到
  `~/.local/bin` / `%USERPROFILE%\.local\bin`，可用 `OPENCODE_INSTALL_DIR` 覆盖，
  测试可用 `OPENCODE_BASE_URL` 切换镜像源
- `config.sh` — 幂等配置脚本。OpenCode V2 生成 `opencode.json` + `cli.json` 原生配置
  （`permissions` 有序规则、`plugins` 数组）；V1 自动回退旧 `permission`/`plugin` +
  `tui.json`。默认 dry-run，`--apply` 才写盘
- `config.test.sh` — 隔离 HOME/XDG 的 V2/V1 配置回归测试
- `setup.md` — 版本分流、安装、配置、插件和验证说明

由 `bin/agent.sh`、`bin/agent.bat`/`agent-runtime.ps1`（op 分支）相关流程引用。
