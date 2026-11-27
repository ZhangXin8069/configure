#!/usr/bin/env bash
# 环境主入口: 被 ~/.zshrc / ~/.bashrc source (不可直接执行)
# 职责: PATH/LD_LIBRARY_PATH/locale/git 别名/screen 会话别名/通用别名
# @INIT@
_configure_env_source=${BASH_SOURCE[0]:-${0}}
case "${_configure_env_source}" in
    */*) _configure_env_root=${_configure_env_source%/*}; [ -z "${_configure_env_root}" ] && _configure_env_root="/" ;;
    *) _configure_env_root=. ;;
esac
_configure_env_name=${_configure_env_source##*/}
_configure_env_root=$(CDPATH= cd -P -- "${_configure_env_root}" && pwd -P)
_configure_env_self="${_configure_env_root%/}/${_configure_env_name}"
unset _configure_env_source _configure_env_name

# @CONFLICT_GUARD_PAUSED@
# 用户要求暂时停用大规模 alias/function/executable 冲突告警；恢复时取消以下注释。
    # if [ -n "${_SCREEN_GUIDE_PATH:-}" ] &&
    #     [ "${_SCREEN_GUIDE_PATH}" != "${_configure_env_root}/bin/_screen-guide.txt" ]; then
    #     printf '[WARN] env.sh 未加载：变量 _SCREEN_GUIDE_PATH 已被定义为 %s。\n' \
    #         "${_SCREEN_GUIDE_PATH}" >&2
    #     unset _configure_env_self _configure_env_root
    #     return 1
    # fi
    #
    # if [ ! -r "${_configure_env_root}/lib/_env_conflicts.sh" ]; then
    #     printf '[WARN] env.sh 未加载：缺少冲突预检文件 %s。\n' \
    #         "${_configure_env_root}/lib/_env_conflicts.sh" >&2
    #     unset _configure_env_self _configure_env_root
    #     return 1
    # fi
    # if (
    #     . "${_configure_env_root}/lib/_env_conflicts.sh"
    #     _env_conflicts_preflight "${_configure_env_root}" "${_configure_env_self}"
    # ); then
    #     _configure_env_preflight_status=0
    # else
    #     _configure_env_preflight_status=$?
    # fi
    # if [ "${_configure_env_preflight_status}" -ne 0 ]; then
    #     unset _configure_env_preflight_status _configure_env_self _configure_env_root
    #     return 1
    # fi
    # unset _configure_env_preflight_status
# @EXPORT@
# export TERM=xterm
# export TERM=xterm-256color
# @@LOCALE@@
# 实测全部 locale 类别，避免仅 LC_CTYPE 可用时掩盖其他类别失效或产生 setlocale 告警。
_locale_ready=0
_locale_charmap=$(locale charmap 2>/dev/null || true)
if [ "${_locale_charmap}" = "UTF-8" ]; then
    _locale_errors=$(locale 2>&1 >/dev/null || true)
    [ -z "${_locale_errors}" ] && _locale_ready=1
fi
if [ "${_locale_ready}" -eq 0 ]; then
    for _locale_candidate in \
        "${LC_ALL:-}" "${LC_CTYPE:-}" "${LANG:-}" \
        C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8 zh_CN.UTF-8 zh_CN.utf8; do
        [ -n "${_locale_candidate}" ] || continue
        if [ "$(LC_ALL="${_locale_candidate}" locale charmap 2>/dev/null || true)" = "UTF-8" ] \
            && [ -z "$(LC_ALL="${_locale_candidate}" locale 2>&1 >/dev/null || true)" ]; then
            export LANG="${_locale_candidate}" LC_ALL="${_locale_candidate}"
            _locale_ready=1
            break
        fi
    done
fi
if [ "${_locale_ready}" -eq 0 ]; then
    export LANG=C LC_ALL=C
