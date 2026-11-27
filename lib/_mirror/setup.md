# 国内镜像源配置

面向国内网络环境中各类开发环境（发行版包管理、conda、Python、Node.js、Rust、Go、Docker、GitHub 资产、CTAN/HF 等）的下载源选择、配置写法、验证与回滚。本文只描述"从哪个地址取包"，安装流程本身仍由 [`../_wsl/setup.md`](../_wsl/setup.md)、[`../_docker/setup.md`](../_docker/setup.md)、[`../_node-js/setup.md`](../_node-js/setup.md) 等入口负责。

文中地址均在 **2026-11-27** 实测过最小可验证路径（目录列表、`Release` 文件、`repodata.json`、`@v/list`、真实 tarball 等）。镜像站的下游策略会变化，使用前按每个小节的"验证"命令自查，不要只信本文。

## 选择与边界

| 场景 | 做法 |
|---|---|
| 能稳定走代理 | 用代理，不换源（[`../_clash/setup.md`](../_clash/setup.md)）；同一工具不要同时配代理和镜像 |
| 代理不可用、只覆盖部分域名、需长期无人值守 | 换源，只改真正慢的那个生态 |
| 需要可复现、可归档的安装包 | 优先带版本号且带 `.sha256` 的地址 |
| CI、容器构建 | 在构建参数或配置文件里固定源，不要依赖操作者本机的全局配置 |

通用约定：

- 系统级路径（`/etc/apt/sources.list*`、`/etc/pip.conf`、`/etc/docker/daemon.json`）属于系统配置变更，执行前需单独确认；用户级文件（`~/.condarc`、`~/.npmrc`、`~/.config/pip/pip.conf`、`~/.cargo/config.toml`）优先。
- 覆盖前先备份为 `*.bak.$(date +%Y%m%d-%H%M%S)`，不要就地覆盖。
- 只用 HTTPS 地址；镜像 URL 不含 userinfo，私有源凭据从 Git 外环境读取。
- 镜像站主机分工：`mirrors.tuna.tsinghua.edu.cn` 是主站；`mirrors-i.tuna.tsinghua.edu.cn` 是其静态文件/大文件节点（响应头同为 `x-tuna-mirror-id: nanomirrors`）。抽样比对（`ubuntu/dists/noble/Release`、`pypi/web/simple/pip/`）两站 `content-length` 一致，Miniforge 安装包哈希也一致，见 [`../_wsl/setup.md`](../_wsl/setup.md) 的 Miniforge 小节；换主机时仍以实际哈希为准。
- 其他可替代站点：USTC `mirrors.ustc.edu.cn`、南大 `mirrors.nju.edu.cn`、北外 `mirrors.bfsu.edu.cn`、阿里 `mirrors.aliyun.com`、腾讯 `mirrors.cloud.tencent.com`、华为 `repo.huaweicloud.com`、CERNET 联邦 `mirrors.cernet.edu.cn`。跨站点替换时保持路径后缀不变。

## Ubuntu / Debian APT

### 定位与备份

```bash
cat /etc/os-release
ls /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null
```

Ubuntu 24.04+ 与 Debian 12+ 默认使用 deb822 格式 `/etc/apt/sources.list.d/ubuntu.sources`（或 `debian.sources`）；更老的系统仍是单行式 `/etc/apt/sources.list`。两者不要同时写同一套件，否则 `apt update` 会重复报错。

```bash
sudo cp -a /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%Y%m%d-%H%M%S)
sudo cp -a /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
```

### deb822（Ubuntu 24.04+ / Debian 12+）

把 `ubuntu.sources` 的 `URIs:` 换成镜像，`Suites:`/`Components:` 保留本机实际值（不要照抄示例里的代号）：

```text
Types: deb
URIs: https://mirrors.tuna.tsinghua.edu.cn/ubuntu
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

Debian 对应把 `URIs` 改 `https://mirrors.tuna.tsinghua.edu.cn/debian`、`Components: main contrib non-free non-free-firmware`、`Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg`。

