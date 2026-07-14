#!/usr/bin/env bash
# ==============================================================================
# Vim 终端配置脚本 — 零外部依赖版
# ==============================================================================
# 功能:
#   1. 部署优化的 .vimrc（从 lib/_vimrc 模板）
#   2. 安装 vim-plug 插件管理器
#   3. 自动安装所有插件（纯 vimscript，无需外部运行时）
#   4. 备份旧配置
#   5. 创建必要的目录结构
#   6. 终端环境检测 & Nerd Font 智能适配
#
# 补全: 使用 vim 内置 ins-completion (Tab 触发)，无需 Node.js / CoC / fzf
#
# 用法:
#   vim_init.sh          (通过 alias 调用)
#   bash bin/vim_init.sh (直接调用)
#
# ==============================================================================

set -euo pipefail

# -------------------------------------------------------------------
# 0. 全局变量与环境检测
# -------------------------------------------------------------------
_PATH=$(cd "$(dirname "$0")" && pwd)
_NAME=$(basename "$0")
_TIMESTAMP=$(date "+%Y-%m-%d-%H-%M-%S")

echo "###${_NAME} in ${_PATH} is running...:${_TIMESTAMP}###"

# 颜色输出
_RED='\033[0;31m'
_GRN='\033[0;32m'
_YLW='\033[0;33m'
_BLU='\033[0;34m'
_CYN='\033[0;36m'
_BLD='\033[1m'
_NC='\033[0m'

# --- 操作系统检测 ---
_IS_WSL=false
_IS_DOCKER=false
_IS_MAC=false
_IS_LINUX=false

if [[ -f /proc/version ]] && grep -qi microsoft /proc/version 2>/dev/null; then
    _IS_WSL=true
fi
if [[ -f /.dockerenv ]] || grep -qi docker /proc/1/cgroup 2>/dev/null; then
    _IS_DOCKER=true
fi
if [[ "$(uname -s)" == "Darwin" ]]; then
    _IS_MAC=true
fi
if [[ "$(uname -s)" == "Linux" ]]; then
    _IS_LINUX=true
fi

# --- 终端模拟器检测 ---
_TERM_EMULATOR="unknown"
_TERM_SUPPORTS_NERD_FONT=false

detect_terminal() {
    # 检查已知支持 Nerd Font 的环境变量
    if [[ -n "${WT_SESSION:-}" ]]; then
        _TERM_EMULATOR="Windows Terminal"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ "$TERM_PROGRAM" == "vscode" ]]; then
        _TERM_EMULATOR="VS Code Integrated Terminal"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ "$TERM_PROGRAM" == "iTerm.app" ]]; then
        _TERM_EMULATOR="iTerm2"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ "$TERM_PROGRAM" == "WarpTerminal" ]]; then
        _TERM_EMULATOR="Warp"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ "$TERM_PROGRAM" == "WezTerm" ]]; then
        _TERM_EMULATOR="WezTerm"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ "$TERM" == "xterm-kitty" ]]; then
        _TERM_EMULATOR="Kitty"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ -n "${ALACRITTY_LOG:-}" ]] || [[ "$TERM" == "alacritty" ]]; then
        _TERM_EMULATOR="Alacritty"
        _TERM_SUPPORTS_NERD_FONT=true
    elif [[ -n "${GNOME_TERMINAL_SERVICE:-}" ]]; then
        _TERM_EMULATOR="GNOME Terminal"
    elif [[ -n "${KONSOLE_VERSION:-}" ]]; then
        _TERM_EMULATOR="Konsole"
    elif [[ "$TERM" == "xterm"* ]] || [[ "$TERM" == "screen"* ]]; then
        _TERM_EMULATOR="xterm/screen (SSH 或基础终端)"
    elif [[ -n "${SSH_TTY:-}" ]] || [[ -n "${SSH_CONNECTION:-}" ]]; then
        _TERM_EMULATOR="SSH 远程会话"
    elif [[ -n "${TMUX:-}" ]]; then
        _TERM_EMULATOR="tmux"
    fi
}

detect_terminal

