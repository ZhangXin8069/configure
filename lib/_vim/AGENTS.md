# AGENTS.md — _vim

Vim 运行时目录，由 `bin/vim_init.sh` 部署到 `~/.vim/`（先备份旧 `~/.vimrc`/`~/.vim`）。

## 目录说明

| 子目录 | 说明 |
|---|---|
| `plugged/` | 第三方插件（auto-pairs、gruvbox、vim-airline、vim-fugitive、nerdtree 等，各含独立 `.git`）。修改请勿直接改源码；新增插件后需重新部署 |
| `autoload/`、`colors/` | vim-plug 自动加载与配色方案 |
| `UltiSnips/` | UltiSnips 代码片段 |
| `after/` | ftplugin 覆盖 |
| `backup/`、`swap/`、`undodir/`、`spell/` | 运行时状态目录（备份/交换/撤销历史/拼写），不入库 |

## 约定

- 修改插件配置应在 `bin/vim_init.sh` 或用户 `~/.vimrc` 中做，插件本体视为第三方依赖
- 校验：`bash -n` 不适用于 vim 脚本；以 `vim_init.sh` 的部署流程为准