安全更新：TUNA 的帮助模板把 `*-security` 仍指向官方 `http://security.ubuntu.com/ubuntu/`（Debian 为 `security.debian.org/debian-security`）。镜像站也镜像了安全套件（`/ubuntu/dists/noble-security/Release`、`/debian-security/dists/trixie-security/Release` 实测可用），但官方模板不这么写，默认遵循模板：

```text
Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

### 传统单行式

按 `/etc/os-release` 的 `VERSION_CODENAME` 替换 `noble`：

```text
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble main restricted universe multiverse
# deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-updates main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-backports main restricted universe multiverse

# 安全更新保持官方源
deb http://security.ubuntu.com/ubuntu/ noble-security main restricted universe multiverse
```

`deb-src` 默认注释：只装二进制包时打开源码行会显著拖慢 `apt update`。

### 验证与回滚

```bash
sudo apt update
apt-cache policy bash | head -5
grep -RH '^\(deb\|URIs:\)' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null
```

- 只验证到 `apt update` 成功、`apt-cache policy` 显示来源为镜像；不要在验证阶段跑 `upgrade`。
- `apt update` 报 `Release file ... is not valid yet`/`Hash Sum mismatch` 时先换回备份，再排查是镜像同步滞后还是本机 DNS/代理插入。
- 回滚：把 `*.bak.*` 恢复回原文件名后 `sudo apt update`。
- 想在不动系统文件的前提下试源，可用隔离目录只读验证：

```bash
apt-get -o Dir::Etc::sourcelist=/path/to/test.sources \
        -o Dir::Etc::sourceparts=/dev/null \
        -o Dir::State::lists=/tmp/apt-lists \
        -o Dir::Cache=/tmp/apt-cache -o Debug::NoLocking=1 update
```

### 第三方软件源

镜像站也镜像了部分第三方 APT 仓库。GPG key 仍需从各自官方地址取（镜像不提供 key），把 deb822 的 `URIs` 换掉即可：

| 仓库 | 镜像 URIs | 实测 |
|---|---|---|
| docker-ce | `https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu` | `dists/noble/Release` 206 |
| Kubernetes | `https://mirrors.tuna.tsinghua.edu.cn/kubernetes/core:/stable:/v1.31/deb` | 目录 200（注意 URL 中的冒号要保留） |
| LLVM | `https://mirrors.tuna.tsinghua.edu.cn/llvm-apt/<codename>`，套件名是 `llvm-toolchain-<codename>-<N>` | `llvm-apt/noble/dists/llvm-toolchain-noble-20/Release` 200 |
| GitLab Runner | `https://mirrors.tuna.tsinghua.edu.cn/gitlab-runner/ubuntu` | `dists/` 200 |
| MySQL | `https://mirrors.tuna.tsinghua.edu.cn/mysql/apt/ubuntu` | `dists/` 200 |
| MongoDB | `https://mirrors.tuna.tsinghua.edu.cn/mongodb/apt/ubuntu` | `dists/` 200 |
| Grafana | `https://mirrors.tuna.tsinghua.edu.cn/grafana/apt` | `dists/` 200 |

`llvm-apt` 的路径结构与官方 `apt.llvm.org` 不同：镜像里 `dists/` 下的套件名是 `llvm-toolchain-<codename>-<N>`（本机实测 `noble/dists/llvm-toolchain-noble-20/Release` 可读，`noble/dists/noble/Release` 为 404），配置前先列一次 `llvm-apt/<codename>/dists/` 取实际套件名。`gitlab-ce` 的 Ubuntu 路径实测 404，不要照抄旧教程。

## conda 与 Miniforge

### 安装包来源

| 目标 | 地址 | 实测 |
|---|---|---|
| Miniforge（推荐，conda-forge 优先） | `https://mirrors-i.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease/Miniforge3-Linux-x86_64.sh` | 200，`Miniforge3-26.9.4-2`，带 `.sha256` |
| Miniconda | `https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/` | 目录 200、`Miniconda3-latest-Linux-x86_64.sh` 可下载 |
| Anaconda 历史归档 | `https://mirrors.tuna.tsinghua.edu.cn/anaconda/archive/` | 目录页对默认 User-Agent 返回 403，具体 `.sh` 文件 200；按文件名直取，不要依赖列目录 |

