# AGENTS.md — _vim

Vim 运行时目录，由 `bin/vim_init.sh` 部署到 `~/.vim/`（先备份旧 `~/.vimrc`/`~/.vim`）。

## 目录说明

| 子目录 | 说明 |
|---|---|
| `plugged/` | 第三方插件 gitlink（auto-pairs、gruvbox、vim-airline、vim-fugitive、nerdtree 等）；当前缺少 `.gitmodules` 映射，目录可能为空。修改请勿直接改源码 |
| `autoload/` | vim-plug 自动加载 |
| `undodir/` | 持久撤销占位目录；其他备份、交换、拼写目录可能由运行时或插件按需创建 |

`colors/`、`UltiSnips/`、`after/`、`backup/`、`swap/`、`spell/` 当前不保证全部存在。部署前应检查实际内容，不能假定完整片段或覆盖层已经入库。

## 约定

- 修改插件配置应在 `bin/vim_init.sh` 或用户 `~/.vimrc` 中做，插件本体视为第三方依赖
- 校验：`bash -n` 不适用于 vim 脚本；以 `vim_init.sh` 的部署流程为准
- `plugged/*` 以 gitlink 记录，但当前仓库没有对应 `.gitmodules` 映射；`git submodule update` 无法初始化这些目录
- `setup.md` 记录部署、插件初始化、离线边界、验证和回滚
