# AGENTS.md — plugins 插件推荐目录

本目录维护 Codex 插件的推荐索引，不默认承载或安装第三方插件。

- `README.md` 记录候选项目、兼容性、重叠风险和调研来源。
- `install-recommended.sh` 只在用户显式执行时调用 Codex marketplace；支持 profile、单插件、Git ref 和 dry-run，不复制第三方源码、不安装 npm 依赖、不自动信任 hooks。
- 只有实际可加载的插件才建立子目录，并保留 `.codex-plugin/plugin.json`；新增后核对入口、依赖、权限和路径。
- 不在此目录自动创建个人 marketplace、执行外部安装或复制未经审查的上游源码。