Miniforge 的下载、校验与安装顺序见 [`../_wsl/setup.md`](../_wsl/setup.md) 的「Miniforge 与 conda」。要点：不带版本号的文件名没有 `.sha256`，需要校验时改用带版本号的地址。

### 用户级 `.condarc`（conda-forge 单通道）

```yaml
channels:
  - conda-forge
  - nodefaults
show_channel_urls: true
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
```

### 仍需要 `defaults` 时

`defaults` 是 `default_channels` 组成的多重通道，只有改 `default_channels` 才会换源；`custom_channels` 对 `defaults` 无效：

```yaml
channels:
  - defaults
  - conda-forge
show_channel_urls: true
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  bioconda: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
```

镜像覆盖的云通道至少有 `conda-forge`、`pytorch`、`bioconda`、`msys2`（`noarch`/`linux-64` 的 `repodata.json` 实测 206）。

### 生效与验证

`custom_channels` 只按**通道名**重写地址，`-c conda-forge` 或 `.condarc` 里的 `conda-forge` 才会命中；直接写 `-c https://conda.anaconda.org/conda-forge` 会绕过重写。

```bash
conda config --show channels custom_channels default_channels
conda config --show-sources
conda clean -i                       # 只清索引缓存，不动已装环境
conda search -c conda-forge --override-channels "zlib" --info | grep -i url | head -3
```

期望 `url` 前缀是 `https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/`（本机 conda 26.10.0 实测）。写错域名时 `conda search` 会直接报 HTTP 错误，可用来做反向验证。

排障：

- `conda search` 显示的 `url` 仍是 `conda.anaconda.org`：先看是否命中了已缓存的 repodata（`$CONDA_PKGS_DIRS/cache/*.info.json` 记录了实际请求地址），必要时换一个空的 `CONDA_PKGS_DIRS` 复测；不要因为缓存命中误判配置未生效。
- 用 `CONDARC=<文件>` 做隔离验证时，文件名必须是 `condarc`、`.condarc` 或以 `.yml`/`.yaml` 结尾；`abc.condarc`、`named-condarc`、`custom.txt` 会被**静默忽略**（本机 conda 26.10.0 逐项实测）。这也是"设了 CONDARC 却没生效"最常见的原因。
- `default_channels` 的重写同样可验证：`conda search -c defaults --override-channels xz --info` 的 `url` 应变成 `https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/linux-64/...`（实测）。
- `channels` 里不写 `nodefaults` 时会隐式追加 `defaults`，出现 ToS 提示或额外拉取。
- 只清索引用 `conda clean -i`；`conda clean -a` 会删已下载包与 tarball，属于破坏性操作。
- conda 会把 root、用户级与 prefix 级 `.condarc` **合并**而不是简单覆盖（本机实测 `--show-sources` 的三个文件都被读入，`channels` 是拼接结果）。排查"配了没生效"时先看 `conda config --show-sources` 与 `conda config --show channels` 的实际合并值，再决定删哪一条。
- 旧教程里的 USTC anaconda 通道（`mirrors.ustc.edu.cn/anaconda/...`）现在会对部分路径 302 跳转到 NJU 镜像，仍可使用但多一跳；需要单一稳定入口时优先 TUNA。

## PyPI、pip 与 uv

### pip 用户级配置

```bash
mkdir -p ~/.config/pip
cp -a ~/.config/pip/pip.conf ~/.config/pip/pip.conf.bak.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
pip config list
```

等价的手写内容：

```ini
[global]
index-url = https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

- `pip config set` 写入位置由权限决定：普通用户写 `~/.config/pip/pip.conf`；`sudo pip` 会写 `/etc/pip.conf` 或 `/usr/...`，不要用 sudo 改用户配置。
- 本机实测 `pip config set` **忽略** `PIP_CONFIG_FILE`，总是写用户级文件；`PIP_CONFIG_FILE` 只在读取时生效。想写自定义路径就直接编辑该文件。
- 只对单次命令换源：`pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple <pkg>`。
- 备选：`https://mirrors.ustc.edu.cn/pypi/simple`、`https://mirrors.nju.edu.cn/pypi/web/simple`、`https://mirrors.aliyun.com/pypi/simple`、`https://mirrors.cloud.tencent.com/pypi/simple`（均实测 206）。华为云的两个域名表现不一致：`repo.huaweicloud.com/repository/pypi/simple/` 实测 429、`mirrors.huaweicloud.com/repository/pypi/simple/pip/` 200，用它作备用时先确认实际命中的是哪个域名。