# --- Nerd Font 检测 ---
# 检查显式标记: 环境变量 $VIM_NERD_FONT 或标记文件 ~/.vim/nerd-font-enabled
_HAS_NERD_FONT=false
check_nerd_font() {
    # 仅通过显式标记启用 Nerd Font (避免在未安装字体的终端上出现乱码)
    if [[ -n "${VIM_NERD_FONT:-}" ]]; then
        _HAS_NERD_FONT=true
        return
    fi
    if [[ -f "${HOME}/.vim/nerd-font-enabled" ]]; then
        _HAS_NERD_FONT=true
        return
    fi
    # 不自动检测 — 终端支持 Nerd Font != 用户已安装 Nerd Font
    # 用户需手动创建标记文件或设置环境变量来启用
}
check_nerd_font

# -------------------------------------------------------------------
# 辅助函数
# -------------------------------------------------------------------
log_info()  { echo -e "${_BLU}[INFO]${_NC}  $(date '+%H:%M:%S') $*"; }
log_ok()    { echo -e "${_GRN}[OK]${_NC}    $(date '+%H:%M:%S') $*"; }
log_warn()  { echo -e "${_YLW}[WARN]${_NC}  $(date '+%H:%M:%S') $*"; }
log_err()   { echo -e "${_RED}[ERR]${_NC}   $(date '+%H:%M:%S') $*"; }
log_step()  { echo -e "\n${_CYN}${_BLD}==>${_NC} ${_BLD}$*${_NC}"; }
log_title() { echo -e "\n${_BLD}━━━ $* ━━━${_NC}"; }

has_cmd() { command -v "$1" &>/dev/null; }

# -------------------------------------------------------------------
# 欢迎信息
# -------------------------------------------------------------------
log_title "Vim 终端配置脚本 (零外部依赖)"
echo "  执行时间 : ${_TIMESTAMP}"
echo "  脚本路径 : ${_PATH}/${_NAME}"
echo "  运行环境 : $(uname -a | cut -d' ' -f1-3)"
echo "  终端模拟器: ${_TERM_EMULATOR}"
if $_IS_WSL;     then echo "  检测到   : WSL2 (Windows Subsystem for Linux)"; fi
if $_IS_DOCKER;  then echo "  检测到   : Docker 容器"; fi
if $_IS_MAC;     then echo "  检测到   : macOS"; fi
echo ""
echo "  补全方案 : vim 内置 ins-completion (Tab 触发)"
echo "  依赖     : 无 (不需要 Node.js / CoC / fzf / ripgrep)"
echo ""

# -------------------------------------------------------------------
# 1. 检查 vim
# -------------------------------------------------------------------
log_step "1/6 检查 vim"

if ! has_cmd vim; then
    log_err "vim 未安装！请先安装 vim (apt install vim / brew install vim / ...)"
    exit 1
fi
log_info "vim: $(vim --version 2>/dev/null | head -1)"
log_ok "vim 就绪"

# -------------------------------------------------------------------
# 2. 创建 vim 目录结构
# -------------------------------------------------------------------
log_step "2/6 创建 vim 目录结构"

_VIM_DIR="${HOME}/.vim"
mkdir -p "${_VIM_DIR}/autoload"
mkdir -p "${_VIM_DIR}/plugged"
mkdir -p "${_VIM_DIR}/undodir"
mkdir -p "${_VIM_DIR}/backup"
mkdir -p "${_VIM_DIR}/swap"
mkdir -p "${_VIM_DIR}/spell"
mkdir -p "${_VIM_DIR}/after/ftplugin"
mkdir -p "${_VIM_DIR}/colors"
mkdir -p "${_VIM_DIR}/UltiSnips"

log_ok "目录结构创建完毕"

# -------------------------------------------------------------------
# 3. Nerd Font 检测与配置
# -------------------------------------------------------------------
log_step "3/6 Nerd Font 检测"

if $_HAS_NERD_FONT; then
    log_ok "Nerd Font 支持: 已启用 (终端: ${_TERM_EMULATOR})"
    # 创建标记文件，供 vim 和后续运行检测
    touch "${_VIM_DIR}/nerd-font-enabled"
