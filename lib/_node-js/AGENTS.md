# AGENTS.md — _node-js

Node.js 22+ 安装与版本检查目录。供 `_command-code` 等 Node.js 工具在运行前复用；脚本手动执行，不随 shell 自动部署。

- `install.sh` — 统一入口。`--check` 只读检查；当前主版本已满足目标且 npm 可用时不改动系统；否则调用同目录 `nvm-install.sh`。位置参数或 `NODE_VERSION` 覆盖目标版本（默认 22），`PROFILE=/dev/null` 阻止写入 shell 启动文件。**稳定入口约定**：node/npm/npx 软链到 `${NODE_BIN_DIR:-$HOME/.local/bin}`（与 `_codex`、`_claude-code` 一致，PATH 只引用该稳定目录，不写死 nvm 版本路径）；已满足分支同样执行链接；源与目标同一路径时跳过，避免自指软链；用户自有的非软链文件保留不覆盖。
- `nvm-install.sh` — 上游 nvm v0.39.7 安装器，原样保留；`install.sh` 通过 `NODE_VERSION` 驱动其安装 Node.js。也可直接运行 `NODE_VERSION=22 bash nvm-install.sh`。
- `install.bat` — 原生 Windows 用户级安装；从 nodejs.org 解析目标主版本的最新 win-x64/arm64 zip，运行时解压到 `%USERPROFILE%\.local\node`（`NODE_INSTALL_DIR` 可覆盖），并在 `%USERPROFILE%\.local\bin`（`NODE_BIN_DIR` 可覆盖）生成 node/npm/npx 稳定入口（优先硬链接，失败回退绝对路径转发脚本），PATH 只写入该稳定目录；幂等，无需管理员。
- `install.test.sh` — 隔离 HOME、NVM_DIR 和假 node/npm 的回归测试，覆盖已满足时复用、20→22 升级委派、`v` 前缀、非法参数、`--check`、稳定入口软链、`NODE_BIN_DIR` 覆盖、自指保护与用户自有文件不被覆盖。
- `setup.md` — 检查、nvm 一键安装、HPC 无 root 官方二进制、module/conda、Windows、npm 全局前缀、验证与回滚。

默认目标是 22（Command Code 的最低要求），需要其他版本时显式传入。nvm 方式会写入 `~/.bashrc`、`~/.zshrc` 等启动文件；不接受修改时使用 `PROFILE=/dev/null`。官方 Node.js 22 二进制要求 glibc 2.28+。
