# AGENTS.md — _env

Shell 环境入口与版本化机器配置的选择、复制、恢复和更新说明目录。

- `setup.md`：`env.sh`、`lib/set-env.sh`、`~/env.sh`、`~/env-key.sh`、日期版本目录、`@SECTION@` 约定和版本化快照索引。
- 根 `env.sh` 的大规模冲突预检与告警当前暂停；`../_env_conflicts.sh` 实现保留，恢复时取消 `env.sh` 中 `@CONFLICT_GUARD_PAUSED@` 块注释。
- 成功加载后导出 `_CONFIGURE_ENV_LOADED_PATH`；同一 Shell 或子 Shell 再次 source 且路径匹配时跳过。
- 实际环境源位于 `../<name>-vYYYYMMDD>/env.sh`；本目录不复制或替代这些快照。
- 更新机器配置时新建日期目录，不改旧目录；真实密钥只放本机受控文件。