else
    log_warn "Nerd Font 支持: 未启用 — 图标功能已禁用，使用 ASCII 回退方案"
    echo ""
    echo -e "  ${_YLW}图标 (vim-devicons) 需要安装 Nerd Font 字体并在终端中选择该字体。${_NC}"
    echo ""
    echo "  ${_BLD}启用方法:${_NC}"
    echo "  ┌─────────────────────────────────────────────────────────────┐"
    echo "  │ 1. 安装 Nerd Font:                                         │"
    echo "  │    https://www.nerdfonts.com/font-downloads                │"
    echo "  │    推荐: JetBrainsMono Nerd Font, FiraCode Nerd Font       │"
    echo "  │                                                             │"
    echo "  │ 2. 在终端设置中选择该字体:                                   │"
    echo "  │    Windows Terminal: 设置 → 配置文件 → 外观 → 字体          │"
    echo "  │    VS Code: settings.json → terminal.integrated.fontFamily  │"
    echo "  │    iTerm2: Preferences → Profiles → Text → Font            │"
    echo "  │    GNOME Terminal: Preferences → 自定义字体                 │"
    echo "  │                                                             │"
    echo "  │ 3. 重新运行本脚本: vim_init.sh                               │"
    echo "  │    或手动启用: touch ~/.vim/nerd-font-enabled               │"
    echo "  └─────────────────────────────────────────────────────────────┘"
    echo ""
    # 确保标记文件不存在 (禁用状态)
    rm -f "${_VIM_DIR}/nerd-font-enabled"
fi

# -------------------------------------------------------------------
# 4. 安装 vim-plug 插件管理器
# -------------------------------------------------------------------
log_step "4/6 安装 vim-plug"

_PLUG_URL="https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
_PLUG_PATH="${_VIM_DIR}/autoload/plug.vim"

if [[ -f "$_PLUG_PATH" ]]; then
    log_info "vim-plug 已安装: ${_PLUG_PATH}"
else
    log_info "下载 vim-plug..."
    if ! curl -fLo "$_PLUG_PATH" --create-dirs "$_PLUG_URL"; then
        log_err "下载 vim-plug 失败，请检查网络连接"
        exit 1
    fi
    log_ok "vim-plug 安装完毕"
fi

# -------------------------------------------------------------------
# 5. 部署 vimrc (基础配置)
# -------------------------------------------------------------------
log_step "5/6 部署 .vimrc (基础配置)"

_VIMRC_SRC="${_PATH}/../lib/_vimrc"
_VIMRC_DST="${HOME}/.vimrc"

if [[ ! -f "$_VIMRC_SRC" ]]; then
    log_err "源文件 ${_VIMRC_SRC} 不存在!"
    exit 1
fi

# 备份现有 .vimrc
if [[ -f "$_VIMRC_DST" ]]; then
    if ! diff "$_VIMRC_SRC" "$_VIMRC_DST" &>/dev/null; then
        cp "$_VIMRC_DST" "${_VIMRC_DST}.${_TIMESTAMP}.bak"
        log_info "已备份旧 .vimrc → ${_VIMRC_DST}.${_TIMESTAMP}.bak"
    else
        log_info ".vimrc 已是最新，跳过部署"
    fi
fi

cp "$_VIMRC_SRC" "$_VIMRC_DST"
log_ok ".vimrc 基础配置部署完毕 → ${_VIMRC_DST}"

# -------------------------------------------------------------------
# 6. 插件配置块 (自动适配 Nerd Font)
# -------------------------------------------------------------------
log_step "6/6 插件配置"

# 清理旧版插件块 (v1 无版本标记 或 v2+ 有 BEGIN/END 标记)
_OLD_BLOCK=false
if grep -q "vim-plug 插件管理器" "$_VIMRC_DST" 2>/dev/null; then
    _OLD_BLOCK=true

    # 尝试用 END 标记删除 (v2+ 格式)，失败则用起始标记到文件末尾范围删除 (v1 格式)
    if grep -q '^" ===== vim-plug 插件管理器 v[0-9]\+ END =====' "$_VIMRC_DST" 2>/dev/null; then
        sed -i '/^" ===== vim-plug 插件管理器 v[0-9]\+ BEGIN =====/,/^" ===== vim-plug 插件管理器 v[0-9]\+ END =====/d' "$_VIMRC_DST"
    else
        # v1 格式: 从标记行删到文件末尾 (v1 没有 END 标记)
        sed -i '/^" ===== vim-plug 插件管理器/,$d' "$_VIMRC_DST"
    fi
    # 清理末尾空行
    sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$_VIMRC_DST" 2>/dev/null || true

    log_info "已清理旧版插件配置"
