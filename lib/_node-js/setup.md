# Node.js 安装与版本管理

面向本库中依赖 Node.js 的工具（当前主要为 [`../_command-code/`](../_command-code/)）。默认目标是
Node.js 22，可通过参数或 `NODE_VERSION` 覆盖。参考实现日期为 2026-11-03。

## 入口

| 文件 | 用途 |
|---|---|
| `install.sh` | 统一入口：检查现有 Node.js，必要时委派 `nvm-install.sh` 安装 |
| `nvm-install.sh` | 上游 nvm v0.39.7 安装器，保持原样，读取 `NODE_VERSION` |
| `install.bat` | 原生 Windows 用户级安装，不需要管理员权限 |
| `install.test.sh` | 隔离环境的回归测试 |
| `setup.md` | 本文档 |

## 检查

```bash
bash lib/_node-js/install.sh --check
node --version
npm --version
```

`--check` 只读，不修改任何文件：主版本满足目标且 npm 可用时返回 0，否则返回 1 并给出升级命令。
Windows 使用：

```bat
lib\_node-js\install.bat --check
```

## 一键安装（nvm）

```bash
bash lib/_node-js/install.sh          # 安装最新 22.x
bash lib/_node-js/install.sh 24       # 安装最新 24.x
bash lib/_node-js/install.sh 22.11.0  # 安装指定完整版本
```

等价的显式环境变量写法：

```bash
NODE_VERSION=24 bash lib/_node-js/install.sh
```

行为约定：

1. 已存在满足目标主版本且 npm 可用的 Node.js 时直接返回，不写任何文件。
2. 否则调用 `nvm-install.sh`：安装 nvm 到 `$HOME/.nvm`（设置 `XDG_CONFIG_HOME` 时为
   `$XDG_CONFIG_HOME/nvm`，可用 `NVM_DIR` 覆盖），再安装目标 Node.js。
3. nvm 安装器默认把加载语句写入当前 shell 的启动文件（`~/.bashrc`、`~/.zshrc` 等）。
   不接受修改时使用 `PROFILE=/dev/null`。
4. 安装完成后，新登录 shell 会自动加载 nvm；当前终端需手动执行：

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22
```

nvm 安装器需要 `git`，或设置 `METHOD=script` 后使用 `curl`/`wget`。完整环境变量与上游行为见
<https://github.com/nvm-sh/nvm#installing-and-updating>。

## HPC 无 root：官方二进制

登录节点通常没有 root 权限，优先复用集群已有环境；需要自带 Node.js 时，可把官方预编译包解压到
`$HOME/.local/node`，不修改系统目录。`NODE_ROOT` 与 `NODE_MAJOR` 可覆盖默认值：

```bash
installer="$(mktemp "${TMPDIR:-/tmp}/install-node.XXXXXX")"
cat > "$installer" <<'NODE_INSTALL'
#!/usr/bin/env bash
set -euo pipefail

node_root="${NODE_ROOT:-$HOME/.local/node}"
node_major="${NODE_MAJOR:-22}"

case "$(uname -s)" in
    Linux)  node_os=linux ;;
    Darwin) node_os=darwin ;;
    *) echo "不支持的系统: $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64)  node_arch=x64 ;;
    aarch64|arm64) node_arch=arm64 ;;
    *) echo "不支持的架构: $(uname -m)；请从 https://nodejs.org/dist/ 手动选择" >&2; exit 1 ;;
esac

node_version="$(curl -fsSL "https://nodejs.org/dist/latest-v${node_major}.x/SHASUMS256.txt" |
    sed -n "s/.*node-v\([0-9][0-9.]*\)-${node_os}-${node_arch}\.tar\.xz/\1/p" |
    head -n 1 || true)"
[ -n "$node_version" ] || { echo '无法获取 Node.js 版本，请检查网络或代理设置' >&2; exit 1; }

archive="$(mktemp "${TMPDIR:-/tmp}/node.XXXXXX")"
trap 'rm -f "$archive"' EXIT
curl -fsSLo "$archive" "https://nodejs.org/dist/v${node_version}/node-v${node_version}-${node_os}-${node_arch}.tar.xz"
mkdir -p "$node_root"
tar -xJf "$archive" -C "$node_root" --strip-components=1
"$node_root/bin/node" --version
printf 'Node.js %s 已安装到 %s\n' "$node_version" "$node_root"
NODE_INSTALL
bash "$installer"
rm -f "$installer"
```

把 Node.js 加入登录 shell（幂等；按实际 shell 调整文件名）：

```bash
node_bin="$HOME/.local/node/bin"
profile="$HOME/.bashrc"
[ "${SHELL##*/}" = "zsh" ] && profile="$HOME/.zshrc"
grep -Fqs "$node_bin" "$profile" 2>/dev/null || \
    printf '\n# Node.js\nexport PATH="%s:$PATH"\n' "$node_bin" >> "$profile"