### 环境变量与 CI

```bash
export PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
# 私有源并存时用附加源，注意依赖混淆风险
export PIP_EXTRA_INDEX_URL=https://pypi.org/simple
```

### uv

```bash
export UV_DEFAULT_INDEX=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

`~/.config/uv/uv.toml` 里的键名**不是** `default-index`。本机 uv 0.13.10 实测：写 `default-index` 会直接报 `unknown field 'default-index'`，合法写法是

```toml
index-url = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
```

或用 `[[index]]` 表并设 `default = true`。验证时可以加 `-v`，日志里应出现 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/six/` 这样的请求地址；把地址改成不存在的路径应报 `No solution found when resolving dependencies`。

`UV_INDEX` 用于**追加**索引（`name=url`），`UV_EXTRA_INDEX_URL` 与 pip 同名变量语义相同；索引优先级规则随版本变化，以 `uv --help` 与官方 `reference/environment` 页为准。

### 其他包管理器的单行写法（TUNA 官方模板）

```bash
pdm config pypi.url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
poetry source add --priority=primary mirrors https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/
```

poetry 的 `[[tool.poetry.source]]` 写法与其版本强相关，改完先跑一次 `poetry lock --no-update` 观察是否仍访问 `pypi.org`。

### 验证

```bash
pip config list
python -m pip download --no-deps -d /tmp/pipcheck six
```

输出首行应为 `Looking in indexes: https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`。反向验证：把地址改成不存在的路径，应立即 `No matching distribution found`，说明配置确实被读取而不是回退到官方源。本机按此流程实测通过。

## npm 与 Node.js

### registry

```bash
npm config set registry https://registry.npmmirror.com
npm config get registry
cat ~/.npmrc
```

```ini
registry=https://registry.npmmirror.com
```

- 项目级优先级高于用户级：仓库里已有 `.npmrc` 时，用户级设置会被覆盖，先 `npm config list` 看来源。
- 实测 `npm view left-pad version` 可解析，`dist.tarball` 指向 `https://registry.npmmirror.com/...`，说明包元数据与 tarball 都走了镜像。
- 备选 registry：`https://mirrors.huaweicloud.com/repository/npm`（实测 200）。`mirrors.cloud.tencent.com/npm` 已返回 404，不要再用。
- `pnpm`/`yarn` 读取同一 registry 语义：`pnpm config set registry ...`、`yarn config set npmRegistryServer ...`（yarn 2+/4 的字段名不同）。

### Node.js 二进制

nvm/fnm/n 这类版本管理器默认从 `nodejs.org` 取二进制，与 registry 无关：

```bash
export NVM_NODEJS_ORG_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/nodejs-release/
export FNM_NODE_DIST_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/nodejs-release/
```

`n` 用 `NODE_MIRROR`，`volta` 需在 `~/.volta/tools/image/node` 侧另行配置。npmmirror 也提供二进制：`https://registry.npmmirror.com/-/binary/node/`（含 `SHASUMS256.txt`，实测 206）。

安装流程与 npm 全局前缀约定见 [`../_node-js/setup.md`](../_node-js/setup.md)。

### Electron 等二进制依赖

```bash
export ELECTRON_MIRROR=https://registry.npmmirror.com/-/binary/electron/
```

同理还有 `SASS_BINARY_SITE`、`PUPPETEER_DOWNLOAD_HOST` 等；此类变量由各包自身定义，按包文档取值，不要臆造。

### 验证

```bash
npm config get registry
npm view left-pad version
npm view left-pad dist.tarball
```

反向验证：`--registry=https://registry.npmmirror.com-no-such` 应立即报 network 错误。

## Rust

### rustup 与工具链

```bash
export RUSTUP_DIST_SERVER=https://mirrors.tuna.tsinghua.edu.cn/rustup
export RUSTUP_UPDATE_ROOT=https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup
rustup install stable
```