fi

log_info "写入插件配置块 (Nerd Font: $($_HAS_NERD_FONT && echo '已启用' || echo '已禁用'))..."

cat >> "$_VIMRC_DST" << 'PLUGEOF'

" ===== vim-plug 插件管理器 v3 BEGIN =====
" Nerd Font 检测 — 满足任一条件即启用图标:
"   1. 环境变量 $VIM_NERD_FONT 非空
"   2. 标记文件 ~/.vim/nerd-font-enabled 存在
"   启用方法: touch ~/.vim/nerd-font-enabled  或  export VIM_NERD_FONT=1
let s:has_nerd_font = 0
if !empty($VIM_NERD_FONT) || filereadable(expand('~/.vim/nerd-font-enabled'))
    let s:has_nerd_font = 1
endif
" 输出检测结果 (启动时 :message 可见)
if s:has_nerd_font
    let g:nerd_font_enabled = 1
else
    let g:nerd_font_enabled = 0
endif

call plug#begin('~/.vim/plugged')

" --- 外观 ---
Plug 'morhetz/gruvbox'                     " 复古暖色主题 (终端友好)
Plug 'vim-airline/vim-airline'             " 状态栏增强
Plug 'vim-airline/vim-airline-themes'      " 状态栏主题
if s:has_nerd_font
    Plug 'ryanoasis/vim-devicons'          " 文件图标 (需要 Nerd Font)
endif
Plug 'luochen1990/rainbow'                 " 彩虹括号

" --- 导航 ---
Plug 'preservim/nerdtree'                  " 侧边栏文件浏览器 (:NERDTreeToggle)
Plug 'mhinz/vim-startify'                  " 启动界面: 最近文件 / 书签 / session

" --- 编辑增强 ---
Plug 'tpope/vim-commentary'                " gc 注释/取消注释
Plug 'tpope/vim-surround'                  " cs/ds/ys 操作括号引号
Plug 'mg979/vim-visual-multi'              " 多光标编辑 (<C-n> 选中)
Plug 'jiangmiao/auto-pairs'                " 自动补全括号引号
Plug 'tpope/vim-repeat'                    " . 命令支持插件操作
Plug 'tpope/vim-unimpaired'                " [b ]b [q ]q 等成对快捷键
Plug 'junegunn/vim-easy-align'             " ga 对齐 (=, :, | 等)

" --- Git 集成 ---
Plug 'tpope/vim-fugitive'                  " :Git 命令
Plug 'airblade/vim-gitgutter'              " 行号旁 git diff 标记
Plug 'junegunn/gv.vim'                     " :GV 查看 git 提交历史

" --- Markdown ---
Plug 'godlygeek/tabular'                   " 表格对齐

" --- Tmux 集成 (仅当检测到 tmux 环境) ---
if !empty($TMUX)
    Plug 'christoomey/vim-tmux-navigator'  " C-hjkl 无缝切换 vim/tmux 窗格
    Plug 'tmux-plugins/vim-tmux-focus-events'
endif

call plug#end()

" ===== 插件配置 =====

" --- 主题 ---
if has('termguicolors') && ($COLORTERM == 'truecolor' || $COLORTERM == '24bit')
    set termguicolors
endif
let g:gruvbox_contrast_dark = 'medium'
let g:gruvbox_italic = 1
silent! colorscheme gruvbox
set background=dark

" --- vim-devicons (仅 Nerd Font 环境加载) ---
if s:has_nerd_font
    let g:webdevicons_enable = 1
    let g:webdevicons_conceal_nerdtree_brackets = 1
    " 解决某些终端下图标后文件名粘连问题: 在图标和文件名之间加空格
    let g:DevIconsEnableFoldersOpenClose = 1
    let g:WebDevIconsUnicodeDecorateFolderNodes = 1
