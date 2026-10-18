# AGENTS.md — _claude-code 稳定目录

Claude Code 安装包的稳定路径。安装脚本文件与 `../claude-code-v20260706/` 保持真实文件副本关系；`setup.md` 是本任务重新整理后的当前操作文档，版本化目录中的历史说明未改写。

- 用途：提供无版本后缀的稳定路径，便于脚本/文档引用最新 Claude Code 安装
- 修改脚本行为时先改 `claude-code-v20260706/` 下的维护源，再同步本目录
- 修改操作说明时只更新本目录 `setup.md` 即可，避免改写历史版本目录
- 离线二进制、cc-switch CLI 和 GUI 包默认不随仓库存在；从本目录运行 `download_all.sh` 时按需下载到本目录
- `setup.md` 记录安装、配置、离线下载、校验、卸载和密钥边界
- `.agent.*.log` 为创建过程日志，不入库
