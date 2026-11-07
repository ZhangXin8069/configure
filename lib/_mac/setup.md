# macOS 配置操作

## 系统更新策略

| 脚本 | 行为 | 风险 |
|---|---|---|
| `disable_mac_updates.sh` | 关闭自动检查、下载、大版本升级和自动重启，保留安全更新 | 删除 `/Library/Updates/*` 下已下载内容 |
| `restore_mac_updates.sh` | 启用自动检查、下载、升级和重启，保留安全更新 | 恢复标准默认值，不保证还原原机器设置 |

两个脚本都要求 root：

```bash
sudo bash lib/_mac/disable_mac_updates.sh
sudo bash lib/_mac/restore_mac_updates.sh
```

执行前记录当前状态：

```bash
softwareupdate --schedule
for key in AutomaticCheckEnabled AutomaticDownload AutomaticallyInstallMacOSUpdates \
  RestartRequired CriticalUpdateInstall ConfigDataInstall; do
  printf '%-40s ' "$key"
  defaults read /Library/Preferences/com.apple.SoftwareUpdate "$key" 2>/dev/null || echo '(not set)'
done
```

`disable_mac_updates.sh` 会删除 `/Library/Updates/*`，这是不可逆的本地缓存清理。若设备上有待安装更新或受限网络环境，应先确认这一行为。

恢复脚本不会读取上面的输出并逐项回填。它写入一组常用默认值：

```text
AutomaticCheckEnabled=true
AutomaticDownload=true
AutomaticallyInstallMacOSUpdates=true
RestartRequired=true
CriticalUpdateInstall=true
ConfigDataInstall=true
```

需要精确恢复原状态时，应根据执行前记录手工执行 `defaults write`。

## Gatekeeper quarantine

`bin/xxattr.sh` 递归移除用户目录或指定目录的 `com.apple.quarantine` 属性：

```bash
bash bin/xxattr.sh ~/Downloads/trusted-tool
```

不带参数时会对 Desktop、Documents、Downloads、Pictures、Music、Movies、Draft、Favorites 递归执行。

该脚本降低 Gatekeeper 对下载内容的隔离保护，只应对已确认来源和完整性的文件使用。不要为省事对所有下载目录无条件执行。

## SSH Keychain

macOS 推荐把 SSH key 加入 Keychain：

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
ssh-add -l
```

完整 SSH 操作见 [`../_ssh/setup.md`](../_ssh/setup.md)。

## Homebrew 与工具路径

Apple Silicon 的 Homebrew 默认前缀通常为 `/opt/homebrew`，Intel 通常为 `/usr/local`。本仓库不会自动安装 Homebrew。检查：

```bash
command -v brew || true
brew --prefix 2>/dev/null || true
uname -m
```

版本化 `lib/mac-v*/env.sh` 包含某台机器当时使用的 Homebrew、conda 和本地工具路径，不应直接假定所有 macOS 都相同。

## 环境快照参考

`mac-v*` 快照的共同模式（arm64）：

| 项 | 典型值 |
|---|---|
| Conda | `Miniconda3-py311_25.9.1-3-MacOSX-arm64.sh`，环境 `qcu`（Python 3.11 + cmake/autoconf/automake/libtool/wget） |
| 本地工具 | `watch`、`tree`、`htop`、`btop` 编译到 `~/lib/<tool>` 后加入 `PATH` |
| TeX | `/Library/TeX/texbin` 加入 `PATH` |
| Homebrew | `HOMEBREW_NO_AUTO_UPDATE=1` |
| Python | `KMP_DUPLICATE_LIB_OK=TRUE`，`PYTHONPATH=~/PyQCU` |
| 覆盖 | `@ENV@` 按存在性加载 `~/env-key.sh`；`v20260814` 另加 `~/.opencode/bin` |

复用边界：

- 快照中的 `/Users/zhangxin` 是示例用户路径，其他用户必须替换为 `$HOME`。
- `KMP_DUPLICATE_LIB_OK=TRUE` 只是绕过 OpenMP 运行库重复加载的报错，不是修复；出现崩溃时应定位重复的 `libomp`/`libiomp`。
- 本机编译的 `watch`/`tree`/`htop`/`btop` 没有包管理器升级路径，升级时重新编译并保留旧二进制。
- Apple Silicon 与 Intel 的 Homebrew 前缀不同（`/opt/homebrew` vs `/usr/local`），不要把 Intel 路径带过去。
- `mac-v20260908` 把 `env-key.sh` 加载改为 `[ -r ... ]` 判断，避免文件缺失时中断；新快照沿用该写法。
- 新增快照按 `mac-vYYYYMMDD` 新建；稳定入口只保留跨机器可复用的路径和变量模式。

## 验证

```bash
bash -n lib/_mac/disable_mac_updates.sh
bash -n lib/_mac/restore_mac_updates.sh
bash -n bin/xxattr.sh
softwareupdate --schedule
```

系统维护脚本只能在 macOS 上验证。Linux 环境可做语法检查，但不要执行。
