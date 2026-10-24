# Docker 开发环境操作

WSL 2 的安装、`.wslconfig`、发行版导入迁移和磁盘维护见 [`wsl.md`](wsl.md)。本文只保留 Docker Desktop 与容器侧操作，避免把 WSL 发行版维护和容器数据维护混为一谈。

## 前提

当前文档主要面向 Windows + Docker Desktop：

1. Windows 10/11 已安装 Docker Desktop。
2. 启用 WSL 2 后端。
3. NVIDIA 驱动支持 WSL GPU。
4. 能在 PowerShell 中运行 `docker` 和 `wsl`。

检查：

```powershell
docker context ls
docker version
docker info
wsl --status
```

Docker Desktop 应使用 Linux containers 和 WSL 2 backend；`docker context ls` 中带 `*` 的上下文应指向 Docker Desktop。WSL 内调用 `docker` 前，还需在 **Settings > Resources > WSL Integration** 为对应发行版启用集成。

GPU 冒烟测试：

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

失败时不要继续执行深度学习镜像命令，先修复 Docker Desktop WSL 集成或 NVIDIA 驱动。

Linux 需要 Docker Engine、可用的 NVIDIA Container Toolkit 和当前用户对 Docker daemon 的访问权限；macOS 使用 Docker Desktop。后续 `docker` 命令相同，但 GPU 可用性取决于宿主平台和驱动。

## Docker Desktop 与 WSL 集成

不要在启用 Docker Desktop 集成的 WSL 发行版中另行安装并启动 Docker Engine。两套 daemon 会争用 `docker` 客户端配置、socket、iptables 和端口，排障时应先确认实际连接的 daemon：

```powershell
docker context ls
docker context inspect desktop-linux
wsl -d Ubuntu -- docker context ls
```

WSL 内应看到 `desktop-linux` 上下文，并能访问 Docker Desktop 的 socket。若 `docker info` 失败：

1. 确认 Docker Desktop 已启动且处于 Linux containers 模式。
2. 确认目标发行版使用 WSL 2：`wsl --list --verbose`。
3. 在 Docker Desktop 的 WSL Integration 中启用该发行版并 Apply。
4. 重新打开 WSL shell，再运行 `docker context use desktop-linux`。

不要手动注册、移动、压缩或注销 Docker Desktop 自建的 `docker-desktop` 发行版及其数据 VHDX。它们由 Docker Desktop 管理，应在 **Settings > Resources > Advanced** 中迁移数据目录或通过 Docker Desktop 的重置流程处理。

## 资源与存储

Docker Desktop 的内存、CPU、Swap 和虚拟磁盘由 WSL 2 虚拟机及 Docker Desktop 设置共同约束。不要同时用手工 `.wslconfig` 和 Docker Desktop 界面盲目压低资源上限；先确认限制最终落在哪一层。

最低可用性检查：

```powershell
docker info --format 'CPUs={{.NCPU}} Memory={{.MemTotal}} Driver={{.Driver}}'
docker system df
docker system df -v
```

Linux 容器内可用内存不等于 Windows 物理内存。深度学习任务应确认容器可见内存、共享内存和 GPU：

```powershell
docker run --rm `
  --gpus all `
  --shm-size 8g `
  nvidia/cuda:12.4.0-base-ubuntu22.04 `
  bash -lc 'nvidia-smi; df -h /dev/shm; free -h'
```

`--shm-size` 对 PyTorch DataLoader、多进程训练和部分数据库容器很重要。只提高共享内存而不限制并发进程仍可能耗尽宿主内存。

Docker Desktop 的镜像和容器层默认位于 `%LOCALAPPDATA%\Docker\wsl`。需要在 Windows 内保存大文件时放到独立数据盘，不要通过 `/mnt/c` 或 `C:\Users` 承载高频构建 I/O。迁移 Docker Desktop 数据目录应使用设置界面，不能直接剪切正在使用的 VHDX。

## 镜像版本

| 名称 | 标签 |
|---|---|
| v20250708 | `zhangxin8069/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17` |
| v20260708 | `zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22` |

## 拉取镜像

公开镜像通常不要求预先登录，但匿名拉取可能受到速率限制：

```powershell
docker pull docker.io/zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
```

需要登录时：

```powershell
docker login
```

不要将密码写入脚本或命令历史中的明文参数。

## 从本地 tar 加载