fi
unset _locale_charmap _locale_candidate _locale_errors _locale_ready
# @@OPENMPI@@
# MPI_HOME=/usr/local/openmpi
# export PATH=${MPI_HOME}/bin:${PATH}
# export LD_LIBRARY_PATH=${MPI_HOME}/lib:${LD_LIBRARY_PATH}
# export MPI_INCLUDE_PATH=${MPI_HOME}/include:${MPI_INCLUDE_PATH}
# export MANPATH=${MPI_HOME}/share/man:${MANPATH}
# @@CUDA@@
# CUDA_HOME=/usr/local/cuda
# export PATH=${CUDA_HOME}/bin:${PATH}
# export LD_LIBRARY_PATH=${CUDA_HOME}/lib:${LD_LIBRARY_PATH}
# export CUDA_INCLUDE_PATH=${CUDA_HOME}/include:${CUDA_INCLUDE_PATH}
# export MANPATH=${CUDA_HOME}/share/man:${MANPATH}
# @@PATH@@
# 防重复: 已含仓库 bin 前缀则跳过（env.sh 可能被多次 source，避免 PATH 无限拼接）
case ":${PATH}:" in
*":${_configure_env_root}/bin:"*) : ;;
*) export PATH=${_configure_env_root}/bin:${HOME}/.local/bin:${HOME}/sbin:${HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH} ;;
esac
# @@LD_LIBRARY_PATH@@
# 防重复: 已含仓库 lib 前缀则跳过
case ":${LD_LIBRARY_PATH}:" in
*":${_configure_env_root}/lib:"*) : ;;
*) export LD_LIBRARY_PATH=${_configure_env_root}/lib:${HOME}/.local/lib:${HOME}/slib:${HOME}/lib:/usr/local/lib:/usr/lib:/usr/lib64:/usr/libx32:/usr/lib32:/lib:/lib64:/libx32:/lib32:${LD_LIBRARY_PATH} ;;
esac
# @ALIAS@
alias ...=../..
alias ....=../../..
alias .....=../../../..
alias ......=../../../../..
alias 1='cd -1'
alias 2='cd -2'
alias 3='cd -3'
alias 4='cd -4'
alias 5='cd -5'
alias 6='cd -6'
alias 7='cd -7'
alias 8='cd -8'
alias 9='cd -9'
alias _='sudo '
alias egrep='grep -E --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias fgrep='grep -F --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias grep='grep --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
# @GIT_ALIASES@
source "${_configure_env_root}/lib/_git_aliases.sh"
_SCREEN_GUIDE_PATH="${_configure_env_root}/bin/_screen-guide.txt"
source "${_configure_env_root}/lib/_screen.sh"
_screen_normalize_term
# screen 会话: 默认取 SSH_CLIENT 客户端地址，也可用 SSH_SCREEN_NAME 或参数覆盖
alias scn='_screen_new'
alias scl='_screen_list'
alias scr='_screen_resume'
alias scw='screen -wipe'
# ls 系（修正原 --color=tty 非法选项为 --color=auto; 两 shell 通用）
alias ls='ls --color=auto'
alias l='ls -lah'
alias ll='ls -lh'
alias la='ls -lAh'
alias lsa='ls -lah'
alias md='mkdir -p'
alias rd='rmdir'
# 通用增强
alias df='df -h'
alias du='du -h'
alias free='free -h'
alias path='echo -e ${PATH//:/\\n}'
# 常用工具
alias v='vim'
alias python='python3'
alias pip='pip3'
alias py='python'
alias clc='clear'
alias gsize='git count-objects -vH'
alias gcat-tag='git for-each-ref --sort=-creatordate --count=10 --format="tag: %(refname:short)%0aobject: %(objecttype) %(objectname)%0apeeled: %(*objecttype) %(*objectname)%0atagger: %(taggername) %(taggeremail)%0ataggerdate: %(taggerdate:iso-strict)%0acreatordate: %(creatordate:iso-strict)%0atag-subject: %(subject)%0aauthor: %(*authorname) %(*authoremail)%0aauthordate: %(*authordate:iso-strict)%0acommitter: %(*committername) %(*committeremail)%0acommitterdate: %(*committerdate:iso-strict)%0acommit-subject: %(*subject)%0amessage:%0a%(contents)%0a---%1f" refs/tags | awk '\''BEGIN { RS=sprintf("%c", 31) } $0 !~ /^\n?$/ { n++; record[n]=$0 } END { for (i=n; i>=1; i--) { sub(/^\n/, "", record[i]); print record[i] } }'\'''
alias gback-tag='git fetch origin --tags --force'
alias his='history | tail'
alias ohmyzsh='${EDITOR:-vim} ~/.oh-my-zsh'
alias zshconfig='${EDITOR:-vim} ~/.zshrc'
# zsh/oh-my-zsh 专有（bash 下不定义, 避免覆盖内置 history 语义；which-command 保留 zsh 默认）
if [ -n "${ZSH_VERSION}" ]; then
    alias history='omz_history'
fi
# zda: 激活 ${HOME}/miniforge3 的 conda base，并把 base 的 bin/include/lib 等
# 路径前置到对应开发环境变量；环境缺失时打印安装与换源指南
_ZDA_GUIDE_PATH="${_configure_env_root}/bin/_zda-guide.txt"
# zda 注入的环境变量声明（唯一的权威清单，文档与测试都以此为准）：
#   PATH                  <- bin sbin nvvm/bin
#   LD_LIBRARY_PATH       <- lib lib64 targets/*/lib          （_ZDA_SKIP_LIBPATH=1 时跳过）
#   LIBRARY_PATH          <- lib lib64 targets/*/lib          （_ZDA_SKIP_LIBPATH=1 时跳过）
#   CPATH                 <- include targets/*/include
#   CPLUS_INCLUDE_PATH    <- include targets/*/include
#   C_INCLUDE_PATH        <- include targets/*/include
#   PYTHONPATH            <- lib/python*/site-packages
#   PKG_CONFIG_PATH       <- lib/pkgconfig share/pkgconfig
#   CMAKE_PREFIX_PATH     <- 前缀根
#   MANPATH               <- share/man man
#   ACLOCAL_PATH          <- share/aclocal
#   CUDA_PATH / CUDA_HOME / CUDA_ROOT / CUDAToolkit_ROOT <- targets/<arch> 或前缀根
#   CUDA_INCLUDE_PATH     <- targets/*/include（另有 targets/*/lib/stubs 供链接期占位）
#   MPI_HOME / OPENMPI_ROOT / OPAL_PREFIX <- 前缀根
#   MPICC MPICXX MPIF77 MPIF90 MPIFORT    <- 前缀 bin 下的同名包装器
#   MPI_INCLUDE_PATH / MPI_LIBRARY_PATH   <- include / lib（MPI 头与 libmpi）
#   OMPI_CC / OMPI_CXX / OMPI_FC          <- 前缀内的 conda 编译器包装
#   HDF5_DIR / HDF5_ROOT / HDF5_INCLUDE_PATH / HDF5_MPI / HDF5_LIBRARY_PATH
#   CC CXX CPP FC F77                     <- 前缀内的 conda 编译器（仅当对应可执行存在）
#   OMPI_ALLOW_RUN_AS_ROOT / OMPI_ALLOW_RUN_AS_ROOT_CONFIRM / MPI_ALLOW_RUN_AS_ROOT
# 规则：目录/可执行必须存在；conda 项前置；旧值保留在后；按物理路径去重；可重复执行。
# 1 = 跳过 LD_LIBRARY_PATH / LIBRARY_PATH 注入（HPC 上 conda 的 libstdc++
# 可能遮蔽系统或 module 提供的版本；其余变量仍会同步）
_ZDA_SKIP_LIBPATH="${_ZDA_SKIP_LIBPATH:-0}"

# 判断 ":" 分隔列表里是否已有某项（POSIX + zsh 通用，不依赖 word splitting）
_zda_list_has() {
    case ":${1:-}:" in
    *":${2:-}:"*) return 0 ;;
    esac
    return 1
}