else
    " 禁用 devicons 的所有集成，避免垃圾字符
    let g:webdevicons_enable = 0
endif

" --- vim-airline ---
let g:airline#extensions#tabline#enabled = 1
let g:airline#extensions#tabline#formatter = 'unique_tail'
let g:airline_theme = 'gruvbox'

if s:has_nerd_font
    " Nerd Font 环境: 使用 Powerline 符号 (需要打补丁的字体)
    let g:airline_powerline_fonts = 1
else
    " 无 Nerd Font: 使用 ASCII 回退符号，兼容所有终端
    let g:airline_powerline_fonts = 0
    let g:airline_symbols = {}
    let g:airline_symbols.branch    = '|'
    let g:airline_symbols.readonly  = 'RO'
    let g:airline_symbols.linenr    = ':'
    let g:airline_symbols.maxlinenr = ''
    let g:airline_symbols.dirty     = '*'
    let g:airline_symbols.crypt     = '🔒'
    let g:airline_symbols.paste     = 'PASTE'
    let g:airline_symbols.spell     = 'SPELL'
    let g:airline_symbols.notexists = '?'
    let g:airline_symbols.whitespace = '!'
endif

" 禁用 devicons 集成 airline (如果不满足条件)
if !s:has_nerd_font
    let g:airline#extensions#tabline#enabled = 1
endif

" --- NERDTree ---
let g:NERDTreeShowHidden = 1
let g:NERDTreeMinimalUI = 1
" 箭头符号: 使用标准 Unicode (U+25B8/U+25BE)，几乎所有现代终端都支持
" 如果终端极旧不支持，可改用 ASCII: let g:NERDTreeDirArrowExpandable = '+'
"                                    let g:NERDTreeDirArrowCollapsible = '-'
let g:NERDTreeDirArrowExpandable = '▸'
let g:NERDTreeDirArrowCollapsible = '▾'
nnoremap <silent> <Leader>t :NERDTreeToggle<CR>
nnoremap <silent> <Leader>e :NERDTreeFind<CR>

" 无 Nerd Font 时用纯文本标记代替图标
if !s:has_nerd_font
    let g:NERDTreeIndicatorMapCustom = {
        \ 'Modified'  : '~',
        \ 'Staged'    : '+',
        \ 'Untracked' : '?',
        \ 'Renamed'   : '>',
        \ 'Unmerged'  : '!',
        \ 'Deleted'   : 'x',
        \ 'Dirty'     : '*',
        \ 'Clean'     : ' ',
        \ 'Ignored'   : '-',
        \ 'Unknown'   : '?'
        \ }
endif

" --- vim-visual-multi ---
let g:VM_maps = {}
let g:VM_maps['Find Under'] = '<C-n>'
let g:VM_maps['Find Subword Under'] = '<C-n>'

" --- rainbow 括号 ---
let g:rainbow_active = 1

" --- vim-startify ---
let g:startify_change_to_dir = 1
let g:startify_session_autoload = 1
let g:startify_lists = [
    \ { 'type': 'files',     'header': ['   最近文件'] },
    \ { 'type': 'dir',       'header': ['   当前目录: ' . getcwd()] },
    \ { 'type': 'sessions',  'header': ['   Sessions'] },
    \ { 'type': 'bookmarks', 'header': ['   书签'] },
    \ ]
let g:startify_bookmarks = [
    \ { 'c': '~/configure' },
    \ { 'l': '~/lattice-pdf' },
    \ { 'p': '~/PyQCU' },
    \ { 'q': '~/PyQUDA' },
    \ ]

" --- vim-easy-align ---
xmap ga <Plug>(EasyAlign)
nmap ga <Plug>(EasyAlign)

" ===== 快捷键 (Leader = 空格) =====
let mapleader = " "
let maplocalleader = " "

" --- 基本操作 ---
nnoremap <Leader>w :w<CR>
nnoremap <Leader>q :q<CR>
nnoremap <Leader>Q :q!<CR>
nnoremap <Leader>s :source ~/.vimrc<CR>
nnoremap <Leader>h :nohlsearch<CR>

