# AGENTS.md — _docker

Docker Desktop 与容器开发环境参考文档目录，无脚本，不部署到 `$HOME`：

- `setup.md`：Docker Desktop、镜像、容器、Compose、GPU、存储与排障。

WSL 2 的安装、发行版导入/迁移、磁盘维护和发行版内开发环境见 [`../_wsl/setup.md`](../_wsl/setup.md)；Docker Desktop 自建的 `docker-desktop` 发行版和 VHDX 仍由 Docker Desktop 管理，不套用 WSL 发行版迁移步骤。

文档以 Windows Docker Desktop 为主要环境，同时标明 PowerShell、cmd 与 Git Bash/WSL 的路径差异。删除容器、镜像或 Docker 数据，执行 `docker system prune`、`docker volume prune`、`docker builder prune` 及 `--purge` 类操作必须由用户显式确认，agent 不自动执行。WSL 发行版的 `wsl --unregister`、磁盘压缩等操作以 `_wsl` 目录的确认清单为准。
