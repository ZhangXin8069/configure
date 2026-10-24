# AGENTS.md — _docker

Docker 与 WSL 开发环境参考文档目录，无脚本，不部署到 `$HOME`：

- `setup.md`：Docker Desktop、镜像、容器、Compose、GPU、存储与排障。
- `wsl.md`：WSL 2 安装配置、发行版导入/迁移、磁盘维护及 Docker Desktop 集成。

文档以 Windows Docker Desktop 和 WSL 2 为主要环境，同时标明 PowerShell、cmd 与 Git Bash/WSL 的路径差异。删除容器、镜像或 WSL 发行版，执行 `wsl --unregister`、`docker system prune`、磁盘压缩及 `--purge` 类操作必须由用户显式确认，agent 不自动执行。
