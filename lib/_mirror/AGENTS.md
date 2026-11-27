# AGENTS.md — _mirror

国内镜像源配置稳定入口，无脚本、不部署到 `$HOME`：

- `setup.md`：APT、conda/Miniforge、PyPI、npm/Node.js、Rust、Go、Docker、GitHub 资产与 Hugging Face 等生态的镜像地址、配置文件写法、验证命令和回滚方式。
- `AGENTS.md`：本目录契约、与其他稳定入口的边界，以及"镜像可用性必须实测"的判定规则。

## 边界

| 目录 | 职责 |
|---|---|
| `_mirror/` | 各包管理器与语言生态的**下载源选择**：镜像地址、配置文件位置、验证与回滚 |
| `_clash/` | 代理通道本身（Clash 解压、`source env.sh`、`https_proxy`）。代理能通时优先用代理，不必换源；两者不要叠加到同一工具 |
| `_wsl/` | WSL 宿主与发行版生命周期；发行版内 Miniforge 安装顺序仍以 `_wsl/setup.md` 为准，本目录只解释其中的镜像部分 |
| `_docker/` | Docker Desktop、镜像、容器与数据生命周期；registry 镜像加速只在本目录给出配置位置，拉取与清理规则仍归 `_docker/` |
| `_node-js/` | Node.js 安装、nvm 与 npm 全局前缀；`NVM_NODEJS_ORG_MIRROR` 等变量的取值来源在本目录，安装流程仍归 `_node-js/` |
| `_package/` | APT/Python 清单与随库可执行资源；本目录不改清单内容，只说明清单下载时的源 |
| `wsl-vYYYYMMDD/` | 机器版本快照。快照中已生效的源不因本目录更新而改写 |

## 判定规则

1. **先代理后换源**：能稳定走代理时优先代理；镜像站适合代理不可用、代理只覆盖部分域名或需要长期无人值守抓取的场景。
2. **镜像可用性必须实测**：镜像站的下游目录、上游策略和限流会变化。文档中的每个地址都在 `setup.md` 标注了实测日期与实测到的最小可验证路径；未实测的项必须标明。
3. **校验优先于速度**：优先选择提供 `.sha256`/`SHA256SUMS` 的下载路径；`github-release` 镜像只有带版本号的文件名才有校验文件。
4. **系统级配置需确认**：写入 `/etc/apt/sources.list*`、`/etc/docker/daemon.json`、`/etc/pip.conf` 等系统级路径属于系统配置变更，`setup.md` 只给步骤，执行由用户单独确认。
5. **不写凭据**：镜像 URL 不含 userinfo；私有源凭据只从 Git 外的环境变量或本地覆盖文件读取。
6. **回滚成对出现**：每个改写源的步骤都要有对应的回滚命令或备份路径，备份文件带时间戳，不覆盖原文件。

## 破坏性操作确认

以下操作会覆盖现有软件源配置或影响全机包管理行为，agent 不得自动执行：

- 覆盖 `/etc/apt/sources.list`、`/etc/apt/sources.list.d/*.sources` 或 `*.list`。
- 覆盖 `/etc/pip.conf`、`/etc/docker/daemon.json`、`~/.condarc` 等已有配置文件。
- 执行 `pip config set`/`npm config set --global`/`conda config --add channels` 等写盘命令。
- 在 `daemon.json` 中加入或更换 `registry-mirrors` 后重启 Docker。

## 交叉引用

- 代理通道：[`../_clash/setup.md`](../_clash/setup.md)
- WSL 内 Miniforge 与 conda 顺序：[`../_wsl/setup.md`](../_wsl/setup.md)
- Docker 与容器：[`../_docker/setup.md`](../_docker/setup.md)
- Node.js 与 npm 前缀：[`../_node-js/setup.md`](../_node-js/setup.md)
- APT/Python 包清单：[`../_package/setup.md`](../_package/setup.md)
- Linux 系统级操作分层：[`../_linux/setup.md`](../_linux/setup.md)
