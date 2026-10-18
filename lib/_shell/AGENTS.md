# AGENTS.md — _shell

Shell 配置部署与个性化操作目录，不直接部署本目录。

- `setup.md`：Bash/Zsh/oh-my-zsh 部署、启动链、本机覆盖与回滚说明。
- 实际部署源仍为 `../_bashrc`、`../_zshrc`、`../_oh-my-zsh/` 与仓库根 `env.sh`。
- 修改配置后先编辑对应源文件，再运行 `bash ../../bin/sh_init.sh` 部署；不要只改 `$HOME` 下的副本。
