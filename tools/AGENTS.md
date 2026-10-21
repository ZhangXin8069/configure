# AGENTS.md — tools 工具目录

本目录保存配置仓库维护工具和上游工具推荐信息。

- `configure-check.sh` 是只读检查入口，必须保持可执行、带 Bash shebang，并通过 `bash -n`；
  技能表与互鉴表同时核验登记完整性和 Markdown 列数一致性。
- `configure-check.sh --strict` 将警告提升为失败，供需要零警告的 CI 门禁使用；默认模式仍区分警告与错误。
- `coverage-report.sh` 是只读诊断入口，复用 `configure-check.sh` 的发现思路输出四树覆盖摘要、镜像一致性线索和缺口提示；允许缺口存在，但必须保持可执行、带 Bash shebang，并配套测试。其插件 manifest 诊断依赖 `python3`，其余部分只用 Bash/常见文本工具。
- `task-scope.sh` 是只读任务分流入口，把自然语言任务映射到技能组合与拆分建议；保持可执行，并同步 `README.md` 里的用途、参数和测试入口。
- `agent-resume.sh` 检测 agent run 的瞬时基础设施故障，默认等待 10 秒后通过原统一 launcher
  执行一次 `--resume`；必须保持 fail-closed、识别存活进程、恢复 session/thread，并用单次标记
  防止持续限流引发无界重试。配套 `agent-resume.test.sh`，并覆盖派发子 agent 的同构 manifest。
- `agent-resources.py` 是只读资源快照入口，分离 host inventory、process affinity、cgroup v2、
  Slurm allowlist 和 accelerator management visibility；不得运行 benchmark/stress、写系统状态、
  输出 hostname、绝对路径、job/device ID 或未脱敏环境变量。未知值保持 `null`，配套
  `agent-resources.test.py`。
- 工具不得自动安装依赖、执行 hook/plugin 或修改仓库；第三方项目只记录在 `README.md`。
- 新增 shell 工具后同步说明用途、参数、退出码和依赖，并做权限、语法和边界参数验证；只读诊断工具的“成功”指报表或建议成功生成，不要求仓库被修改。
- `configure-check.sh` 的路径枚举失败必须 fail-closed；其临时 NUL 清单仅用于检查过程并在退出时清理。
- `skills/form/references/source-snapshots/` 是保留上游名称、权限和 shebang 状态的只读
  明文快照；`configure-check.sh` 必须排除该目录，不把 vendored 脚本当作本库维护脚本。