# 解析目录的物理路径；失败时原样返回。用于合并 python3.1 -> python3.12 这类软链接
_zda_real_dir() {
    local _resolved
    _resolved=$(CDPATH= cd -P -- "$1" 2>/dev/null && pwd -P) || _resolved=''
    printf '%s' "${_resolved:-$1}"
}

# 把存在的目录前置到指定变量，已存在的项移到最前（conda 覆盖旧配置），其余保持原序
_zda_prepend_env() {
    local _var=$1
    shift
    if [ -n "${ZSH_VERSION:-}" ]; then setopt localoptions nonomatch; fi
    local _cur _dir _real _out='' _seen='' _segs _seg _rest='' _trailing=0
    eval "_cur=\${${_var}:-}"
    for _dir in "$@"; do
        [ -n "${_dir}" ] && [ -d "${_dir}" ] || continue
        _real=$(_zda_real_dir "${_dir}")
        _zda_list_has "${_seen}" "${_real}" && continue
        _seen="${_seen:+${_seen}:}${_real}"
        _out="${_out:+${_out}:}${_dir}"
    done
    [ -n "${_out}" ] || return 0
    case "${_cur}" in
    *:) _trailing=1 ;;
    esac
    _segs=${_cur}
    while [ -n "${_segs}" ]; do
        _seg=${_segs%%:*}
        case "${_segs}" in
        *:*) _segs=${_segs#*:} ;;
        *) _segs='' ;;
        esac
        [ -n "${_seg}" ] || continue
        _real=$(_zda_real_dir "${_seg}")
        _zda_list_has "${_seen}" "${_real}" && continue
        _zda_list_has "${_rest}" "${_seg}" && continue
        _seen="${_seen:+${_seen}:}${_real}"
        _rest="${_rest:+${_rest}:}${_seg}"
    done
    if [ -n "${_rest}" ]; then
        if [ "${_trailing}" -eq 1 ]; then
            export "${_var}=${_out}:${_rest}:"
        else
            export "${_var}=${_out}:${_rest}"
        fi
    elif [ "${_trailing}" -eq 1 ]; then
        export "${_var}=${_out}:"
    else
        export "${_var}=${_out}"
    fi
}

