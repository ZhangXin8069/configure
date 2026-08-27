# AGENTS.md — _clash

Clash 代理环境的本地安装包包装目录，不直接部署到 `$HOME`。目录中的 `clash-for-linux.tar.gz` 是外来 `clash-for-linux` gitlink 的离线归档，`setup.sh` 负责动态定位、解压和检查。

## 使用约定

- `bash setup.sh --check`：只检查已解压的 `env.sh`，包括 Bash 语法、代理变量和增强检查函数。
- `bash setup.sh`：校验压缩包后解压到 `clash-for-linux/`，会对已有目标做 tar 增量覆盖，然后通过 `source env.sh` 检查；确认需要刷新上游副本时才执行。
- `setup.sh` 使用 `BASH_SOURCE` 和 Git 根目录定位，不要硬编码 `/root/...` 路径。
- `clash-for-linux/` 是外来组件；其实现和自身说明不在本目录维护，父目录只维护归档、包装脚本和调用边界。
