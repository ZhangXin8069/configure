# AGENTS.md — _mac

macOS 系统维护脚本目录（不部署到 `$HOME`）：

- `disable_mac_updates.sh` — 关闭 macOS 系统自动更新
- `restore_mac_updates.sh` — 恢复 macOS 系统自动更新
- `setup.md` — 更新策略、quarantine 清理、SSH Keychain 与操作边界

脚本会修改 `/Library/Preferences` 等系统级设置，必须由用户明确执行；`restore_mac_updates.sh` 恢复的是标准默认值，不是执行前的历史快照。
