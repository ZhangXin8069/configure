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

## 验证

```bash
bash -n lib/_mac/disable_mac_updates.sh
bash -n lib/_mac/restore_mac_updates.sh
bash -n bin/xxattr.sh
softwareupdate --schedule
```

系统维护脚本只能在 macOS 上验证。Linux 环境可做语法检查，但不要执行。