# 同步 base 的开发环境变量；幂等，可重复调用
_zda_sync_env() {
    local _p=${CONDA_PREFIX:-}
    [ -n "${_p}" ] && [ -d "${_p}" ] || return 1
    if [ -n "${ZSH_VERSION:-}" ]; then setopt localoptions nonomatch; fi
    local -a _arch_dirs=("${_p}"/targets/*)
    local -a _site_dirs=("${_p}"/lib/python*/site-packages)
    local _arch_includes=() _arch_libs=() _sp _arch_root=''

    # targets/<arch> 只保留目录本身，供 include/lib/stubs 复用；
    # 首个架构根单独存成标量，避免 zsh 数组从 1 开始导致 [0] 取空
    for _sp in "${_arch_dirs[@]}"; do
        [ -d "${_sp}" ] || continue
        [ -n "${_arch_root}" ] || _arch_root=${_sp}
        [ -d "${_sp}/include" ] && _arch_includes+=("${_sp}/include")
        [ -d "${_sp}/lib" ] && _arch_libs+=("${_sp}/lib")
    done

    _zda_prepend_env PATH "${_p}/bin" "${_p}/sbin" "${_p}/nvvm/bin"
    if [ "${_ZDA_SKIP_LIBPATH}" != 1 ]; then
        _zda_prepend_env LD_LIBRARY_PATH "${_p}/lib" "${_p}/lib64" "${_arch_libs[@]}"
        _zda_prepend_env LIBRARY_PATH "${_p}/lib" "${_p}/lib64" "${_arch_libs[@]}"
    fi
    _zda_prepend_env CPATH "${_p}/include" "${_arch_includes[@]}"
    _zda_prepend_env CPLUS_INCLUDE_PATH "${_p}/include" "${_arch_includes[@]}"
    _zda_prepend_env C_INCLUDE_PATH "${_p}/include" "${_arch_includes[@]}"
    _zda_prepend_env PYTHONPATH "${_site_dirs[@]}"
    _zda_prepend_env PKG_CONFIG_PATH "${_p}/lib/pkgconfig" "${_p}/share/pkgconfig"
    _zda_prepend_env CMAKE_PREFIX_PATH "${_p}"
    _zda_prepend_env MANPATH "${_p}/share/man" "${_p}/man"
    _zda_prepend_env ACLOCAL_PATH "${_p}/share/aclocal"

    # --- CUDA：targets/<arch> 是 nvcc 的根，include 与 lib/stubs 都在其下 ---
    if [ -n "${_arch_root}" ] && [ -d "${_arch_root}/include" ]; then
        export CUDA_PATH="${_arch_root}"
        export CUDA_HOME="${_arch_root}"
        export CUDA_ROOT="${_arch_root}"
        export CUDAToolkit_ROOT="${_arch_root}"
        _zda_prepend_env CUDA_INCLUDE_PATH "${_arch_root}/include"
        _zda_prepend_env CUDA_LIBRARY_PATH "${_arch_root}/lib" "${_arch_root}/lib/stubs"
    fi
    [ -x "${_p}/bin/nvcc" ] && export CUDACXX="${_p}/bin/nvcc"

    # --- MPI：conda 的 openmpi/mpich 都有 <prefix>/bin/mpicc 与 <prefix>/include/mpi.h ---
    if [ -x "${_p}/bin/mpicc" ]; then
        export MPI_HOME="${_p}"
        export OPENMPI_ROOT="${_p}"
        export OPAL_PREFIX="${_p}"
        [ -x "${_p}/bin/mpicc" ] && export MPICC="${_p}/bin/mpicc"
        [ -x "${_p}/bin/mpicxx" ] && export MPICXX="${_p}/bin/mpicxx"
        [ -x "${_p}/bin/mpif77" ] && export MPIF77="${_p}/bin/mpif77"
        [ -x "${_p}/bin/mpif90" ] && export MPIF90="${_p}/bin/mpif90"
        [ -x "${_p}/bin/mpifort" ] && export MPIFORT="${_p}/bin/mpifort"
        _zda_prepend_env MPI_INCLUDE_PATH "${_p}/include"
        _zda_prepend_env MPI_LIBRARY_PATH "${_p}/lib"
        # 让 MPI 包装器调用 conda 编译器，而不是系统 gcc
        if [ -x "${_p}/bin/x86_64-conda-linux-gnu-cc" ]; then
            export OMPI_CC="${_p}/bin/x86_64-conda-linux-gnu-cc"
        elif [ -x "${_p}/bin/gcc" ]; then
            export OMPI_CC="${_p}/bin/gcc"
        fi
        if [ -x "${_p}/bin/x86_64-conda-linux-gnu-c++" ]; then
            export OMPI_CXX="${_p}/bin/x86_64-conda-linux-gnu-c++"
        elif [ -x "${_p}/bin/g++" ]; then
            export OMPI_CXX="${_p}/bin/g++"
        fi
        if [ -x "${_p}/bin/x86_64-conda-linux-gnu-gfortran" ]; then
            export OMPI_FC="${_p}/bin/x86_64-conda-linux-gnu-gfortran"
        elif [ -x "${_p}/bin/gfortran" ]; then
            export OMPI_FC="${_p}/bin/gfortran"
        fi
        # 容器/root 场景下 mpirun 默认拒绝运行；与 docker-* 快照保持一致
        export OMPI_ALLOW_RUN_AS_ROOT=1
        export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
        export MPI_ALLOW_RUN_AS_ROOT=1
    fi

    # --- HDF5：并行 HDF5 需要与 MPI 同一变体，这里按前缀统一声明 ---
    if [ -d "${_p}/include/hdf5" ] || [ -f "${_p}/include/hdf5.h" ]; then
        export HDF5_DIR="${_p}"
        export HDF5_ROOT="${_p}"
        export HDF5_MPI="ON"
        _zda_prepend_env HDF5_INCLUDE_PATH "${_p}/include"
        _zda_prepend_env HDF5_LIBRARY_PATH "${_p}/lib"
    fi

    # --- 组件根目录（沿用 lib/snsc-v20260817/env.sh 的 *_ROOT 命名）---
    # conda 把各组件平铺在同一个前缀里，因此这些 ROOT 都指向前缀本身；
    # 用组件特征文件做门禁，缺哪个就不设哪个，避免给出无效路径。
    [ -f "${_p}/include/ncurses.h" ] && export NCURSES_ROOT="${_p}"
    if [ -d "${_p}/lib/python3.12" ] || [ -d "${_p}/lib/python3.11" ] ||
        [ -d "${_p}/lib/python3.10" ] || [ -d "${_p}/lib/python3.9" ]; then
        export PYTHON_ROOT="${_p}"
    fi
    [ -f "${_p}/include/hwloc.h" ] && export HWLOC_ROOT="${_p}"
    [ -f "${_p}/include/ucp/api/ucp.h" ] && export UCX_ROOT="${_p}"
    if [ -d "${_p}/lib/pmix" ] || [ -f "${_p}/include/pmix.h" ]; then
        export PMIX_ROOT="${_p}"
    fi
    [ -f "${_p}/include/event2/event.h" ] && export LIBEVENT_ROOT="${_p}"
    [ -x "${_p}/bin/gcc" ] && export GCC_ROOT="${_p}"
    # 真正的查找路径是 CMAKE_PREFIX_PATH；不设 CMAKE_ROOT，它是 cmake 内部变量

    # --- 编译器：conda activate 已设过三前缀编译器时保留，否则补 prefixed/unprefixed ---
    _zda_set_compiler() {
        local _var=$1 _bin=$2 _cur
        [ -x "${_bin}" ] || return 1
        eval "_cur=\${${_var}:-}"
        case "${_cur}" in
        "${_p}"/*) return 0 ;;
        esac
        export "${_var}=${_bin}"
    }
    if [ -x "${_p}/bin/x86_64-conda-linux-gnu-cc" ]; then
        _zda_set_compiler CC "${_p}/bin/x86_64-conda-linux-gnu-cc"
    else
        _zda_set_compiler CC "${_p}/bin/cc"
    fi
    if [ -x "${_p}/bin/x86_64-conda-linux-gnu-c++" ]; then
        _zda_set_compiler CXX "${_p}/bin/x86_64-conda-linux-gnu-c++"
    else
        _zda_set_compiler CXX "${_p}/bin/c++"
    fi
    if [ -x "${_p}/bin/x86_64-conda-linux-gnu-cpp" ]; then
        _zda_set_compiler CPP "${_p}/bin/x86_64-conda-linux-gnu-cpp"
    else
        _zda_set_compiler CPP "${_p}/bin/cpp"
    fi
    if [ -x "${_p}/bin/x86_64-conda-linux-gnu-gfortran" ]; then
        _zda_set_compiler FC "${_p}/bin/x86_64-conda-linux-gnu-gfortran"
        _zda_set_compiler F77 "${_p}/bin/x86_64-conda-linux-gnu-gfortran"
    else
        _zda_set_compiler FC "${_p}/bin/gfortran"
        _zda_set_compiler F77 "${_p}/bin/gfortran"
    fi
    unset -f _zda_set_compiler
    return 0
}

# 移除会遮蔽 conda base 可执行文件的旧别名（python/pip 系）；结果写入
# _ZDA_DROPPED_ALIASES。必须在当前 shell 执行，不能用 $(...) 放进子 shell
_zda_drop_aliases() {
    local _name
    _ZDA_DROPPED_ALIASES=''
    for _name in python python3 pip pip3 py ipython; do
        alias "${_name}" >/dev/null 2>&1 || continue
        unalias "${_name}" 2>/dev/null || continue
        _ZDA_DROPPED_ALIASES="${_ZDA_DROPPED_ALIASES}${_ZDA_DROPPED_ALIASES:+ }${_name}"
    done
}

_zda_activate_base() {
    local conda_root="${HOME}/miniforge3"
    local conda_sh="${conda_root}/etc/profile.d/conda.sh"

    if [ ! -d "${conda_root}" ] || [ ! -r "${conda_sh}" ]; then
        printf '[WARN] zda: 未找到可用的 conda 环境 %s（缺少 %s）。\n' \
            "${conda_root}" "${conda_sh}" >&2
        if [ -n "${_ZDA_GUIDE_PATH:-}" ] && [ -r "${_ZDA_GUIDE_PATH}" ]; then
            command cat "${_ZDA_GUIDE_PATH}" >&2
        else
            printf 'zda: 环境配置指南缺失：%s\n' "${_ZDA_GUIDE_PATH}" >&2
        fi
        return 1
    fi

    # 已在该 base 时不重复激活，但仍补同步变量与别名，保证旧 shell 也能用
    if [ -n "${CONDA_PREFIX:-}" ] && [ "${CONDA_PREFIX}" -ef "${conda_root}" ]; then
        printf 'zda: 已处于 %s（base）\n' "${CONDA_PREFIX}"
    else
        . "${conda_sh}"
        if ! conda activate base; then
            printf '[WARN] zda: conda activate base 执行失败。\n' >&2
            return 1
        fi
        if [ -z "${CONDA_PREFIX:-}" ] || [ ! "${CONDA_PREFIX}" -ef "${conda_root}" ]; then
            printf '[WARN] zda: 激活后 CONDA_PREFIX=%s，与预期 %s 不一致。\n' \
                "${CONDA_PREFIX:-<空>}" "${conda_root}" >&2
            return 1
        fi
        printf 'zda: 已激活 %s（base）\n' "${CONDA_PREFIX}"
    fi

    _zda_sync_env || {
        printf '[WARN] zda: 同步 %s 的开发环境变量失败。\n' "${conda_root}" >&2
        return 1
    }
    _zda_drop_aliases
    if [ -n "${_ZDA_DROPPED_ALIASES}" ]; then
        printf 'zda: 已移除与 base 冲突的别名：%s\n' "${_ZDA_DROPPED_ALIASES}"
    fi
    printf 'zda: 已同步 PATH/CPATH/LIBRARY_PATH/PKG_CONFIG_PATH/PYTHONPATH/CMAKE_PREFIX_PATH/MANPATH 等变量（base 优先）\n'
    return 0
}
alias zda='_zda_activate_base'
# @@ZHANGXIN@@
# alias nvvp='nvvp -vm /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java'
alias nv-smi='nvidia-smi -l 1'
# nvtop 异常退出后 10 秒自动重启；正常退出或 Ctrl-C 时结束
_nnvtop_restart() {
    local _nnvtop_status
    while true; do
        command nvtop "$@"
        _nnvtop_status=$?
        case "${_nnvtop_status}" in
        0 | 130) return "${_nnvtop_status}" ;;
        esac
        printf 'nnvtop: nvtop 异常退出（状态码 %s），10 秒后重启；按 Ctrl-C 停止。\n' "${_nnvtop_status}" >&2
        sleep 10
        _nnvtop_status=$?
        [ "${_nnvtop_status}" -eq 0 ] || return "${_nnvtop_status}"
    done
}
alias nnvtop='_nnvtop_restart'
alias get_files_types="find . -type f -printf '%f\n' | sed -n 's/.*\.\([^.]*\)$/\1/p' | sort -u"
get_git_files_types() {
  while IFS= read -r -d '' f; do
    b=${f##*/}
    [[ $b == *.* && $b != .* ]] && printf '%s\n' "${b##*.}"
  done < <(git ls-files -co --exclude-standard -z) | sort -u
}
# ===== get_soft_links: 递归列出软链接（带指向与高亮） =====
# 用法: get_soft_links [路径]        # 默认 .
# 配色参考 fd -t l：链接青色加粗；目标黄色；断链红色
# 完全自包含；readlink 不可用或失败时逐级兜底到 ls / python3 / perl
# zsh 5+ / bash 4+ 通用；非 TTY 自动关闭颜色
get_soft_links() {
    local root_dir="${1:-.}"
    if [[ ! -d "$root_dir" ]]; then
        printf 'get_soft_links: not a directory: %s\n' "$root_dir" >&2
        return 1
    fi

    # ---- 颜色：仅 TTY 启用 ----
    local use_color=0
    [[ -t 1 ]] && use_color=1
    local C_LINK='' C_ARROW='' C_TARGET='' C_BROKEN='' C_RESET=''
    if (( use_color )); then
        C_LINK=$'\033[1;36m'    # 青加粗（fd symlink 默认）
        C_ARROW=$'\033[0;37m'   # 白
        C_TARGET=$'\033[0;33m'  # 黄
        C_BROKEN=$'\033[1;31m'  # 红加粗
        C_RESET=$'\033[0m'
    fi

    # ---- 收集软链接（不依赖 find，且不进入目录链接） ----
    local -a links=() pending=("$root_dir")
    local current_dir entry link
    local pending_index=0 pending_count=1 array_base=0
    [[ -z "${ZSH_VERSION:-}" ]] || setopt localoptions nullglob
    [[ -z "${ZSH_VERSION:-}" ]] || array_base=1
    while (( pending_index < pending_count )); do
        current_dir="${pending[pending_index + array_base]}"
        pending_index=$((pending_index + 1))
        for entry in "$current_dir"/* "$current_dir"/.[!.]* "$current_dir"/..?*; do
            [[ -e "$entry" || -L "$entry" ]] || continue
            if [[ -L "$entry" ]]; then
                links+=("$entry")
            elif [[ -d "$entry" ]]; then
                case "${entry##*/}" in
                    .git | node_modules) continue ;;
                esac
                pending+=("$entry")
                pending_count=$((pending_count + 1))
            fi
        done
    done

    # ---- 收集可用读取器（单个读取器失败时继续尝试下一个） ----
    # 优先级: readlink → ls -ld 解析 → python3 → perl
    local -a readers=()
    local reader reader_name reader_path
    for reader_name in readlink ls python3 perl; do
        if [[ -n "${ZSH_VERSION:-}" ]]; then
            reader_path=$(whence -p "$reader_name" 2>/dev/null) || reader_path=''
        else
            reader_path=$(type -P "$reader_name" 2>/dev/null) || reader_path=''
        fi
        if [[ -n "$reader_path" && -x "$reader_path" ]]; then
            readers+=("$reader_name")
        fi
    done

    # ---- 遍历 ----
    local count=0 broken=0 target out reader_input
    for link in "${links[@]}"; do
        case "$link" in
            /*) reader_input=$link ;;
            *)  reader_input="./$link" ;;
        esac

        target=''
        for reader in "${readers[@]}"; do
            case "$reader" in
                readlink)
                    target=$(command readlink "$reader_input" 2>/dev/null) || target='' ;;
                ls)
                    out=$(command ls -ld "$reader_input" 2>/dev/null) || out=''
                    case "$out" in
                        *" -> "*) target="${out#* -> }" ;;
                        *)        target='' ;;
                    esac ;;
                python3)
                    target=$(command python3 -c 'import os,sys;sys.stdout.write(os.readlink(sys.argv[1]))' "$reader_input" 2>/dev/null) || target='' ;;
                perl)
                    target=$(command perl -e 'print readlink($ARGV[0])' "$reader_input" 2>/dev/null) || target='' ;;
            esac
            [[ -n "$target" ]] && break
        done
        [[ -n "$target" ]] || target='?'

        if [[ -e "$link" ]]; then
            printf '%s%s%s %s->%s %s%s%s\n' \
                "$C_LINK" "$link" "$C_RESET" \
                "$C_ARROW" "$C_RESET" \
                "$C_TARGET" "$target" "$C_RESET"
        else
            printf '%s%s%s %s->%s %s%s%s %s[broken]%s\n' \
                "$C_LINK" "$link" "$C_RESET" \
                "$C_ARROW" "$C_RESET" \
                "$C_BROKEN" "$target" "$C_RESET" \
                "$C_BROKEN" "$C_RESET"
            broken=$((broken + 1))
        fi
        count=$((count + 1))
    done

    # ---- 汇总（走 stderr，不污染可解析 stdout） ----
    if (( use_color )); then
        printf '%s%d%s symlink(s)' "$C_LINK" "$count" "$C_RESET" >&2
        (( broken > 0 )) && printf ', %s%d broken%s' "$C_BROKEN" "$broken" "$C_RESET" >&2
        printf '\n' >&2
    else
        printf '%d symlink(s)' "$count" >&2
        (( broken > 0 )) && printf ', %d broken' "$broken" >&2
        printf '\n' >&2
    fi
}

# ===== get_git_large_files: 审计当前 Git 仓库历史中的大文件 =====
# 用法: get_git_large_files
# 范围: 当前仓库所有 ref 可达提交中的文件版本（含已删除文件）
# 着色: (1, 5] MiB 蓝色；(5, 10] MiB 黄色；> 10 MiB 红色
# GET_GIT_LARGE_FILES_COLOR=auto|always|never，默认 auto
get_git_large_files() (
    local temp_dir=''
    trap '[[ -z "${temp_dir:-}" ]] || rm -rf -- "$temp_dir"' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM

    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        printf 'get_git_large_files: 当前目录不在 Git 仓库中\n' >&2
        return 1
    fi

    local repo_root
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null) ||
        repo_root=$(git rev-parse --git-dir 2>/dev/null)

    local use_color=0 color_mode=${GET_GIT_LARGE_FILES_COLOR:-auto}
    case "$color_mode" in
        always) use_color=1 ;;
        never)  use_color=0 ;;
        auto)   [[ -t 1 ]] && use_color=1 ;;
        *)
            printf 'get_git_large_files: 未知颜色模式 %s（应为 auto/always/never）\n' \
                "$color_mode" >&2
            return 1
            ;;
    esac
    [[ -z "${NO_COLOR:-}" || "$color_mode" == always ]] || use_color=0

    if [[ -z "$(git for-each-ref --format='%(objectname)' refs 2>/dev/null | head -n 1)" ]]; then
        printf 'Git 仓库: %s\n' "$repo_root"
        printf '未发现历史大文件：仓库中没有可用 ref 或提交。\n'
        return 0
    fi

    temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/configure-git-large-files.XXXXXX") || {
        printf 'get_git_large_files: 无法创建临时目录\n' >&2
        return 1
    }
    local history_file=$temp_dir/history.bin
    local occurrences_file=$temp_dir/occurrences.tsv
    local unique_file=$temp_dir/occurrences-unique.tsv
    local objects_file=$temp_dir/objects.tsv
    local sized_file=$temp_dir/sized.tsv
    local sorted_file=$temp_dir/sorted.tsv

    if ! LC_ALL=C git log --all --raw --root -m --no-renames --no-abbrev -z \
        --format='C%H%x00' >"$history_file"; then
        printf 'get_git_large_files: 读取 Git 历史失败\n' >&2
        return 1
    fi

    local current_commit='' token file_path meta
    local old_mode new_mode old_oid new_oid change_status
    while IFS= read -r -d '' token; do
        token=${token#$'\n'}
        case "$token" in
            C*)
                current_commit=${token#C}
                ;;
            :*)
                IFS= read -r -d '' file_path || break
                meta=${token#:}
                read -r old_mode new_mode old_oid new_oid change_status <<<"$meta"
                [[ -n "$new_oid" && "$new_oid" == *[!0]* ]] || continue
                printf '%s\t%s\t%s\n' "$new_oid" "$current_commit" "$file_path"
                ;;
        esac
    done <"$history_file" >"$occurrences_file"

    if ! LC_ALL=C sort -u "$occurrences_file" >"$unique_file"; then
        printf 'get_git_large_files: 去重历史文件版本失败\n' >&2
        return 1
    fi

    local cat_format=$'%(objectname)\t%(objecttype)\t%(objectsize)\t%(rest)'
    if ! git cat-file --batch-check="$cat_format" <"$unique_file" >"$objects_file"; then
        printf 'get_git_large_files: 读取 Git 对象信息失败\n' >&2
        return 1
    fi

    local one_mib=1048576 five_mib=5242880 ten_mib=10485760
    local oid object_type object_size rest commit
    while IFS=$'\t' read -r oid object_type object_size rest; do
        [[ "$object_type" == blob ]] || continue
        (( object_size > one_mib )) || continue
        commit=${rest%%$'\t'*}
        file_path=${rest#*$'\t'}
        printf '%s\t%s\t%s\t%s\n' "$file_path" "$oid" "$object_size" "$commit"
    done <"$objects_file" >"$sized_file"

    if ! LC_ALL=C sort -u -t $'\t' -k1,1 -k3,3nr -k4,4 \
        "$sized_file" >"$sorted_file"; then
        printf 'get_git_large_files: 排序历史文件版本失败\n' >&2
        return 1
    fi

    local C_BLUE='' C_YELLOW='' C_RED='' C_RESET=''
    if (( use_color )); then
        C_BLUE=$'\033[34m'
        C_YELLOW=$'\033[33m'
        C_RED=$'\033[31m'
        C_RESET=$'\033[0m'
    fi

    printf 'Git 仓库: %s\n' "$repo_root"
    printf '历史大文件（1 MiB = 1048576 字节）\n'
    printf '大小标记: >1–5 MiB 蓝色 | >5–10 MiB 黄色 | >10 MiB 红色\n'

    local branch_names tag_names filename human_size
    local size_color='' count=0
    while IFS=$'\t' read -r file_path oid object_size commit; do
        branch_names=$(LC_ALL=C git for-each-ref --contains "$commit" \
            --format='%(refname:short)' refs/heads refs/remotes 2>/dev/null |
            awk '$0 !~ /\/HEAD$/ { printf "%s%s", separator, $0; separator="," }')
        tag_names=$(LC_ALL=C git tag --contains "$commit" 2>/dev/null |
            awk '{ printf "%s%s", separator, $0; separator="," }')
        [[ -n "$branch_names" ]] || branch_names='-'
        [[ -n "$tag_names" ]] || tag_names='-'

        filename=${file_path##*/}
        human_size=$(printf '%d.%02d MiB (%d bytes)' \
            "$((object_size / one_mib))" \
            "$(((object_size % one_mib) * 100 / one_mib))" \
            "$object_size")

        size_color=$C_RED
        (( object_size > ten_mib )) || {
            size_color=$C_YELLOW
            (( object_size > five_mib )) || size_color=$C_BLUE
        }

        printf '分支=[%s] 标签=[%s] 提交=[%s] 路径=[%s] 文件名=[%s] 大小=[%s%s%s] 哈希=[%s]\n' \
            "$branch_names" "$tag_names" "$commit" "$file_path" "$filename" \
            "$size_color" "$human_size" "$C_RESET" "$oid"
        count=$((count + 1))
    done <"$sorted_file"

    if (( count == 0 )); then
        printf '未发现大于 1 MiB 的历史文件版本。\n'
    else
        printf '共 %d 个历史大文件版本（> 1 MiB）。\n' "$count"
    fi
)

