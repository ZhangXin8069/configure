# Docker 开发环境操作

## 前提

当前文档主要面向 Windows + Docker Desktop：

1. Windows 10/11 已安装 Docker Desktop。
2. 启用 WSL 2 后端。
3. NVIDIA 驱动支持 WSL GPU。
4. 能在 PowerShell 中运行 `docker` 和 `wsl`。

检查：

```powershell
docker version
docker info
wsl --status
```

GPU 冒烟测试：

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

失败时不要继续执行深度学习镜像命令，先修复 Docker Desktop WSL 集成或 NVIDIA 驱动。

Linux 需要 Docker Engine、可用的 NVIDIA Container Toolkit 和当前用户对 Docker daemon 的访问权限；macOS 使用 Docker Desktop。后续 `docker` 命令相同，但 GPU 可用性取决于宿主平台和驱动。

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

## 进入容器

```powershell
docker exec -it computer-v20260708 bash
docker exec -it computer-v20260708 nvidia-smi
```

`bin/ddocker.sh` 和 `bin/ddocker.bat` 会通过 `docker ps --latest` 选择最近创建的容器，并进入可用 shell，见 [`../_commands/setup.md`](../_commands/setup.md)。

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

## 通用排障

| 现象 | 检查 |
|---|---|
| `nvidia-smi` 失败 | Docker Desktop GPU 配置、WSL 集成、NVIDIA 驱动 |
| 挂载目录为空 | PowerShell 路径、盘符共享、WSL `/mnt/<盘符>` 路径 |
| 容器名冲突 | `docker ps -a --filter name=<name>` |
| 进入后不是预期 shell | 容器内是否安装 bash/zsh |
| 镜像找不到 | `docker image ls` 与 `docker load` 输出标签 |

## 环境基线

| 组件 | 版本 |
|---|---|
| OS | Ubuntu 22.04 |
| GCC | 11.4.0 |
| Python | 3.10.12 |
| CUDA | 12.4.0 |
| QUDA | develop, SM80 |
| PyQCD | stab17 或 stab22，取决于镜像 |
