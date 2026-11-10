# AGENTS.md — _command-code

Command Code 跨平台安装与用户级一键配置目录。所有脚本手动执行，不随 shell 启动自动运行：

- `install.sh` / `install.bat` — 检查 Node.js 22+，通过 npm 安装官方 `command-code`
  包；Node.js 缺失或过旧时退出，并指向 `../_node-js/install.sh` / `install.bat`。
  默认固定 `1.88.2`，`--new` 安装最新版，也可显式传入版本号。Unix 默认安装到
  `$HOME/.local/bin`（npm prefix 为 `$HOME/.local`），Windows 默认安装到
  `%USERPROFILE%\.local\bin`；两者均与同目录的 Codex/OpenCode agent 路径约定一致，
  可用 `COMMAND_CODE_INSTALL_DIR` 覆盖，并在安装目录不在 PATH 时幂等注册。
- `config.sh` — 合并 `~/.commandcode/config.json` 与 `~/.commandcode/settings.json`。
  默认 dry-run，只有 `--apply` 才写盘；写盘前备份，保留未知字段，拒绝在配置中保存原始密钥。
- `install.test.sh` — 使用隔离 HOME 与假 Node.js/npm 验证版本选择、统一安装前缀、
  PATH 幂等写入、Node.js 版本闸门、`_node-js` 提示与安装后版本检查。
- `config.test.sh` — 使用隔离 `HOME` 与假 `command-code` 覆盖个人偏好、权限规则、幂等合并、
  未知字段保留、dry-run 和参数校验。
- Node.js 依赖 — 安装、升级与版本检查统一由 `../_node-js/` 提供，本目录不重复维护。
- `setup.md` — Quickstart、安装（Node.js 前置见 `../_node-js/setup.md`）、
  认证、taste/import/update、配置、权限、BYOK、项目级配置与排障说明。
- Agent 集成 — 仓库 `bin/cm`（Command Code）与 `bin/cms`（secure）默认使用
  `commandcode-goat`、DeepSeek V4.1 Flash、max、1M 上下文和 yolo；支持
  `cm --goal <objective>` / `cm goal <objective|status|clear>` 原生 goal，
  `--max-turns` 作为 goal 预算。`bin/agent*` 的 `gt|tgo` 快捷词为 `cl/op/co`
  提供同一 Provider API。`cm pay`/`cm go|cgo`/`cm dgo` 走 BYOK：启动器把
  `agent-config.json` 中 `commandcode.byok=true` 的途径幂等合并进
  `~/.commandcode/providers.json`，模型以 `<途径>/<模型>` 传给 `--model`。

官方依据：

- <https://commandcode.ai/docs/quickstart>
- <https://commandcode.ai/docs/settings>
- <https://commandcode.ai/docs/permissions>
- <https://commandcode.ai/docs/byok>
- <https://commandcode.ai/docs/provider>

认证文件 `.commandcode/auth.json` 由 Command Code 管理，禁止手工提交或复制。BYOK 的
`providers.json` 只能保存 `$ENV_VAR`、`{env:VAR}` 或 `!command` 形式的密钥引用。
