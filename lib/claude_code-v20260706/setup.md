# Claude Code & cc-switch 离线安装包

本目录存放 **Claude Code**、**cc-switch-cli**、**cc-switch** 的离线安装包及各版本历史版本，用于无外网环境下的部署与版本回退。

## 目录结构

```
claude_code-v20260706/
│
├── setup.md                    # 本文档
├── download_all.sh             # 批量下载脚本（幂等）
│
├── claude-code/                # Claude Code 二进制 (~261 MB/版)
│   ├── latest.txt
│   └── <version>/
│       ├── claude              #   linux-x64 可执行文件
│       └── manifest.json       #   checksum / 平台信息
│
├── cc-switch-cli/              # cc-switch 命令行工具 (~7 MB/版)
│   ├── latest.json
│   └── <version>/
│       ├── cc-switch-cli-linux-x64-musl.tar.gz
│       └── install.sh
│
└── cc-switch/                  # cc-switch GUI (~110 MB/版)
    ├── latest.json
    └── <version>/
        ├── CC-Switch-<ver>-Linux-x86_64.AppImage
        ├── CC-Switch-<ver>-Linux-x86_64.AppImage.sig
        ├── CC-Switch-<ver>-Linux-x86_64.deb
        ├── CC-Switch-<ver>-Linux-x86_64.rpm
        └── latest.json
```

## 版本覆盖

| 组件 | 版本数 | 范围 | 大小 | 上游来源 |
|------|--------|------|------|----------|
| Claude Code | 25 | 2.1.210 → 1.0.50 | 5.5 GB | Google Cloud Storage |
| cc-switch-cli | 57 | v5.9.0 → v4.0.0 | 182 MB | GitHub [`SaladDay/cc-switch-cli`] |
| cc-switch | 19* | v3.17.0 → v3.6.1 | 1.7 GB | GitHub [`farion1231/cc-switch`] |

> \* cc-switch 共 46 个 release，其中 27 个的 linux-x86_64 资产因 GitHub 网络中断尚未下载。运行 `./download_all.sh --cc-switch` 可续传补全。

## 下载

`download_all.sh` 幂等运行——已存在且非空的文件自动跳过。

```bash
./download_all.sh                  # 下载全部
./download_all.sh --claude-code    # 仅 Claude Code
./download_all.sh --cc-switch-cli  # 仅 cc-switch-cli
./download_all.sh --cc-switch      # 仅 cc-switch
```

数据源：

| 组件 | 源地址 |
|------|--------|
| Claude Code | `http://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases` |
| cc-switch-cli | `https://github.com/SaladDay/cc-switch-cli/releases` |
| cc-switch | `https://github.com/farion1231/cc-switch/releases` |

前置依赖: `curl`, `bash`, `python3`。

> **为什么 Claude Code 用 HTTP？** GCS 存储桶在此环境存在 SSL 握手兼容性问题，HTTPS 连接会报 `error:0A000126:SSL routines::unexpected eof while reading`。建议下载后通过 `manifest.json` 中的 SHA-256 校验完整性。

## 离线安装

### 安装约定

| 路径 | 用途 |
|------|------|
| `~/.local/bin/claude` | Claude Code 主程序（软链接） |
| `~/.local/share/claude/versions/` | Claude Code 版本文件 |
| `~/.local/bin/cc-switch` | cc-switch 命令行工具 |
| `~/.claude.json` | Claude Code 配置 |
| `~/.claude/` | Claude Code 数据 / 缓存 / 锁文件 |

安装前确保 `~/.local/bin` 在 `PATH` 中：

```bash
export PATH="$HOME/.local/bin:$PATH"
# 持久化:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # 或 ~/.zshrc
```

### 安装 Claude Code

```bash
VERSION=2.1.210

# 安装二进制
cp claude-code/$VERSION/claude ~/.local/bin/claude-$VERSION
chmod +x ~/.local/bin/claude-$VERSION
ln -sf ~/.local/bin/claude-$VERSION ~/.local/bin/claude

# 禁用自动更新（离线环境必要）
mkdir -p ~/.claude
cat > ~/.claude.json << 'EOF'
{
  "installMethod": "native",
  "autoUpdates": false,
  "autoUpdatesProtectedForNative": true
}
EOF
```

### 安装 cc-switch-cli

```bash
VERSION=v5.9.0
cd cc-switch-cli/$VERSION
tar xzf cc-switch-cli-linux-x64-musl.tar.gz
cp cc-switch ~/.local/bin/
chmod 755 ~/.local/bin/cc-switch
```

### 安装 cc-switch GUI

```bash
VERSION=v3.17.0
# AppImage（免安装，直接运行）
chmod +x cc-switch/$VERSION/CC-Switch-*-Linux-x86_64.AppImage
./cc-switch/$VERSION/CC-Switch-*-Linux-x86_64.AppImage

# deb 安装
sudo dpkg -i cc-switch/$VERSION/CC-Switch-*-Linux-x86_64.deb

# rpm 安装
sudo rpm -i cc-switch/$VERSION/CC-Switch-*-Linux-x86_64.rpm
```

## 卸载

卸载脚本对应安装脚本的布局，默认删除二进制、版本目录、状态/缓存及 shell 配置中的 PATH 行，**保留用户数据**（`~/.claude.json`、`~/.claude`，含登录凭据与设置）；加 `--purge` / `-purge` 后连同用户数据一并删除。

| 脚本 | 平台 | 常用参数 |
|------|------|----------|
| `uninstall_cc-v20260812.sh` | Linux / macOS | `-y` 跳过确认，`--npm` 一并卸载 npm 版，`--dry-run` 预览 |
| `uninstall_cc-v20260812.bat` | Windows (cmd) | `-y`，`-npm`，`-dry-run` |

```bash
# Linux / macOS
./uninstall_cc-v20260812.sh           # 标准卸载（保留用户数据）
./uninstall_cc-v20260812.sh --purge   # 连同 ~/.claude.json、~/.claude 一起删除
./uninstall_cc-v20260812.sh --dry-run # 先预览将删除的内容
./uninstall_cc-v20260812.sh --npm     # 同时卸载 npm 安装的 @anthropic-ai/claude-code
```

```bat
rem Windows (cmd，可直接双击或命令行运行)
uninstall_cc-v20260812.bat            rem 标准卸载（保留用户数据）
uninstall_cc-v20260812.bat -purge -y  rem 连同 .claude.json、.claude 一起删除
uninstall_cc-v20260812.bat -npm       rem 同时卸载 npm 安装的 @anthropic-ai/claude-code
```

> 若 Claude Code 通过官方 npm 安装（`npm i -g @anthropic-ai/claude-code`），脚本会检测并提示，加 `--npm` / `-npm` 自动卸载；npm 安装位置不受默认（非 purge）路径清理影响，需要手动确认。

## 版本切换

使用 `cc-switch` 命令行工具管理 Claude Code 多版本：

```bash
cc-switch list              # 列出已安装/可用版本
cc-switch use 2.1.210       # 切换到指定版本
cc-switch --version         # 查看当前版本
```

## 参考链接

- [Claude Code 安装教程](https://daheiai.com/cc-install.html)
- [cc-switch 项目](https://github.com/farion1231/cc-switch)
- [cc-switch-cli 项目](https://github.com/saladday/cc-switch-cli)


[`SaladDay/cc-switch-cli`]: https://github.com/SaladDay/cc-switch-cli
[`farion1231/cc-switch`]: https://github.com/farion1231/cc-switch