export PATH="$node_bin:$PATH"
node --version
npm --version
```

网络受限时，可在可联网机器下载同版本的 `node-v*-<os>-<arch>.tar.xz` 后复制到目标机器，再执行：

```bash
mkdir -p "$HOME/.local/node"
tar -xJf node-v*-linux-x64.tar.xz -C "$HOME/.local/node" --strip-components=1
```

没有 `curl` 时可将 `curl -fsSLo <文件> <URL>` 换成 `wget -qO <文件> <URL>`；需要代理时先设置
`https_proxy`。官方 Node.js 22 二进制要求 glibc 2.28+；CentOS 7 等较老系统若报
`GLIBC_2.28 not found`，改用 conda-forge 的 `nodejs`、集群模块或自行编译。

## module 与 conda

HPC 常通过 environment modules 或 conda 管理 Node.js，优先复用这些环境：

```bash
module avail node 2>/dev/null || module avail nodejs 2>/dev/null || true
module load nodejs        # 模块名以 module avail 的实际输出为准
node --version
```

```bash
conda create -n node22 -c conda-forge nodejs=22
conda activate node22
node --version
```

`node --version` 显示 `v22` 或更高即可。登录节点与计算节点的环境可能不同，请在真正运行
Node.js 工具的节点上检查。

## Windows

```bat
lib\_node-js\install.bat
lib\_node-js\install.bat --check
lib\_node-js\install.bat 24
```

安装器从 <https://nodejs.org/dist/> 解析目标主版本的最新 `win-x64` / `win-arm64` zip，解压到
`%LOCALAPPDATA%\nodejs`，把该目录幂等加入用户 PATH。默认目录可用 `NODE_INSTALL_DIR` 覆盖。
PATH 修改只对新终端生效，安装后请重新打开终端。

也可以使用系统包管理器，例如：

```powershell
winget install OpenJS.NodeJS.LTS
```

`install.bat` 不需要管理员权限；`winget` 是否提权由包管理器决定。安装后先在 `cmd.exe` 中确认
`node --version`，再运行 `lib\_command-code\install.bat`。

## npm 全局前缀

本库的 Node.js 工具统一把可执行入口放在 `$HOME/.local/bin`（Windows 为
`%USERPROFILE%\.local\bin`）。安装全局包时显式指定 prefix 的父目录，避免入口落入版本化的
Node.js 目录：

```bash
npm install --global --prefix "$HOME/.local" <package>
```

`_command-code/install.sh` 已内置该前缀；手工安装其他工具时保持同样约定，并在 PATH 中只引用
稳定目录，不写死 `~/.nvm/versions/node/vX.Y.Z/bin` 之类的路径。

## 验证

```bash
bash -n lib/_node-js/install.sh
bash -n lib/_node-js/nvm-install.sh
bash -n lib/_node-js/install.test.sh
bash lib/_node-js/install.test.sh
node --version
npm --version
```

Windows 批处理无法在 Unix 主机上真实执行，至少检查 `install.bat --help` 的静态入口；完整验证需在
目标 Windows 机器上完成。

## 排障

- **非交互 shell 找不到 node**：nvm 只在登录 shell 的启动文件中加载。显式设置 `NVM_DIR` 并
  `source "$NVM_DIR/nvm.sh"`，或直接使用 nvm 安装目录下的绝对路径。
- **`node` 与 `npm` 指向不同来源**：执行 `command -v node npm` 并比较路径；确保 `nvm use` 或
  `module load` 在 PATH 中优先。
- **npm registry 或 nodejs.org 不可达**：按集群文档配置 `https_proxy` 或 npm 镜像。只有
  `install.bat` 与官方二进制脚本需要访问 nodejs.org；nvm 的 `git` 方式还需要访问 GitHub。
- **`--check` 通过但工具仍报版本过低**：在工具实际运行的 shell 中重新检查，避免登录节点与计算
  节点环境不一致。
- **Windows 安装后仍是旧版本**：重新打开终端，或用 `where node` 确认 PATH 顺序；不要同时保留
  多个 Node.js 安装目录在 PATH 前部。
- **glibc 过旧**：改用 conda/模块，或自行编译；不要强行使用不兼容的官方二进制。

不要在脚本、Node.js 工具配置或本文档中写入真实 token、API key 或带凭据的 registry URL。

## 回滚

- nvm：先 `nvm uninstall <version>`，再删除 `$NVM_DIR`，并从 `~/.bashrc`、`~/.zshrc` 等文件中
  移除 nvm 加载语句。
- 官方二进制：删除 `$HOME/.local/node`，并从 shell 启动文件移除对应的 `PATH` 行。
- Windows：删除 `%LOCALAPPDATA%\nodejs`，再从用户 PATH 中移除该目录。
- 集群提供的 Node.js 由管理员维护，不要删除或覆盖系统目录。