写入 `~/.bashrc`/`~/.zshrc` 时只写 `export` 行，不要写进 `env.sh` 版本快照（快照应按机器覆盖）。

### crates.io 索引

```bash
mkdir -vp "${CARGO_HOME:-$HOME/.cargo}"
# 先备份已有的 config.toml
cat >> "${CARGO_HOME:-$HOME/.cargo}/config.toml" <<'EOF'
[source.crates-io]
replace-with = 'mirror'

[source.mirror]
registry = "sparse+https://mirrors.tuna.tsinghua.edu.cn/crates.io-index/"

[registries.mirror]
index = "sparse+https://mirrors.tuna.tsinghua.edu.cn/crates.io-index/"
EOF
```

- 只支持 sparse 协议（上面的 `sparse+` 前缀），不要再配已废弃的 git 索引地址。
- 同一文件重复追加会与已存在的 `[source.crates-io]` 冲突（`duplicate key`），追加前先用 `grep -n 'source.crates-io'` 检查。
- **索引镜像不等于包体镜像**：TUNA 的 `crates.io-index/config.json` 里 `dl` 仍指向 `https://static.crates.io/crates`，元数据走镜像、`.crate` 包体仍从官方 CDN 下载。要连包体一起换源，用 USTC（`dl` 指向自身，实测 200）或 rsproxy。
- 备选：USTC `https://mirrors.ustc.edu.cn/crates.io-index/`、rsproxy `https://rsproxy.cn/index/`；换源时索引与下载地址保持一致。

### 验证

```bash
rustup --version
rustup show
cargo search --limit 3 serde      # 观察是否访问镜像
```

TUNA 的 `dist/channel-rust-{stable,beta,nightly}.toml` 与 `rustup/rustup/dist/<target>/rustup-init` 实测可用（206），但 `dist/<target>/rustup-init` 这个旧路径已 404，说明自更新根与发行根必须分开设置。

## Go

```bash
go env -w GOPROXY=https://goproxy.cn,direct
go env -w GOSUMDB=sum.golang.google.cn
go env | grep -E 'GOPROXY|GOSUMDB'
```

- `,direct` 表示镜像未命中时回退直连；纯企业内网可改为 `,off`。
- 校验和数据库：国内可把 `GOSUMDB` 指向 `sum.golang.google.cn`（实测 200），或设 `GONOSUMDB`/`GOPRIVATE` 排除私有模块。
- 备选：`https://proxy.golang.com.cn,direct`、`https://mirrors.aliyun.com/goproxy/,direct`（阿里云这个地址本身就是代理入口，其下直接接模块路径，实测模块 zip 可取）。
- `goproxy.io` 的 `@v/list` 返回 200，但真实 zip 返回 403，不要因为列表页可用就误判。

### 验证

```bash
GOPROXY=https://goproxy.cn go mod download github.com/pkg/errors@v0.9.1
ls "$(go env GOMODCACHE)/github.com/pkg" 2>/dev/null
```

反向验证：把 `GOPROXY` 换成不存在的地址，`go mod download` 应立即失败。

## Docker

### registry 镜像加速（仅作用于 Docker Hub）

