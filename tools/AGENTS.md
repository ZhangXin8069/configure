# AGENTS.md — tools 工具目录

本目录保存配置仓库维护工具和上游工具推荐信息。

- `configure-check.sh` 是只读检查入口，必须保持可执行、带 Bash shebang，并通过 `bash -n`。
- `configure-check.sh --strict` 将警告提升为失败，供需要零警告的 CI 门禁使用；默认模式仍区分警告与错误。
- `coverage-report.sh` 是只读诊断入口，复用 `configure-check.sh` 的发现思路输出四树覆盖摘要、镜像一致性线索和缺口提示；允许缺口存在，但必须保持可执行、带 Bash shebang，并配套测试。其插件 manifest 诊断依赖 `python3`，其余部分只用 Bash/常见文本工具。
- `task-scope.sh` 是只读任务分流入口，把自然语言任务映射到技能组合与拆分建议；保持可执行，并同步 `README.md` 里的用途、参数和测试入口。
- 工具不得自动安装依赖、执行 hook/plugin 或修改仓库；第三方项目只记录在 `README.md`。
- 新增 shell 工具后同步说明用途、参数、退出码和依赖，并做权限、语法和边界参数验证；只读诊断工具的“成功”指报表或建议成功生成，不要求仓库被修改。
- `configure-check.sh` 的路径枚举失败必须 fail-closed；其临时 NUL 清单仅用于检查过程并在退出时清理。
