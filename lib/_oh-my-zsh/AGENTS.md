# AGENTS.md — _oh-my-zsh

完整 oh-my-zsh 安装（第三方），由 `bin/sh_init.sh` 部署到 `~/.oh-my-zsh/`（先备份旧 `~/.oh-my-zsh`）。

## 目录说明

- `custom/` — 用户自定义：`plugins/`（you-should-use、zsh-autosuggestions、zsh-syntax-highlighting、zsh-vi-mode）、`themes/`、`example.zsh`
- `plugins/`、`lib/`、`tools/`、`templates/`、`themes/` — oh-my-zsh 官方内容（第三方，勿修改）
- `cache/`、`log/` — 运行时状态，不入库

## 约定

- 官方部分视为第三方依赖，改动只在 `custom/` 或 `lib/_zshrc`（配置加载顺序）中进行
- 部署后需要新 shell 生效