Windows Docker Desktop：Settings → Docker Engine，在 JSON 中加 `registry-mirrors`；Linux 改 `/etc/docker/daemon.json`（系统级配置，需单独确认并备份）：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
```

```bash
sudo cp -a /etc/docker/daemon.json /etc/docker/daemon.json.bak.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
sudo systemctl reload docker     # 或重启 Docker Desktop
docker info | grep -A5 'Registry Mirrors'
```

- 实测（2026-11-27，匿名 token 流程 + `library/alpine:3.20` manifest）：`docker.m.daocloud.io`、`docker.1ms.run` 需先取 Bearer token，可取到 manifest；`docker.xuanyuan.me` 直接返回 manifest。
- 公共加速器关停与限流频繁，写死三个以上的地址只会拖慢故障定位；`docker info` 显示的列表顺序即尝试顺序。
- `registry-mirrors` 只改写 Docker Hub（`docker.io`）的拉取，不影响 `ghcr.io`、`quay.io`、`nvcr.io`；这些仓库需要各自的代理或直连策略。
- 私有 registry 与镜像加速不要混在同一份配置里；`docker pull` 失败时先看 `docker info` 是否真的加载了配置。
- 拉取、导入、清理镜像的边界见 [`../_docker/setup.md`](../_docker/setup.md)。

### docker-ce 的 APT 源

```text
Types: deb
URIs: https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.gpg
```

GPG key 仍需从官方 `download.docker.com` 取（镜像站不提供 key 文件），然后用 `apt-get update` 验证 `dists/noble/Release` 可读。Debian 把路径换成 `/docker-ce/linux/debian`。

## GitHub 资产

### Release 包

```text
https://mirrors-i.tuna.tsinghua.edu.cn/github-release/<owner>/<repo>/LatestRelease/<file>
```

TUNA 的 `github-release` 是一个**只收录部分项目**的白名单镜像（实测顶层有 `conda-forge/`、`Homebrew/`、`M2Team/`、`PowerShell/`、`VSCodium/` 等）。不在列表里的仓库直接 404，不要把它当作通用 GitHub 加速。

### raw 与 clone

- `github-raw` 同样是白名单（`ros/`、`fpco/`、`opencollab/`、`docker/` 实测存在），任意仓库的 `README.md` 会 404；不要用 `/github-raw/<owner>/<repo>/<branch>/<path>` 的通用期待。
- 通用加速代理：`https://ghproxy.net/<完整 GitHub URL>`、`https://ghfast.top/<完整 GitHub URL>`。实测用 `curl -fL` 拉 raw 文件均 200 且字节数与直连一致（43268 字节）；这类代理稳定性依赖第三方，脚本中应做成可覆盖变量并在失败时回退直连。
- `gitclone.com`：`<repo>.git/info/refs` 三次探测都返回 200，但真实 `git clone --depth=1` 在 150 秒内没有任何进度（`rc=124`），同一时刻直连 GitHub 克隆同一仓库成功。结论：**不要**因为它能返回 refs 就认为可用，clone 慢时优先用代理或直连 + `--depth=1`。

```bash
url=https://github.com/owner/repo/releases/download/v1.2.3/asset.tar.gz
curl -fL --retry 3 -o /tmp/asset.tar.gz "https://ghproxy.net/$url" \
  || curl -fL --retry 3 -o /tmp/asset.tar.gz "$url"
```

### 校验

Release 资产必须校验；镜像只改动传输路径，不保证内容未被替换：

```bash
sha256sum /tmp/asset.tar.gz
```

没有官方 `SHA256SUMS` 时不要仅凭"下载成功"就安装。

## 其他生态

| 生态 | 配置 | 实测 |
|---|---|---|
| TeX Live / CTAN | `tlmgr option repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet` | `tlpkg/texlive.tlpdb`、`install-tl-unx.tar.gz` 206 |
| R / CRAN | `options(repos = c(CRAN = "https://mirrors.tuna.tsinghua.edu.cn/CRAN/"))` | `src/contrib/PACKAGES` 206 |
| RubyGems / Bundler | `gem sources --add https://mirrors.tuna.tsinghua.edu.cn/rubygems/ --remove https://rubygems.org/`；`bundle config set --global mirror.https://rubygems.org https://mirrors.tuna.tsinghua.edu.cn/rubygems` | `specs.4.8.gz`、真实 `.gem` 206 |
| Homebrew / Linuxbrew | `HOMEBREW_API_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles/api"`、`HOMEBREW_BOTTLE_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles"`；首次安装用 `git clone --depth=1 https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/install.git`；只有需要 `brew cat` 等开发命令时才设 `HOMEBREW_CORE_GIT_REMOTE` | `homebrew-bottles/api/formula.jws.json` 206、`git/homebrew/brew.git` 200 |
| Alpine | `sed -i 's#https\?://dl-cdn.alpinelinux.org/alpine#https://mirrors.tuna.tsinghua.edu.cn/alpine#g' /etc/apk/repositories` | 目录 200 |
| Arch | 改 `/etc/pacman.d/mirrorlist` 为 `https://mirrors.tuna.tsinghua.edu.cn/archlinux/$repo/os/$arch`；`archlinuxcn` 同理 | `core.db`、`archlinuxcn.db` 可读 |
| MSYS2 | 改 `/etc/pacman.d/mirrorlist.*` 的 `mirror.msys2.org` 前缀 | `msys2/mingw/mingw64/` 200 |
| Flutter / Dart | `PUB_HOSTED_URL=https://pub.flutter-io.cn`、`FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn` | pub API 与 `releases_linux.json` 206 |
| Hugging Face | `HF_ENDPOINT=https://hf-mirror.com`（`huggingface_hub`/`transformers` 读取） | `/api/models/gpt2`、`/gpt2/resolve/main/config.json` 200 |
| Julia | 二进制可用 `https://mirrors.tuna.tsinghua.edu.cn/julia-releases/`；registry/pkg server 在 TUNA 已转为 302 到 CERNET 联邦，最终实测 404 | 仅二进制项已验证 |

