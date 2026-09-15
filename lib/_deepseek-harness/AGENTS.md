# AGENTS.md — _deepseek-harness

DeepSeek Harness（`dsh`，官方仓库 <https://github.com/deepseek-ai/deepseek-harness>）跨平台安装与一键配置脚本（不部署到 `$HOME`，手动运行）：

- `install.sh` — Linux/macOS 安装脚本（npm 全局安装 `@deepseek-ai/dsh`，Node 版本提示、
  npm 可运行性预检（npm 11+ 自动放行 dsh 依赖的 install-scripts）、校验与 PATH 防重复注入；
  支持 `[VERSION]` 参数，默认 latest，也可传 npm dist-tag 如 `next`）
- `install.bat` — Windows 安装脚本（npm 全局安装 `@deepseek-ai/dsh`）
- `config.sh` — 一键配置脚本（幂等合并生成 `$DSH_HOME/settings.yaml` 与
  `$DSH_HOME/.credentials.yaml`，保留已有键与注释；默认 dry-run，`--apply` 才写盘；
  支持 baseURL/apiKeyEnv/thinking/reasoningEffort/maxTokens、默认模型
  （`agent-default-model`）与 API key 写入〔凭证文件强制 600；兼容 0.1.5 的
  `version: 1` + `refs:` 结构，旧扁平格式拒绝编辑〕）

上游处于 developer preview 且会引入破坏性变更，npm `latest` 可能指向 rc 版本；模型 id、
配置字段与安全须知（`SAFETY.md`）以官方文档 <https://deepseek-harness.github.io/deepseek-harness/> 为准。

运行环境与入口：

- 需 Node.js `^22.19.0 || >=24.0.0`（上游仓库 engines；npm 包未声明，脚本仅提示不阻断）
- `dsh web` — Web UI，默认 <http://127.0.0.1:3080>；`dsh --profile headless "任务"` —
  单次会话后退出；`dsh --profile acp|sdk` — 自动化服务（stdio）
- 配置位置 `$DSH_HOME`（默认 `~/.dsh`）：`settings.yaml`（用户设置，热加载）、
  `.credentials.yaml`（凭证，`refs:` 按环境变量名存值）、`AGENTS.md`（用户级指令）、
  `profiles/<name>/`（profile 插件栈）
- 认证：`dsh web` → Settings → Models 填 DeepSeek API key，或 `config.sh --key-from-env --apply`；
  已导出的 `DEEPSEEK_API_KEY` 优先级最高且只读（脚本不覆盖环境变量、不代做登录）