Windows 文件名不能包含冒号。收到带镜像标签名称的 tar 文件后，应先重命名为合法文件名，例如：

```text
computer-v20260708_ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22.tar
```

加载：

```powershell
docker load -i E:\Docker\computer-v20260708_ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22.tar
docker image ls | Select-String 'computer-v20260708'
```

`docker load` 恢复的是镜像及其原始标签。`docker import` 只会从文件系统归档创建单层镜像，两者不等价。

## 启动容器

PowerShell：

```powershell
docker run -itd `
  --gpus all `
  --name computer-v20260708 `
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility `
  -e NVIDIA_VISIBLE_DEVICES=all `
  -v "E:\Docker:/root/windows" `
  zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
```

WSL 路径写法：

```bash
docker run -itd \
  --gpus all \
  --name computer-v20260708 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v /mnt/e/Docker:/root/windows \
  zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
```

Git Bash 使用 `/e/Docker`：

```bash
docker run -itd \
  --gpus all \
  --name computer-v20260708 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v /e/Docker:/root/windows \
  zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
```

旧版 v20250708 只需替换镜像标签与容器名。原文档中的 `/c/docker` 与 `/d/docker` 是 Git Bash 路径，不是 PowerShell 路径；不要把两者混用。

长期开发优先使用显式命名挂载，减少路径被 shell 重写的机会：

```powershell
docker run -itd `
  --name dev-shell `
  --mount 'type=bind,source=E:\Docker\workspace,target=/workspace' `
  --workdir /workspace `
  --init `
  zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22 `
  bash
```

挂载源码时，宿主目录与容器目标必须使用对应平台的路径语法。不要把 Docker socket、SSH agent socket 或整个用户主目录无条件挂入不可信容器。

## Docker Compose 开发环境

固定团队环境时，用 Compose 固化工作目录、共享内存、GPU 与环境变量。下例只展示可复用骨架，镜像标签仍应使用不可变的版本标签：

```yaml
services:
  dev:
    image: zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
    init: true
    working_dir: /workspace
    stdin_open: true
    tty: true
    shm_size: 8gb
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility
    volumes:
      - type: bind
        source: 'E:\Docker\workspace'
        target: /workspace
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

常用操作：

```powershell
docker compose up -d
docker compose exec dev bash
docker compose logs --tail 100 dev
docker compose config
docker compose down
```

`docker compose down -v` 会删除 Compose 命名卷，不能作为普通停止命令。需要重建容器但保留命名卷时使用 `docker compose up -d --force-recreate`，不要附加 `-v`。

## 进入容器

```powershell
docker exec -it computer-v20260708 bash
docker exec -it computer-v20260708 nvidia-smi
```

`bin/ddocker.sh` 和 `bin/ddocker.bat` 会通过 `docker ps --latest` 选择最近创建的容器，并进入可用 shell，见 [`../_commands/setup.md`](../_commands/setup.md)。

容器内排障优先使用只读检查：

```powershell
docker inspect --format '{{json .State}}' computer-v20260708
docker inspect --format '{{json .Mounts}}' computer-v20260708
docker stats --no-stream computer-v20260708
docker top computer-v20260708
```

需要自动重启的服务可在创建时加 `--restart unless-stopped`，但交互式开发容器通常不要启用。健康检查应由镜像或 Compose 定义真实协议探测，不能只看进程是否存在。

## 生命周期

```powershell
docker ps
docker ps -a
docker stop computer-v20260708
docker start computer-v20260708
docker restart computer-v20260708
docker logs --tail 100 computer-v20260708
```

删除容器会清空容器层中的修改：

```powershell
docker rm computer-v20260708
```

只应在修改已提交或挂载到宿主机的数据已确认安全后执行。

## 提交为镜像

容器内长期需要保留的修改先提交：

```powershell
docker commit computer-v20260708 zhangxin8069/computer-v20260708:<新标签>
```

镜像标签应表达用途、版本或日期。不要把“latest”作为唯一可追溯版本。

## 保存和加载镜像

导出镜像：

```powershell
docker save -o E:\Docker\computer-v20260708_<标签>.tar zhangxin8069/computer-v20260708:<标签>
```

重新导入：

```powershell
docker load -i E:\Docker\computer-v20260708_<标签>.tar
```

如果已有未提交的容器修改，需要的是 `docker commit` 后 `docker save`，不是直接对容器执行 `docker export`。

镜像归档与容器数据备份是两件事：

- `docker save` 保存镜像层和标签，便于离线迁移。
- 绑定挂载的数据由宿主文件系统负责备份。
- 命名卷应通过临时容器打包，不能只备份镜像。

备份一个命名卷：

```powershell
docker run --rm `
  --mount 'type=volume,source=<卷名>,target=/data,readonly' `
  --mount 'type=bind,source=E:\Docker\backup,target=/backup' `
  ubuntu:22.04 `
  tar -C /data -czf /backup/<卷名>.tar.gz .