# ===== git_diff_tree: 树形查看最近四层 diff（每层配色 + 行数）=====
# 用法: gdtree                 四层 = HEAD~3..HEAD~2 / HEAD~2..HEAD~1 / HEAD~1..HEAD / 本地..HEAD
#       gdtree <git diff 参数>  带参数时退化为单层，参数原样传给 git diff（如 --cached、HEAD~5 HEAD）
# 配色: 层1 青 / 层2 天蓝 / 层3 深蓝 / 层4 红；GIT_DIFF_TREE_COLOR=auto|always|never
git_diff_tree() {
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        printf 'git_diff_tree: 当前目录不在 Git 仓库中\n' >&2
        return 1
    fi

    local color_mode=${GIT_DIFF_TREE_COLOR:-auto}
    local use_color=0
    case "$color_mode" in
        always) use_color=1 ;;
        never)  use_color=0 ;;
        auto)   [[ -t 1 ]] && use_color=1 ;;
        *)
            printf 'git_diff_tree: 未知颜色模式 %s（应为 auto/always/never）\n' "$color_mode" >&2
            return 1
            ;;
    esac
    [[ -z "${NO_COLOR:-}" || "$color_mode" == always ]] || use_color=0

    local c1='' c2='' c3='' c4='' c_dim='' c_rst=''
    if (( use_color )); then
        local color_count=8
        color_count=$(tput colors 2>/dev/null) || color_count=8
        c1=$'\033[36m'
        c3=$'\033[34m'
        c4=$'\033[31m'
        c_rst=$'\033[0m'
        if [[ "$color_count" =~ ^[0-9]+$ ]] && (( color_count >= 256 )); then
            c2=$'\033[38;5;117m'
            c_dim=$'\033[38;5;240m'
        else
            c2=$'\033[96m'
            c_dim=$'\033[90m'
        fi
    fi

    local layer_count labels
    if (( $# == 0 )); then
        layer_count=4
        labels='HEAD~3→HEAD~2|HEAD~2→HEAD~1|HEAD~1→HEAD|本地→HEAD'
    else
        layer_count=1
        labels="diff $*"
    fi

    local awk_bin=awk
    if command -v gawk >/dev/null 2>&1; then
        awk_bin=gawk
    fi

    {
        if (( layer_count == 4 )); then
            if git rev-parse -q --verify 'HEAD~3^{commit}' >/dev/null 2>&1; then
                git diff --numstat HEAD~3 HEAD~2 | awk -F'\t' -v layer=1 'BEGIN{OFS="\t"}{print layer,$1,$2,$3}'
            else
                printf 'git_diff_tree: 历史不足 4 个提交，较早层置空\n' >&2
            fi
            if git rev-parse -q --verify 'HEAD~2^{commit}' >/dev/null 2>&1; then
                git diff --numstat HEAD~2 HEAD~1 | awk -F'\t' -v layer=2 'BEGIN{OFS="\t"}{print layer,$1,$2,$3}'
            fi
            if git rev-parse -q --verify 'HEAD~1^{commit}' >/dev/null 2>&1; then
                git diff --numstat HEAD~1 HEAD | awk -F'\t' -v layer=3 'BEGIN{OFS="\t"}{print layer,$1,$2,$3}'
            fi
            if git rev-parse -q --verify 'HEAD^{commit}' >/dev/null 2>&1; then
                git diff --numstat HEAD | awk -F'\t' -v layer=4 'BEGIN{OFS="\t"}{print layer,$1,$2,$3}'
            fi
        else
            git diff --numstat "$@" | awk -F'\t' -v layer=1 'BEGIN{OFS="\t"}{print layer,$1,$2,$3}'
        fi
    } | "$awk_bin" -F'\t' -v NL="$layer_count" -v LBLS="$labels" \
        -v C1="$c1" -v C2="$c2" -v C3="$c3" -v C4="$c4" -v DIM="$c_dim" -v RST="$c_rst" '
    BEGIN{
        split(LBLS,labs,"|"); split("青色|天蓝|深蓝|红色",cnm,"|")
        col[1]=C1; col[2]=C2; col[3]=C3; col[4]=C4
    }
    {
        L=$1+0; a=$2; d=$3; p=$4
        if (a=="-") { a=0; d=0; bin[p]=1 }
        if (p ~ /=>/) {
            if (match(p,/\{[^}]*=>[^}]*\}/)) {
                t=substr(p,RSTART+1,RLENGTH-2); n=split(t,kv,"=>")
                gsub(/^ +| +$/,"",kv[1]); gsub(/^ +| +$/,"",kv[2])
                p=substr(p,1,RSTART-1) kv[2]
            } else { n=split(p,kv," => "); p=kv[n] }
        }
        a+=0; d+=0
        k=p SUBSEP L; add[k]+=a; del[k]+=d; has[k]=1
        n=split(p,pt,"/"); pref=""
        for (i=1;i<n;i++) {
            pref=(i==1)?pt[1]:pref "/" pt[i]
            dk=pref SUBSEP L; dadd[dk]+=a; ddel[dk]+=d
            node[pref]=1; isdir[pref]=1
        }
        node[p]=1; isf[p]=1
    }
    END{
        m=0; for (k in node) ord[++m]=k
        if (m==0) { printf "（最近 %d 层均无改动）\n", NL; exit }
        for (i=2;i<=m;i++){ v=ord[i]; j=i-1; while (j>=1 && ord[j]>v){ ord[j+1]=ord[j]; j-- } ord[j+1]=v }
        for (i=1;i<=m;i++){ p=ord[i]; n=split(p,pt,"/"); par=(n==1)?"":substr(p,1,length(p)-length(pt[n])-1); last[par]=p }
        maxw=0
        for (i=1;i<=m;i++){
            p=ord[i]; n=split(p,pt,"/"); ind=""; anc=""
            for (l=1;l<n;l++){ pa=anc; anc=(l==1)?pt[1]:anc "/" pt[l]; ind = ind ((last[pa]==anc)?"    ":"│   ") }
            par=(n==1)?"":substr(p,1,length(p)-length(pt[n])-1)
            lab[i]=ind ((last[par]==p)?"└── ":"├── ") pt[n]
            if (length(lab[i])>maxw) maxw=length(lab[i])
            for (L=1;L<=NL;L++){
                k=p SUBSEP L; s=""
                if (isf[p]) { if (k in has) s=(bin[p]?"bin":sprintf("+%d -%d",add[k],del[k])) }
                else { dk=p SUBSEP L; if (dk in dadd) s=sprintf("+%d -%d",dadd[dk],ddel[dk]) }
                if (s=="") s="·"
                seg[i,L]=s
                if (length(s)>cw[L]) cw[L]=length(s)
            }
        }
        if (NL==1) { print "色标: " col[1] labs[1] RST }
        else {
            leg="色标:"
            for (L=1;L<=NL;L++){ if (L>1) leg = leg " " DIM "|" RST; leg = leg " " col[L] cnm[L] " " labs[L] RST }
            print leg
        }
        print ""
        for (i=1;i<=m;i++){
            line=sprintf("%-*s",maxw+2,lab[i])
            for (L=1;L<=NL;L++){
                s=seg[i,L]; cc=(s=="·")?DIM:col[L]
                line = line cc s sprintf("%*s",cw[L]-length(s)+1,"") RST
            }
            print line
        }
    }'
}
alias gdtree='git_diff_tree'

if [ "${_CONFIGURE_ENV_PROBE:-}" = "${_configure_env_self}" ]; then
    printf '%s\n' '@@CONFIGURE_ENV_ALIASES@@'
    if [ -n "${ZSH_VERSION:-}" ]; then
        printf '%s\n' ${(ok)aliases}
    else
        compgen -a 2>/dev/null | sort
    fi
    printf '%s\n' '@@CONFIGURE_ENV_FUNCTIONS@@'
    if [ -n "${ZSH_VERSION:-}" ]; then
        printf '%s\n' ${(ok)functions}
    else
        compgen -A function 2>/dev/null | sort
    fi
    unset _configure_env_self _configure_env_root
    return 0
fi

unset _configure_env_self _configure_env_root