" --- 分屏导航 (Ctrl+hjkl 代替 Ctrl+w+hjkl) ---
nnoremap <silent> <C-h> :wincmd h<CR>
nnoremap <silent> <C-j> :wincmd j<CR>
nnoremap <silent> <C-k> :wincmd k<CR>
nnoremap <silent> <C-l> :wincmd l<CR>

" --- jk 代替 Esc ---
inoremap jk <Esc>
inoremap kj <Esc>
cnoremap jk <C-c>

" --- Buffer 操作 ---
nnoremap <Leader>bn :bnext<CR>
nnoremap <Leader>bp :bprevious<CR>
nnoremap <Leader>bd :bdelete<CR>
nnoremap <Leader>bl :ls<CR>:b<Space>

" --- 快速修复列表 ---
nnoremap <Leader>cn :cnext<CR>
nnoremap <Leader>cp :cprev<CR>
nnoremap <Leader>co :copen<CR>

" --- 缩进保持选择的视觉模式 ---
vnoremap < <gv
vnoremap > >gv

" --- 上下移动整行 ---
nnoremap <A-j> :m .+1<CR>==
nnoremap <A-k> :m .-2<CR>==
inoremap <A-j> <Esc>:m .+1<CR>==gi
inoremap <A-k> <Esc>:m .-2<CR>==gi
vnoremap <A-j> :m '>+1<CR>gv=gv
vnoremap <A-k> :m '<-2<CR>gv=gv

" --- 搜索选中文本 (visual 模式按 * ) ---
vnoremap // y/\V<C-R>=escape(@",'/\')<CR><CR>

" --- 一键执行 ---
autocmd FileType python nnoremap <buffer> <Leader>r :w<CR>:!python %<CR>
autocmd FileType sh nnoremap <buffer> <Leader>r :w<CR>:!bash %<CR>
autocmd FileType c,cpp nnoremap <buffer> <Leader>r :w<CR>:!gcc % -o /tmp/a.out && /tmp/a.out<CR>

" ===== 文件类型缩进 =====
autocmd FileType python   setlocal ts=4 sw=4 sts=4 expandtab
autocmd FileType yaml     setlocal ts=2 sw=2 sts=2 expandtab
autocmd FileType html,css,javascript,json setlocal ts=2 sw=2 sts=2 expandtab
autocmd FileType c,cpp,cuda   setlocal ts=4 sw=4 sts=4 noexpandtab
autocmd FileType make,cmake   setlocal ts=4 sw=4 sts=4 noexpandtab " Makefile 必须用 tab
autocmd FileType markdown setlocal ts=2 sw=2 sts=2 expandtab spell

" ===== 光标位置记忆 =====
autocmd BufReadPost *
    \ if line("'\"") >= 1 && line("'\"") <= line("$") && &ft !~# 'commit'
    \ |   exe "normal! g`\""
    \ | endif

" ===== 不可见字符显示 ====="
nnoremap <Leader>l :set list!<CR>
set listchars=tab:▸\ ,trail:·,nbsp:␣,extends:→,precedes:←

" ===== netrw 内置文件浏览器配置 =====
let g:netrw_banner = 0
let g:netrw_liststyle = 3
let g:netrw_browse_split = 4
let g:netrw_altv = 1
let g:netrw_winsize = 25

" ===== 备份与 Swap 文件集中管理 =====
set backupdir=~/.vim/backup//
set directory=~/.vim/swap//
set undodir=~/.vim/undodir//
silent! call mkdir(&backupdir, 'p', 0700)
silent! call mkdir(&directory, 'p', 0700)
silent! call mkdir(&undodir, 'p', 0700)

" ===== vim-plug 插件管理器 v3 END =====
PLUGEOF

log_ok "插件配置写入完毕"

# -------------------------------------------------------------------
# 安装 vim 插件 (无头模式)
# -------------------------------------------------------------------
log_info "通过 vim-plug 安装所有插件 (纯 vimscript, 无外部依赖)..."
vim -es -u "$_VIMRC_DST" -i NONE -c "PlugInstall" -c "qa" 2>&1 | while IFS= read -r line; do
    if [[ "$line" =~ (Installing|Updated|Already|Finishing) ]]; then
        log_info "  $line"
    fi