```

恢复前确认目标卷为空。覆盖现有卷属于数据破坏性操作，不能默认执行。

## 推送

```powershell
docker push zhangxin8069/computer-v20260708:<标签>
```

推送前检查：

```powershell
docker image inspect zhangxin8069/computer-v20260708:<标签>
docker history zhangxin8069/computer-v20260708:<标签>
```

确认镜像中不含 SSH 私钥、API key、浏览器凭据和临时数据集。

## 清理

```powershell
docker image ls
docker rmi <镜像ID>
docker system df
```

`docker rm`、`docker rmi`、`docker system prune` 都可能删除不可恢复的数据。本文档不提供自动清理脚本；先确认目标容器和镜像 ID。

安全诊断顺序：

```powershell
docker system df -v
docker image ls --filter dangling=true
docker volume ls
docker ps -a --size
```

先区分悬空镜像、停止容器、未使用卷和构建缓存，再决定清理范围。`docker system prune --volumes`、`docker volume prune`、`docker builder prune -a` 都可能造成不可恢复的数据删除，必须单独确认目标。

## 端口、日志与构建上下文

端口冲突：

```powershell
docker port computer-v20260708
netstat -ano | Select-String ':8000'
docker inspect --format '{{json .NetworkSettings.Ports}}' computer-v20260708
```

查看带时间戳日志并持续跟踪：

```powershell
docker logs --timestamps --tail 200 --follow computer-v20260708
```

构建慢时先检查上下文，而不是立即增加 CPU。大型数据目录应通过 `.dockerignore` 排除：

```text
.git
**/.cache
**/__pycache__
**/*.tar
data/
results/
```

`.dockerignore` 只影响发送给 builder 的上下文，不会自动缩小已有镜像。镜像体积仍应通过分层、清理构建缓存、避免把密钥或大数据复制进镜像来控制。

## 通用排障

| 现象 | 检查 |
|---|---|
| `nvidia-smi` 失败 | Docker Desktop GPU 配置、WSL 集成、NVIDIA 驱动 |
| 挂载目录为空 | PowerShell 路径、盘符共享、WSL `/mnt/<盘符>` 路径 |
| 容器名冲突 | `docker ps -a --filter name=<name>` |
| 进入后不是预期 shell | 容器内是否安装 bash/zsh |
| 镜像找不到 | `docker image ls` 与 `docker load` 输出标签 |
| `docker info` 连到错误 daemon | `docker context ls`、`docker context inspect` |
| WSL 内没有 `docker` 命令 | Docker Desktop WSL Integration 是否启用 |
| 构建上下文异常巨大 | 检查构建目录及 `.dockerignore` |
| 容器频繁退出 137 | 检查内存上限、OOM 与宿主资源压力 |
| GPU 可见但训练 OOM | 区分显存 OOM、共享内存不足与宿主内存不足 |

## 安全边界

Docker daemon 访问权限通常等价于宿主 root 权限。不要把 `/var/run/docker.sock`、Windows named pipe、宿主根目录或凭据目录挂载给不可信容器，也不要在镜像层中写入密钥。

提交或推送前检查：

```powershell
docker history --no-trunc zhangxin8069/computer-v20260708:<标签>
docker run --rm --entrypoint sh zhangxin8069/computer-v20260708:<标签> -c 'env | sort'
```

第二条命令会显示镜像默认环境变量；若镜像本身包含密钥，应停止推送并轮换密钥。不要把该输出原样粘贴到公开日志。

## 环境基线

| 组件 | 版本 |
|---|---|
| OS | Ubuntu 22.04 |
| GCC | 11.4.0 |
| Python | 3.10.12 |
| CUDA | 12.4.0 |
| QUDA | develop, SM80 |
| PyQCD | stab17 或 stab22，取决于镜像 |
