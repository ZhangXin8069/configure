# AGENTS.md — tools 工具目录

本目录保存配置仓库维护工具和上游工具推荐信息。

- `configure-check.sh` 是只读检查入口，必须保持可执行、带 Bash shebang，并通过 `bash -n`。
- 工具不得自动安装依赖、执行 hook/plugin 或修改仓库；第三方项目只记录在 `README.md`。
- 新增 shell 工具后同步说明用途、参数、退出码和依赖，并做权限、语法和边界参数验证。
