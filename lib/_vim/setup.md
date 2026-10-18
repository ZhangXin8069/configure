# Vim 配置操作

## 文件关系

| 仓库路径 | 部署目标 | 内容 |
|---|---|---|
| `lib/_vimrc` | `~/.vimrc` | 主配置、键位、补全与 vim-plug 声明 |
| `lib/_vim/` | `~/.vim/` | `autoload`、插件 gitlink 与运行时目录；片段、覆盖层和部分主题目录不保证存在 |

## 检查插件完整性

`lib/_vim/plugged/*` 在当前索引中是 gitlink，但仓库没有 `.gitmodules` 映射。因此不能假定一次普通 clone 就包含插件，也不能用 `git submodule update` 初始化。

```bash
git ls-files -s lib/_vim/plugged | head -30
find lib/_vim/plugged -mindepth 1 -maxdepth 1 -type d -print | sort
find lib/_vim/plugged -mindepth 2 -maxdepth 3 -type f -print | head -30
```

如果目录为空，可选方案只有：

1. 在联网环境运行 `:PlugInstall`，由 vim-plug 按 `_vimrc` 中的仓库地址重新克隆。
2. 从已有的完整工作副本复制插件内容。
3. 先补齐 `.gitmodules` 映射，再初始化 submodule；这会修改仓库元数据，属于单独的仓库维护决策。

## 部署

```bash
bash bin/vim_init.sh
```

脚本会：

1. 切换到 `$HOME`。
2. 将现有 `.vimrc`、`.vim` 移动为带时间戳的 `.bak`。
3. 复制 `lib/_vimrc` 与 `lib/_vim`。

重复执行会再次备份当前版本，不做原地合并。若仓库路径包含空格，应先确认脚本的未加引号路径变量不会拆分参数。

## 插件安装和更新

仓库已声明 vim-plug。只有当当前工作副本中的插件内容已经完整时，部署才不需要联网；`plugged` gitlink 为空时，首次安装需要联网或预先准备可信插件副本：

```vim
:PlugStatus
:PlugInstall
:PlugUpdate
:PlugClean
```

`PlugInstall` 和 `PlugUpdate` 需要访问各插件 Git 远程。内网或离线机器应先通过完整工作副本、vim-plug 缓存或其他可信镜像准备插件内容。

## 自定义位置

| 需求 | 推荐位置 |
|---|---|
| 可跨机器复用的键位与插件 | `lib/_vimrc` |
| 插件、主题、片段运行时 | `lib/_vim/` |
| 单机临时修改 | `~/.vimrc`，但下次 `vim_init.sh` 会备份并覆盖 |
| 上游插件修改 | 不直接改；通过配置覆盖、维护 fork，或在补齐 `.gitmodules` 后维护 submodule 指针 |

## 验证

```bash
command -v vim
vim --version | head -5
test -r lib/_vim/autoload/plug.vim
git ls-files -s lib/_vim/plugged | head -5
vim -Nu lib/_vimrc -n -es +'qall!'
```

交互检查：

```bash
vim -Nu lib/_vimrc
```

进入后确认 `:PlugStatus` 无缺失项，并测试 `<Leader>t`、`<Leader>w` 和普通插入/退出。

## 回滚

```bash
ls -1dt ~/.vimrc.*.bak ~/.vim.*.bak 2>/dev/null
mv ~/.vimrc ~/.vimrc.failed 2>/dev/null || true
mv ~/.vim ~/.vim.failed 2>/dev/null || true
mv ~/.vimrc.<时间戳>.bak ~/.vimrc
mv ~/.vim.<时间戳>.bak ~/.vim
```

确认恢复对象后执行，不要一次删除所有历史备份。
