# AGENTS.md — docs 参考文档

参考文档、包依赖清单与图片素材。供 `bin/` 脚本消费或作为独立指南。

## 包依赖清单（目标态，非一次性安装脚本）

- `apt_requirement.txt` — APT 包，由 `bin/apt_install.sh` 读取（`sudo apt install $(cat docs/apt_requirement.txt)`）。改此文件后重跑脚本即生效
- `pip_requirement.txt` — Python 包（PyTorch、NumPy、SciPy、Matplotlib、Jupyter、mpi4py、Cython 等），由 `bin/pip_install.sh` 读取；以 `#` 注释的行被排除

## 指南

- `julab_settings.md` — Jupyter Lab 配置指南（中文语言包、LSP、Cling C++ 内核、远程连接）
- `openmc_settings.md` — OpenMC（蒙特卡洛中子输运）在 WSL2/Ubuntu 上的安装指南（清华/中科大镜像、源码编译、截面数据）

## 图片素材

`background.jpeg`（桌面壁纸）、`classicAvatar.png`（头像）、`clqcd.png`（CLQCD logo）、`desktop.png`（桌面截图）——静态资源，被配置或文档引用。
