# AGENTS.md — _env

Shell 环境入口与版本化机器配置的选择、复制、恢复和更新说明目录。

- `setup.md`：`env.sh`、`lib/set-env.sh`、`~/env.sh`、`~/env-key.sh`、日期版本目录和 `@SECTION@` 约定。
- 实际环境源位于 `../<name>-vYYYYMMDD>/env.sh`；本目录不复制或替代这些快照。
- 更新机器配置时新建日期目录，不改旧目录；真实密钥只放本机受控文件。
