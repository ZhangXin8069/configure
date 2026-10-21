# AGENTS.md — plugins 插件推荐目录

本目录维护 Codex 插件的推荐索引，不默认承载或安装第三方插件。

- `README.md` 记录候选项目、兼容性、重叠风险和调研来源。
- `install-recommended.sh` 只在用户显式执行时调用 Codex marketplace；支持 profile、单插件、Git ref、`--status/--audit` 和 dry-run，不复制第三方源码、不安装 npm 依赖、不自动信任 hooks。状态模式只读查询并禁止 `add` 命令；官方来源只接受精确别名 `openai-curated`/`openai-api-curated`。社区 ref 只接受完整 40/64 位 commit，或经 `git check-ref-format` 与 `git ls-remote --exit-code --tags` 验证的固定 tag；多社区 profile 使用每项内建完整 commit，显式 `--ref` 只能覆盖一个社区目标。已配置社区 marketplace 无法从 JSON 证明 source/ref，必须拒绝复用；查询或 JSON schema 异常返回 2 且禁止写入。
- `--audit-manifest PATH` 委托 `tools/plugin-audit.py --strict`，在安装或启用前检查 manifest、hook、
  MCP、路径边界和危险命令；审计模式不调用 Codex marketplace。
- 只有实际可加载的插件才建立子目录，并保留 `.codex-plugin/plugin.json`；新增后核对入口、依赖、权限和路径。
- 不在此目录自动创建个人 marketplace、执行外部安装或复制未经审查的上游源码。