Julia 的 `JULIA_PKG_SERVER` / `JULIA_PKG_UPGRADE` 一类变量在镜像不再直供时不要照抄旧教程；`Pkg.Registry` 仍可直连官方，或使用仍有 registry 镜像的站点。

## 验证与回滚速查

| 生态 | 一行验证 | 回滚 | 本次是否实测 |
|---|---|---|---|
| APT | `sudo apt update` | 恢复 `*.bak.*` 后 `apt update` | 是（隔离目录 `Dir::Etc` 方式） |
| conda | `conda search -c conda-forge --override-channels zlib --info \| grep url` | 恢复 `.condarc` 备份，`conda clean -i` | 是 |
| pip | `python -m pip download --no-deps -d /tmp/x six` | `pip config unset global.index-url`（已验证）或恢复备份 | 是 |
| npm | `npm config get registry` + `npm view <pkg> dist.tarball` | `npm config delete registry`（已验证，回落到 `registry.npmjs.org`） | 是 |
| cargo | `grep -n 'source.crates-io' ~/.cargo/config.toml` | 删除对应 `[source.*]` 块 | 否（本机无 cargo，仅验证了索引 `config.json` 与包体地址） |
| Go | `go env GOPROXY` + `go mod download <mod>@<ver>` | `go env -u GOPROXY GOSUMDB` | 否（本机无 go，仅验证了代理端点返回模块 zip） |
| uv | `uv pip install -v --dry-run six` | 删除 `uv.toml` 中的 `index-url` | 是 |
| Docker | `docker info \| grep -A5 'Registry Mirrors'` | 恢复 `daemon.json` 备份并重启 | 部分（本机无 docker，仅验证 registry manifest 可取） |

每条回滚都应能独立执行；不要用"重新安装工具"代替回滚。

## 参考

- 清华大学 TUNA 镜像站帮助：<https://mirrors.tuna.tsinghua.edu.cn/>（各生态页面给出官方模板，`/help/<name>/` 可直接访问）
- TUNA GitHub Release 镜像：<https://mirrors.tuna.tsinghua.edu.cn/github-release/>
- 中科大镜像站：<https://mirrors.ustc.edu.cn/>
- 南京大学镜像站：<https://mirrors.nju.edu.cn/>
- CERNET 镜像联邦：<https://mirrors.cernet.edu.cn/list>
- npmmirror：<https://npmmirror.com/>
- Go 模块代理：<https://goproxy.cn/>
- crates.io sparse 索引说明：<https://doc.rust-lang.org/cargo/reference/registry-index.html>
- Docker 官方文档中的 registry mirror 段落（本机测试时 `docs.docker.com` 只有 IPv6 地址且不可达，未实测该链接，仅作官方出处）：<https://docs.docker.com/docker-hub/image-library/mirror/>
- 历史参考（2022 年 WSL2 + OpenMC 换源记录，其中 Ubuntu `focal` 与 USTC conda 通道已过时，USTC 的 anaconda 路径现 302 跳转到 NJU）：<https://gitlab.itp.ac.cn/ZhangXin8069/20210608-20250619/-/tree/main/_2021_/Install-OpenMC-in-Windows-wsl2-and-change-sources-for-Chinese-users>
