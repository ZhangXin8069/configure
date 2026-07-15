#!/usr/bin/env bash
# Vim 终端配置脚本
# 功能: 备份 ~/.vimrc 和 ~/.vim, 部署新版配置 (从 lib/_vimrc + lib/_vim 复制)
# 补全: vim 内置 ins-completion (Tab), 无需 Node.js / CoC / fzf
# 插件: vim-plug 管理, 预装于 lib/_vim/ 无需联网
# 图标: 纯 ASCII 符号, 兼容所有终端
# 主题: solarized dark + vim-airline

_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
pushd ~
mv ./.vimrc .vimrc."$(date "+%Y-%m-%d-%H-%M-%S")".bak 2>/dev/null
mv ./.vim .vim."$(date "+%Y-%m-%d-%H-%M-%S")".bak 2>/dev/null
cp -r ${_PATH}/../lib/_vimrc .vimrc
cp -r ${_PATH}/../lib/_vim .vim
popd

cat << 'USAGE'

  ┌──────────────────────────────────────────────────────────────┐
  │                    Vim 终端配置 — 使用说明                   │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  基础操作 (Leader = 空格)                                    │
  │    <Leader>w     保存文件                                    │
  │    <Leader>q     强制退出                                    │
  │    <Leader>s     重新加载 .vimrc                             │
  │    <Leader>h     清除搜索高亮                                │
  │    <Leader>l     切换不可见字符显示                          │
  │                                                              │
  │  编辑                                                        │
  │    jk / kj       退出插入模式 (代替 Esc)                     │
  │    gc            注释/取消注释 (vim-commentary)              │
  │    ga            对齐 (vim-easy-align)                       │
  │    <C-n>         多光标选中下一个 (vim-visual-multi)         │
  │    <A-j>/<A-k>   整行上下移动                                │
  │    < / >         缩进 (visual 模式保持选择)                  │
  │                                                              │
  │  分屏窗口                                                    │
  │    :sp [file]     水平分屏 (split), 可选打开指定文件         │
  │    :vs [file]     垂直分屏 (vsplit), 可选打开指定文件        │
  │    <C-h/j/k/l>    在分屏窗口间移动 (左/下/上/右)             │
  │    <C-w> + / -    增大/减小当前窗口高度                      │
  │    <C-w> > / <    增大/减小当前窗口宽度                      │
  │    <C-w> =        均分所有窗口尺寸                           │
  │    <C-w> q        关闭当前窗口 (:q 只关当前分屏)             │
  │    <Leader>q      强制关闭当前窗口                           │
  │                                                              │
  │  文件浏览 & Buffer                                           │
  │    <Leader>t      左侧打开/关闭 NERDTree 文件浏览器          │
  │    <Leader>e      在 NERDTree 中定位当前文件                 │
  │    <Leader>bn/bp  切换上一个/下一个 buffer                   │
  │    <Leader>bd     删除当前 buffer                            │
  │    <Leader>bl     列出所有 buffer                            │
  │                                                              │
  │  运行代码                                                    │
  │    <Leader>r     运行当前文件 (Python / Shell / C / C++)     │
  │                                                              │
  │  补全                                                        │
  │    Tab           关键字补全 / 弹出菜单中向前选择             │
  │    S-Tab         弹出菜单中向后选择                          │
  │    C-Space       omni 补全 (文件类型感知)                    │
  │    C-n / C-p     通用关键字补全                              │
  │    C-x C-f       文件路径补全                                │
  │    C-x C-l       整行补全                                    │
  │                                                              │
  │  插件                                                        │
  │    solarized, vim-airline, rainbow, nerdtree, vim-startify     │
  │    vim-commentary, vim-surround, vim-visual-multi            │
  │    auto-pairs, vim-repeat, vim-unimpaired, vim-easy-align    │
  │    vim-fugitive, vim-gitgutter, gv.vim, tabular              │
  │    vim-tmux-navigator, vim-tmux-focus-events (tmux 环境)     │
  │                                                              │
  │  手动更新插件: 打开 vim 后执行 :PlugInstall 或 :PlugUpdate   │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
USAGE

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
