# 开发环境搭建指南

## 前置条件

- Windows 系统，已安装 Docker Desktop
- NVIDIA GPU 及驱动已正确安装
- 已注册 Docker Hub 账号

## 1. 登录 Docker

```bash
docker login
```

## 2. 拉取或加载镜像

### 方式一：从 Docker Hub 拉取

**v20250708：**

```bash
docker pull docker.io/zhangxin8069/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17
```

### 方式二：从本地 tar 文件加载

**v20250708：**

```bash
# 发送邮件到zhangxin8069@qq.com请求张鑫阿里云盘/资源库/Downloads/zip/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17.tar
docker load -i E:\Docker\computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17.tar
```

**v20260708：**

```bash
# 发送邮件到zhangxin8069@qq.com请求张鑫阿里云盘/资源库/Downloads/zip/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22.tar
docker load -i E:\Docker\computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22.tar
```

## 3. 启动容器

### v20250708

```bash
docker run -itd --gpus all --name v20250708 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /c/docker:/root/windows zhangxin8069/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17
```

### v20260708

```bash
docker run -itd --gpus all --name v20260708 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /c/docker:/root/windows zhangxin8069/computer-v20260708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab22
```

## 4. 进入容器

```bash
docker exec -it v20250708 bash
```

```bash
docker exec -it v20260708 bash
```

## 5. 保存容器修改为新镜像

在容器内完成环境配置后，执行以下命令将修改保存为新镜像：

```bash
docker commit <容器ID> zhangxin8069/computer-v20250708:<新标签>
```

```bash
docker commit <容器ID> zhangxin8069/computer-v20260708:<新标签>
```

## 6. 导出/导入镜像

### 导出镜像为 tar 文件

```bash
docker save -o <文件名>.tar zhangxin8069/computer-v20250708:<标签>
```

```bash
docker save -o <文件名>.tar zhangxin8069/computer-v20260708:<标签>
```

### 从 tar 文件导入镜像

```bash
docker load -i <文件名>.tar
```

## 7. 推送镜像到 Docker Hub

```bash
docker push zhangxin8069/computer-v20250708:<标签>
```

```bash
docker push zhangxin8069/computer-v20260708:<标签>
```

## 环境信息

| 组件 | 版本 |
|------|------|
| OS | Ubuntu 22.04 |
| GCC | 11.4.0 |
| Python | 3.10.12 |
| CUDA | 12.4.0 |
| QUDA | develop (SM80) |
| PyQCD | stab22 (v20260708) / stab17 (v20250708) |

## 常用命令

```bash
# 查看运行中的容器
docker container ls

# 查看所有镜像
docker image ls

# 停止容器
docker stop v20250708
docker stop v20260708

# 启动已存在的容器
docker start v20250708
docker start v20260708

# 删除容器
docker rm v20250708
docker rm v20260708

# 删除镜像
docker rmi <镜像ID>
```
