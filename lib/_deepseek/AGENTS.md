# AGENTS.md — _deepseek

DeepSeek 在 Claude Code、Codex CLI 和桌面客户端中的配置辅助目录。

- `claude-code-deepseek-env.sh/.ps1`：Anthropic 兼容环境变量模板，含未填写的密钥占位符。
- `codex-deepseek-setup.sh/.ps1`：菜单式 Codex 配置管理器，支持切换模型和恢复安装前配置。
- `.codex/config.toml`：Codex 配置参考模板，不包含真实密钥。
- `setup.md`：两条接入路径、备份恢复、密钥和兼容性说明。

本目录脚本来自上游生成模板；修改行为前应先确认上游再重建，不要只改生成文件而丢失可复现性。
