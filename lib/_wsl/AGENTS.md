# AGENTS.md — _wsl

Windows Subsystem for Linux（WSL 2）稳定操作入口，无脚本，不部署到 `$HOME`：

- `setup.md`：WSL 2 安装升级、`.wslconfig`、`/etc/wsl.conf`、发行版导入/克隆/迁移、VHDX 备份与压缩、文件系统/网络/GPU、发行版内开发环境、版本快照参考、故障表与检查清单。
- `AGENTS.md`：本目录契约、边界与破坏性操作确认清单。

## 边界

| 目录 | 职责 |
|---|---|
| `_wsl/` | WSL 2 宿主侧配置、发行版生命周期、VHDX 与发行版内 Linux 开发环境 |
| `_docker/` | Docker Desktop、镜像、容器、Compose、GPU 与容器数据；Docker Desktop 自建的 `docker-desktop` 发行版和 VHDX 由 Docker Desktop 管理，不套用本目录的发行版迁移步骤 |
| `wsl-v20261107/` | 2026-11-07 WSL 机器的版本化环境快照；`env.sh` 是实际加载的环境变量，`setup.md` 是一次性安装命令记录。更新配置时新建当天日期目录，不直接改旧快照 |

Docker 与 WSL 的集成边界仍以 [`../_docker/setup.md`](../_docker/setup.md) 为准；发行版内环境加载、包管理、SSH 和 Vim 的通用规则由 `_env/`、`_package/`、`_ssh/`、`_vim/` 等稳定入口维护，本目录只记录 WSL 场景下的组合方式。

## 破坏性操作确认

以下操作不可撤销或可能损坏正在使用的磁盘，`setup.md` 只提供步骤；agent 不得自动执行，必须由用户逐项确认目标、备份和回滚路径：

- `wsl --unregister <发行版>`：永久删除该发行版注册信息与存储。
- `wsl --shutdown`：停止全部 WSL 实例，可能中断 Docker Desktop 构建和正在写入的数据。
- `wsl --manage <发行版> --move <路径>`：迁移发行版 VHDX，失败可能留下不可用注册或残留文件。
- `wsl --import-in-place` 覆盖同名发行版或直接注册唯一备份：注册前保留独立可用备份。
- `diskpart` 的 `compact vdisk`、`attach vdisk readonly` / `detach vdisk`：压缩或挂载 VHDX 前必须有可用备份，且没有进程占用。
- 删除、移动或覆盖 `ext4.vhdx`，以及对 VHDX 所在目录执行同步、备份或去重软件写入。
- 修改 `.wslconfig` 或 `/etc/wsl.conf` 后未验证就覆盖旧配置。
- 删除 `~/env.sh`、`~/env-key.sh` 或其中的凭据；环境入口失效时先备份再重建。

## 交叉引用

- Docker 容器与 GPU：[`../_docker/setup.md`](../_docker/setup.md)
- 版本化 WSL 环境：[`../wsl-v20261107/setup.md`](../wsl-v20261107/setup.md)、[`../wsl-v20261107/env.sh`](../wsl-v20261107/env.sh)
- 环境三层加载：[`../_env/setup.md`](../_env/setup.md)
- Shell 部署：[`../_shell/setup.md`](../_shell/setup.md)
- Vim 部署：[`../_vim/setup.md`](../_vim/setup.md)
- Git 与 SSH：[`../_git/setup.md`](../_git/setup.md)、[`../_ssh/setup.md`](../_ssh/setup.md)
- Windows 侧入口：[`../_windows/setup.md`](../_windows/setup.md)
- ZeroTier（含 WSL 段落）：[`../_zerotier/setup.md`](../_zerotier/setup.md)
- 包清单与可执行资源：[`../_package/setup.md`](../_package/setup.md)
- 用户命令总索引：[`../_commands/setup.md`](../_commands/setup.md)
- Node.js 与 Command Code：[`../_node-js/setup.md`](../_node-js/setup.md)、[`../_command-code/setup.md`](../_command-code/setup.md)