done || log_warn "部分插件安装可能失败，打开 vim 后执行 :PlugInstall 重试"

log_ok "插件安装完毕"

# -------------------------------------------------------------------
# 收尾工作
# -------------------------------------------------------------------
log_title "安装完成"

echo ""
echo -e "  ${_GRN}✓${_NC} vim         : $(vim --version 2>/dev/null | head -1 | cut -d' ' -f1-5)"
echo -e "  ${_GRN}✓${_NC} 插件管理器  : vim-plug (${_PLUG_PATH})"
echo -e "  ${_GRN}✓${_NC} 配置文件    : ${_VIMRC_DST}"
echo -e "  ${_GRN}✓${_NC} 补全方案    : vim 内置 ins-completion (Tab 触发)"
echo -e "  ${_GRN}✓${_NC} 终端        : ${_TERM_EMULATOR}"
if $_HAS_NERD_FONT; then
    echo -e "  ${_GRN}✓${_NC} Nerd Font   : 已启用 (vim-devicons, powerline 符号)"
else
    echo -e "  ${_YLW}⚠${_NC} Nerd Font   : 未启用 (使用 ASCII 回退方案, 无图标)"
    echo ""
    echo -e "  ${_BLD}如需启用图标支持:${_NC}"
    echo "    1. 从 https://www.nerdfonts.com 下载安装 Nerd Font"
    echo "    2. 在终端设置中切换为该字体"
    echo "    3. 执行: touch ~/.vim/nerd-font-enabled && vim_init.sh"
fi
echo ""
echo -e "  ${_BLD}核心快捷键:${_NC}"
echo -e "  ┌──────────────────────┬──────────────────────────────┐"
echo -e "  │ ${_CYN}Tab${_NC}                  │ 触发/导航关键字补全            │"
echo -e "  │ ${_CYN}Ctrl+Space${_NC}          │ omni 补全 (Python/C/HTML...)  │"
echo -e "  │ ${_CYN}jk${_NC}                  │ 退出插入模式 (代替 Esc)       │"
echo -e "  │ ${_CYN}空格 + w${_NC}            │ 保存文件                      │"
echo -e "  │ ${_CYN}空格 + q${_NC}            │ 关闭窗口                      │"
echo -e "  │ ${_CYN}Ctrl + h/j/k/l${_NC}      │ 分屏导航                      │"
echo -e "  │ ${_CYN}gc${_NC}                  │ 注释/取消注释 (vim-commentary) │"
echo -e "  │ ${_CYN}空格 + t${_NC}            │ NERDTree 文件浏览器            │"
echo -e "  │ ${_CYN}空格 + h${_NC}            │ 清除搜索高亮                   │"
echo -e "  │ ${_CYN}空格 + r${_NC}            │ 运行当前文件 (Python/Shell/C)  │"
echo -e "  └──────────────────────┴──────────────────────────────┘"
echo ""
echo -e "  ${_BLD}补全类型速查:${_NC}"
echo -e "  ┌──────────────────────┬──────────────────────────────┐"
echo -e "  │ ${_CYN}Tab${_NC}                  │ 关键字补全 (当前缓冲区)       │"
echo -e "  │ ${_CYN}Ctrl+Space${_NC}          │ omni 补全 (智能, 文件类型感知) │"
echo -e "  │ ${_CYN}Ctrl+F${_NC}              │ 文件路径补全                  │"
echo -e "  │ ${_CYN}Ctrl+x Ctrl+l${_NC}       │ 整行补全                      │"
echo -e "  │ ${_CYN}Ctrl+x Ctrl+]${_NC}       │ 标签补全                      │"
echo -e "  │ ${_CYN}Ctrl+n / Ctrl+p${_NC}     │ 通用关键字补全 (向前/向后)    │"
echo -e "  └──────────────────────┴──────────────────────────────┘"
echo ""

log_ok "vim_init.sh 全部完毕"
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
