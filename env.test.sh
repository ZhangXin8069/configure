#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file=$script_dir/env.sh
test_root=$(mktemp -d "${TMPDIR:-/tmp}/configure-env-test.XXXXXX")

_cleanup() {
    rm -rf -- "$test_root"
}
trap _cleanup EXIT HUP INT TERM

_fail() {
    printf '失败：%s\n' "$*" >&2
    exit 1
}

_assert_line() {
    local output=$1
    local expected=$2

    grep -Fqx -- "$expected" <<<"$output" ||
        _fail "输出缺少行：$expected"
}

_assert_contains() {
    local output=$1
    local expected=$2

    [[ $output == *"$expected"* ]] || _fail "输出缺少内容：$expected"
}

_clean_env_shell() {
    local shell_path=$1
    local path_value=$2
    shift 2
    local -a shell_flags=()

    case "${shell_path##*/}" in
        zsh) shell_flags=(-f) ;;
        *) shell_flags=(--noprofile --norc) ;;
    esac

    command env -i \
        HOME="$test_root/home" USER=configure-test LOGNAME=configure-test \
        SHELL="$shell_path" TERM=dumb LANG=C.UTF-8 PATH="$path_value" \
        "$shell_path" "${shell_flags[@]}" "$@"
}

_run_case() {
    local shell_path=$1
    local fixture=$2
    local fake_bin=${3:-}
    local stdout_file=$test_root/stdout.txt
    local stderr_file=$test_root/stderr.txt
    local status

    set +e
    "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        [[ -z "$2" ]] || PATH="$2:$PATH"
        get_soft_links "$3"
    ' configure-env-test "$env_file" "$fake_bin" "$fixture" \
        >"$stdout_file" 2>"$stderr_file"
    status=$?
    set -e

    (( status == 0 )) || _fail "$shell_path 返回状态码 $status"
    cat "$stdout_file"
    cat "$stderr_file" >&2
}

_check_output() {
    local shell_path=$1
    local output=$2
    local fixture=$3

    _assert_line "$output" "$fixture/valid link -> target file.txt"
    _assert_line "$output" "$fixture/.hidden link -> target file.txt"
    _assert_line "$output" "$fixture/nested/nested link -> ../target file.txt"
    _assert_line "$output" "$fixture/dir link -> dir target"
    _assert_line "$output" "$fixture/broken link -> missing target [broken]"

    if grep -Fq -- ' -> ?' <<<"$output"; then
        _fail "$shell_path 丢失了一个或多个链接目标"
    fi
    if grep -Fq -- '/.git/' <<<"$output" || grep -Fq -- '/node_modules/' <<<"$output"; then
        _fail "$shell_path 遍历了应排除的目录"
    fi
    if [[ $output == *$'\033'* ]]; then
        _fail "$shell_path 在非 TTY 输出中包含颜色控制符"
    fi
}

_create_mib_file() {
    local file=$1
    local mib=$2
    local extra_byte=${3:-0}

    dd if=/dev/zero of="$file" bs=1048576 count="$mib" 2>/dev/null
    (( extra_byte == 0 )) || printf 'x' >>"$file"
}

_create_large_files_repo() {
    local repo=$1

    mkdir -p "$repo/nested"
    git -C "$repo" init -q -b main
    git -C "$repo" config user.name 'configure test'
    git -C "$repo" config user.email 'configure-test@example.invalid'

    _create_mib_file "$repo/small-at-threshold.bin" 1
    _create_mib_file "$repo/nested/blue one plus.bin" 1 1
    _create_mib_file "$repo/nested/blue five exact.bin" 5
    _create_mib_file "$repo/nested/yellow five plus.bin" 5 1
    _create_mib_file "$repo/nested/yellow ten exact.bin" 10
    _create_mib_file "$repo/nested/red ten plus one.bin" 10 1
    _create_mib_file "$repo/nested/duplicate-a.bin" 2
    _create_mib_file "$repo/nested/duplicate-b.bin" 2

    git -C "$repo" add -- \
        small-at-threshold.bin \
        'nested/blue one plus.bin' \
        'nested/blue five exact.bin' \
        'nested/yellow five plus.bin' \
        'nested/yellow ten exact.bin' \
        'nested/red ten plus one.bin' \
        'nested/duplicate-a.bin' \
        'nested/duplicate-b.bin'
    git -C "$repo" commit -q -m 'add large file fixtures'
    git -C "$repo" branch audit-branch
    git -C "$repo" tag -a audit-tag -m 'large file audit fixture'

    git -C "$repo" rm -q -- 'nested/red ten plus one.bin'
    git -C "$repo" commit -q -m 'delete history-only large file'
}

_run_git_large_files_case() {
    local shell_path=$1
    local repo=$2
    local color_mode=$3
    local stdout_file=$test_root/git-large-files.out
    local stderr_file=$test_root/git-large-files.err
    local status

    set +e
    "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        GET_GIT_LARGE_FILES_COLOR=$3
        export GET_GIT_LARGE_FILES_COLOR
        get_git_large_files
    ' configure-env-test "$env_file" "$repo" "$color_mode" \
        >"$stdout_file" 2>"$stderr_file"
    status=$?
    set -e

    (( status == 0 )) || _fail "$shell_path 的 get_git_large_files 返回 $status"
    cat "$stdout_file"
    cat "$stderr_file" >&2
}

_check_git_large_files_output() {
    local shell_path=$1
    local repo=$2
    local output=$3
    local color_mode=$4
    local base_commit red_oid red_row duplicate_oid duplicate_a_row duplicate_b_row

    base_commit=$(git -C "$repo" rev-parse 'audit-tag^{commit}')
    red_oid=$(git -C "$repo" rev-parse "$base_commit:nested/red ten plus one.bin")
    duplicate_oid=$(git -C "$repo" rev-parse "$base_commit:nested/duplicate-a.bin")
    red_row=$(grep -F '路径=[nested/red ten plus one.bin]' <<<"$output")
    duplicate_a_row=$(grep -F '路径=[nested/duplicate-a.bin]' <<<"$output")
    duplicate_b_row=$(grep -F '路径=[nested/duplicate-b.bin]' <<<"$output")

    [[ -n "$red_row" ]] || _fail "$shell_path 未输出已从当前分支删除的历史大文件"
    _assert_contains "$red_row" '分支=[audit-branch,main]'
    _assert_contains "$red_row" '标签=[audit-tag]'
    _assert_contains "$red_row" "提交=[$base_commit]"
    _assert_contains "$red_row" '文件名=[red ten plus one.bin]'
    _assert_contains "$red_row" '10.00 MiB (10485761 bytes)'
    _assert_contains "$red_row" "哈希=[$red_oid]"
    _assert_contains "$duplicate_a_row" "哈希=[$duplicate_oid]"
    _assert_contains "$duplicate_b_row" "哈希=[$duplicate_oid]"
    _assert_contains "$output" '共 7 个历史大文件版本（> 1 MiB）。'

    if grep -Fq '路径=[small-at-threshold.bin]' <<<"$output"; then
        _fail "$shell_path 错误包含了恰好 1 MiB 的文件"
    fi
    if [[ "$color_mode" == always ]]; then
        _assert_contains "$(grep -F '路径=[nested/blue one plus.bin]' <<<"$output")" \
            $'\033[34m1.00 MiB (1048577 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/blue five exact.bin]' <<<"$output")" \
            $'\033[34m5.00 MiB (5242880 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/yellow five plus.bin]' <<<"$output")" \
            $'\033[33m5.00 MiB (5242881 bytes)\033[0m'
        _assert_contains "$(grep -F '路径=[nested/yellow ten exact.bin]' <<<"$output")" \
            $'\033[33m10.00 MiB (10485760 bytes)\033[0m'
        _assert_contains "$red_row" $'\033[31m10.00 MiB (10485761 bytes)\033[0m'
    else
        if [[ $output == *$'\033'* ]]; then
            _fail "$shell_path 在 never 颜色模式下仍输出 ANSI 控制符"
        fi
    fi
}

_check_git_large_files_edge_cases() {
    local shell_path=$1
    local empty_repo=$2
    local non_repo=$3
    local output
    local status

    set +e
    output=$(GIT_CEILING_DIRECTORIES="$test_root" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        get_git_large_files
    ' configure-env-test "$env_file" "$empty_repo" 2>&1)
    status=$?
    set -e
    (( status == 0 )) || _fail "$shell_path 在空仓库中应返回 0，实际为 $status"
    _assert_contains "$output" '仓库中没有可用 ref 或提交'

    set +e
    output=$(GIT_CEILING_DIRECTORIES="$test_root" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        cd "$2" || exit 1
        get_git_large_files
    ' configure-env-test "$env_file" "$non_repo" 2>&1)
    status=$?
    set -e
    (( status == 1 )) || _fail "$shell_path 在非 Git 目录中应返回 1，实际为 $status"
    _assert_contains "$output" '当前目录不在 Git 仓库中'
}

_check_screen_helpers() {
    local shell_path=$1
    local fake_screen=$2
    local output
    local status
    local -a alias_flags=()

    case "${shell_path##*/}" in
        bash) alias_flags=(-O expand_aliases) ;;
    esac

    output=$("$shell_path" -c '
        source "$1" >/dev/null 2>&1
        alias scn
        alias scl
        alias scr
        alias scw
    ' configure-env-test "$env_file")
    _assert_contains "$output" 'scn'
    _assert_contains "$output" '_screen_new'
    _assert_contains "$output" 'scl'
    _assert_contains "$output" '_screen_list'
    _assert_contains "$output" 'scr'
    _assert_contains "$output" '_screen_resume'
    _assert_contains "$output" 'scw'
    _assert_contains "$output" 'screen -wipe'

    output=$(PATH="${fake_screen%/*}:$PATH" "$shell_path" "${alias_flags[@]}" -c '
        source "$1" >/dev/null 2>&1
        eval scw
    ' configure-env-test "$env_file")
    _assert_line "$output" '-wipe'

    output=$(SCREEN_BIN="$fake_screen" SSH_CLIENT='' SSH_SCREEN_NAME='' \
        SCREEN_TERM=screen-256color \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            _screen_new explicit-name
        ' configure-env-test "$env_file")
    _assert_contains "$output" '-U -T screen-256color -t explicit-name -S explicit-name sh -c '

    output=$(SCREEN_BIN="$fake_screen" SSH_CLIENT='203.0.113.9 5555 22' SSH_SCREEN_NAME='' \
        SCREEN_TERM=screen-256color \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            _screen_new
        ' configure-env-test "$env_file")
    _assert_contains "$output" '-U -T screen-256color -t 203.0.113.9 -S 203.0.113.9 sh -c '

    : > "$test_root/screen-resume.log"
    output=$(SCREEN_BIN="$fake_screen" SSH_CLIENT='' SSH_SCREEN_NAME='manual-name' \
        SCREEN_FAKE_LOG="$test_root/screen-resume.log" \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            _screen_resume
        ' configure-env-test "$env_file")
    _assert_contains "$(command cat "$test_root/screen-resume.log")" '-S manual-name -X encoding utf8'
    _assert_line "$output" '-t manual-name -dr manual-name'

    output=$(SCREEN_BIN="$fake_screen" \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            _screen_list
        ' configure-env-test "$env_file")
    _assert_line "$output" '-ls'

    set +e
    output=$(SCREEN_BIN="$test_root/missing-screen" \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            _SCREEN_GUIDE_PATH="$2"
            _screen_list
        ' configure-env-test "$env_file" "$test_root/missing-screen-guide.txt" 2>&1)
    status=$?
    set -e
    (( status == 127 )) || _fail "$shell_path 在 screen 缺失时应返回 127，实际为 $status"
    _assert_contains "$output" 'Debian/Ubuntu: sudo apt update && sudo apt install screen'
    _assert_contains "$output" 'RHEL/CentOS/Fedora: sudo dnf install screen'
    _assert_contains "$output" 'Arch/Manjaro: sudo pacman -S screen'
    _assert_contains "$output" 'openSUSE: sudo zypper install screen'
    _assert_contains "$output" 'Alpine: sudo apk add screen'
    _assert_contains "$output" 'FreeBSD: sudo pkg install screen'
    _assert_contains "$output" 'macOS: brew install screen'
    _assert_contains "$output" 'Ctrl+a d'
    _assert_contains "$output" 'screen -dr <名字>'

    output=$(STY=12345.test SCREEN_TERM=screen-256color TERM=screen \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            printf "%s\n" "$TERM"
        ' configure-env-test "$env_file")
    _assert_line "$output" 'screen-256color'

    output=$(STY='' SCREEN_TERM=screen-256color TERM=screen \
        "$shell_path" -c '
            source "$1" >/dev/null 2>&1
            printf "%s\n" "$TERM"
        ' configure-env-test "$env_file")
    _assert_line "$output" 'screen'
}

_create_fake_conda() {
    local root=$1

    mkdir -p "$root/etc/profile.d" "$root/bin" "$root/sbin" "$root/include" \
        "$root/lib/pkgconfig" "$root/lib/python3.12/site-packages" \
        "$root/share/man" "$root/share/aclocal" "$root/nvvm/bin" \
        "$root/include/ucp/api" "$root/include/hwloc" "$root/include/event2" \
        "$root/lib/pmix" "$root/include/hdf5" \
        "$root/targets/x86_64-linux/include" "$root/targets/x86_64-linux/lib/stubs"
    : >"$root/include/hdf5.h"
    : >"$root/include/ncurses.h"
    : >"$root/include/hwloc.h"
    : >"$root/include/ucp/api/ucp.h"
    : >"$root/include/event2/event.h"
    for exe in cc c++ cpp gcc g++ gfortran nvcc mpicc mpicxx mpif77 mpif90 mpifort \
        x86_64-conda-linux-gnu-cc x86_64-conda-linux-gnu-c++ \
        x86_64-conda-linux-gnu-cpp x86_64-conda-linux-gnu-gfortran cmake; do
        printf '#!/bin/sh\nexit 0\n' >"$root/bin/$exe"
        chmod +x "$root/bin/$exe"
    done
    printf '#!/bin/sh\nexit 0\n' >"$root/nvvm/bin/cicc"
    chmod +x "$root/nvvm/bin/cicc"
    {
        printf '%s\n' \
            '# 测试用最小 conda 壳：只支持 activate base / deactivate' \
            'conda() {' \
            '    case "${1:-}" in' \
            '        activate)' \
            '            if [ "${FAKE_CONDA_ACTIVATE:-}" = fail ]; then' \
            '                printf "fake conda: activate 失败\n" >&2' \
            '                return 1' \
            '            fi' \
            '            CONDA_DEFAULT_ENV=${2:-base}' \
            "            CONDA_PREFIX='${root}'" \
            '            export CONDA_DEFAULT_ENV CONDA_PREFIX' \
            '            ;;' \
            '        deactivate)' \
            '            unset CONDA_DEFAULT_ENV CONDA_PREFIX' \
            '            ;;' \
            '        *)' \
            '            printf "fake conda: 不支持 %s\n" "${1:-}" >&2' \
            '            return 2' \
            '            ;;' \
            '    esac' \
            '}'
    } >"$root/etc/profile.d/conda.sh"
}

_check_zda_alias() {
    local shell_path=$1
    local fake_home=$2
    local fake_root=$fake_home/miniforge3
    local output
    local status

    output=$("$shell_path" -c '
        source "$1" >/dev/null 2>&1
        alias zda
        type _zda_activate_base >/dev/null 2>&1 || exit 1
    ' configure-env-test "$env_file")
    _assert_contains "$output" 'zda'
    _assert_contains "$output" '_zda_activate_base'

    # 首次调用激活 fake base，并写入预期的 CONDA_PREFIX / CONDA_DEFAULT_ENV
    output=$(HOME="$fake_home" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base
        printf "prefix=%s default=%s\n" "$CONDA_PREFIX" "$CONDA_DEFAULT_ENV"
    ' configure-env-test "$env_file" 2>"$test_root/zda-activate.err")
    _assert_contains "$output" "prefix=$fake_root default=base"
    _assert_contains "$output" 'zda: 已激活'

    # 路径变量同步：base 的 bin/include/lib 前置，且旧值保留在后面
    output=$(HOME="$fake_home" "$shell_path" -c '
        unset LD_LIBRARY_PATH LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH \
              PYTHONPATH PKG_CONFIG_PATH CMAKE_PREFIX_PATH MANPATH ACLOCAL_PATH
        export CPATH=/opt/legacy/include PYTHONPATH=/opt/legacy/py
        source "$1" >/dev/null 2>&1
        _zda_activate_base >/dev/null 2>&1
        for v in PATH LD_LIBRARY_PATH LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH \
                 C_INCLUDE_PATH PYTHONPATH PKG_CONFIG_PATH CMAKE_PREFIX_PATH \
                 MANPATH ACLOCAL_PATH \
                 CUDA_PATH CUDA_HOME CUDA_ROOT CUDAToolkit_ROOT CUDA_INCLUDE_PATH \
                 CUDA_LIBRARY_PATH CUDACXX \
                 MPI_HOME OPENMPI_ROOT OPAL_PREFIX MPICC MPICXX MPIF77 MPIF90 MPIFORT \
                 MPI_INCLUDE_PATH MPI_LIBRARY_PATH OMPI_CC OMPI_CXX OMPI_FC \
                 OMPI_ALLOW_RUN_AS_ROOT OMPI_ALLOW_RUN_AS_ROOT_CONFIRM MPI_ALLOW_RUN_AS_ROOT \
                 HDF5_DIR HDF5_ROOT HDF5_INCLUDE_PATH HDF5_LIBRARY_PATH HDF5_MPI \
                 CC CXX CPP FC F77 GCC_ROOT NCURSES_ROOT PYTHON_ROOT HWLOC_ROOT \
                 UCX_ROOT PMIX_ROOT LIBEVENT_ROOT; do
            eval "printf \"%s=%s\\n\" \"$v\" \"\${$v-<unset>}\""
        done
    ' configure-env-test "$env_file" 2>/dev/null)

    local var val
    for var in LD_LIBRARY_PATH LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH \
               C_INCLUDE_PATH PYTHONPATH PKG_CONFIG_PATH MANPATH ACLOCAL_PATH; do
        val=$(printf '%s\n' "$output" | sed -n "s/^${var}=//p")
        [[ -n "$val" ]] || _fail "$shell_path 的 zda 未设置 $var"
        [[ "$val" == "$fake_root"* ]] ||
            _fail "$shell_path 的 $var 未把 conda 路径前置：$val"
    done

    # 声明清单里的每个变量都必须真的被设置（防止声明与实现漂移）
    local declared
    for declared in $(sed -n '/^# zda 注入的环境变量声明/,/^# 规则/p' "$env_file" |
        grep -oE '\b(CUDA|MPI|OMPI|HDF5)_[A-Z_]+|\b(CC|CXX|CPP|FC|F77|GCC_ROOT|NCURSES_ROOT|PYTHON_ROOT|HWLOC_ROOT|UCX_ROOT|PMIX_ROOT|LIBEVENT_ROOT|CUDACXX)\b' |
        sort -u); do
        case "$declared" in
        CMAKE_ROOT) continue ;;
        esac
        printf '%s\n' "$output" | grep -q "^${declared}=" ||
            _fail "$shell_path 的 zda 未设置声明中的 $declared"
    done
    # 具体目录映射（前缀匹配：env.sh 自身还会追加仓库 lib 等路径）
    _assert_contains "$output" "LD_LIBRARY_PATH=$fake_root/lib:$fake_root/targets/x86_64-linux/lib"
    _assert_contains "$output" "LIBRARY_PATH=$fake_root/lib:$fake_root/targets/x86_64-linux/lib"
    _assert_line "$output" "CPATH=$fake_root/include:$fake_root/targets/x86_64-linux/include:/opt/legacy/include"
    _assert_line "$output" "CPLUS_INCLUDE_PATH=$fake_root/include:$fake_root/targets/x86_64-linux/include"
    _assert_line "$output" "C_INCLUDE_PATH=$fake_root/include:$fake_root/targets/x86_64-linux/include"
    _assert_line "$output" "PYTHONPATH=$fake_root/lib/python3.12/site-packages:/opt/legacy/py"
    _assert_line "$output" "PKG_CONFIG_PATH=$fake_root/lib/pkgconfig"
    _assert_line "$output" "CMAKE_PREFIX_PATH=$fake_root"
    _assert_line "$output" "MANPATH=$fake_root/share/man"
    _assert_line "$output" "ACLOCAL_PATH=$fake_root/share/aclocal"
    _assert_line "$output" "CUDA_PATH=$fake_root/targets/x86_64-linux"
    _assert_line "$output" "CUDA_HOME=$fake_root/targets/x86_64-linux"
    _assert_line "$output" "CUDA_ROOT=$fake_root/targets/x86_64-linux"
    _assert_line "$output" "CUDAToolkit_ROOT=$fake_root/targets/x86_64-linux"
    _assert_line "$output" "CUDA_INCLUDE_PATH=$fake_root/targets/x86_64-linux/include"
    _assert_contains "$output" "CUDA_LIBRARY_PATH=$fake_root/targets/x86_64-linux/lib:$fake_root/targets/x86_64-linux/lib/stubs"
    _assert_line "$output" "CUDACXX=$fake_root/bin/nvcc"
    _assert_line "$output" "HDF5_DIR=$fake_root"
    _assert_line "$output" "HDF5_MPI=ON"

    # 旧值不被丢弃，只降序
    _assert_contains "$(printf '%s\n' "$output" | sed -n 's/^PATH=//p')" ':/usr/bin'

    # 重复同步不产生重复项
    output=$(HOME="$fake_home" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base >/dev/null 2>&1
        _zda_activate_base >/dev/null 2>&1
        printf "%s\n" "$PYTHONPATH"
    ' configure-env-test "$env_file" 2>/dev/null)
    [[ "$output" == "$fake_root/lib/python3.12/site-packages" ]] ||
        _fail "$shell_path 的重复 zda 让 PYTHONPATH 出现重复：$output"

    # _ZDA_SKIP_LIBPATH=1 时不注入 conda 的 lib，其他变量照常
    output=$(HOME="$fake_home" _ZDA_SKIP_LIBPATH=1 "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base >/dev/null 2>&1
        printf "LD=%s\nLIB=%s\nCPATH=%s\n" \
            "${LD_LIBRARY_PATH-<unset>}" "${LIBRARY_PATH-<unset>}" "${CPATH-<unset>}"
    ' configure-env-test "$env_file" 2>/dev/null)
    if [[ "$output" == *"LD=$fake_root"* ]]; then
        _fail "$shell_path 在 _ZDA_SKIP_LIBPATH=1 时仍注入了 conda 的 LD_LIBRARY_PATH"
    fi
    _assert_line "$output" 'LIB=<unset>'
    _assert_contains "$output" "CPATH=$fake_root/include"

    # 与 base 冲突的 python/pip 别名应被移除，其他别名保留
    output=$("$shell_path" -c '
        shopt -s expand_aliases 2>/dev/null || setopt aliases 2>/dev/null || true
        source "$1" >/dev/null 2>&1
        alias python=python3
        alias pip=pip3
        alias py=python
        alias mytool=true
        eval zda >/dev/null 2>&1
        for n in python python3 pip pip3 py ipython; do
            alias "$n" >/dev/null 2>&1 && printf "kept:%s\n" "$n"
        done
        alias mytool >/dev/null 2>&1 && printf "mytool-kept\n"
    ' configure-env-test "$env_file" 2>&1)
    if [[ "$output" == *kept:* ]]; then
        _fail "$shell_path 的 zda 未移除冲突别名：$output"
    fi
    _assert_contains "$output" 'mytool-kept'

    # 重复调用幂等，不重复激活
    output=$(HOME="$fake_home" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base >/dev/null 2>&1
        _zda_activate_base
    ' configure-env-test "$env_file" 2>&1)
    _assert_contains "$output" 'zda: 已处于'

    # conda activate 失败时返回 1 且不中断调用方
    output=$(HOME="$fake_home" FAKE_CONDA_ACTIVATE=fail "$shell_path" -c '
        unset CONDA_PREFIX CONDA_DEFAULT_ENV
        source "$1" >/dev/null 2>&1
        _zda_activate_base
        printf "status=%s prefix=%s\n" "$?" "${CONDA_PREFIX:-<empty>}"
    ' configure-env-test "$env_file" 2>&1)
    _assert_contains "$output" 'conda activate base 执行失败'
    _assert_contains "$output" 'status=1 prefix=<empty>'

    # 环境缺失：打印安装/换源指南并返回 1
    output=$(HOME="$test_root/zda-empty-home" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base
        printf "status=%s\n" "$?"
    ' configure-env-test "$env_file" 2>&1)
    _assert_contains "$output" '未找到可用的 conda 环境'
    _assert_contains "$output" '安装 Miniforge'
    _assert_contains "$output" 'lib/_wsl/setup.md'
    _assert_contains "$output" 'status=1'

    # 指南文件缺失时明确报出路径，不静默失败
    output=$(HOME="$test_root/zda-empty-home" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _ZDA_GUIDE_PATH="$2"
        _zda_activate_base
        printf "status=%s\n" "$?"
    ' configure-env-test "$env_file" "$test_root/zda-missing-guide.txt" 2>&1)
    _assert_contains "$output" '环境配置指南缺失'
    _assert_contains "$output" 'status=1'

    # 有目录但缺 conda.sh（半装状态）同样走警告分支
    mkdir -p "$test_root/zda-partial/miniforge3"
    output=$(HOME="$test_root/zda-partial" "$shell_path" -c '
        source "$1" >/dev/null 2>&1
        _zda_activate_base
        printf "status=%s\n" "$?"
    ' configure-env-test "$env_file" 2>&1)
    _assert_contains "$output" 'status=1'

    # 指南文件本身必须存在且被 env.sh 指向
    [[ -s ${env_file%/*}/bin/_zda-guide.txt ]] || _fail '缺少 bin/_zda-guide.txt'
    grep -Fq '_ZDA_GUIDE_PATH="${_configure_env_root}/bin/_zda-guide.txt"' "$env_file" ||
        _fail 'env.sh 未把 _ZDA_GUIDE_PATH 指向 bin/_zda-guide.txt'
    [[ -s $fake_root/etc/profile.d/conda.sh ]] || _fail '缺少 zda 测试用的假 conda.sh'
}

_check_locale_recovery() {
    local shell_path=$1
    local harness_stderr_file=$test_root/locale-harness.err
    local stderr_file=$test_root/locale-recovery.err
    local output

    output=$(_clean_env_shell "$shell_path" "/usr/bin:/bin" -c '
        export LC_ALL=C.utf8.configure-test-missing
        . "$1" 2>/dev/null
        [[ "$LC_ALL" != "C.utf8.configure-test-missing" ]] || exit 21
        [[ "$(locale charmap 2>/dev/null)" == "UTF-8" ]] || exit 22
        sh -c "locale charmap" 2>>"$2"
        printf "locale-recovered\n"
    ' configure-env-locale "$env_file" "$stderr_file" 2>"$harness_stderr_file") ||
        _fail "$shell_path 未修复失效的 LC_ALL，实际输出：$output；Harness 告警：$(<"$harness_stderr_file")；子 shell 告警：$(<"$stderr_file")"
    _assert_line "$output" 'UTF-8'
    _assert_line "$output" 'locale-recovered'
    [[ ! -s "$stderr_file" ]] ||
        _fail "$shell_path locale 修复后仍有告警：$(<"$stderr_file")"
}

_check_locale_category_recovery() {
    local shell_path=$1
    local harness_stderr_file=$test_root/locale-category-harness.err
    local stderr_file=$test_root/locale-category-recovery.err
    local output

    output=$(_clean_env_shell "$shell_path" "/usr/bin:/bin" -c '
        export LC_ALL=
        export LANG=
        export LC_CTYPE=C.utf8
        export LC_TIME=C.utf8.configure-test-missing
        . "$1" 2>/dev/null
        [[ -n "$LC_ALL" ]] || exit 31
        [[ "$(locale charmap 2>/dev/null)" == "UTF-8" ]] || exit 32
        sh -c "locale" >/dev/null 2>>"$2"
        printf "locale-category-recovered\n"
    ' configure-env-locale-category "$env_file" "$stderr_file" 2>"$harness_stderr_file") ||
        _fail "$shell_path 未修复部分失效的 locale 类别，实际输出：$output；Harness 告警：$(<"$harness_stderr_file")；子 shell 告警：$(<"$stderr_file")"
    _assert_line "$output" 'locale-category-recovered'
    [[ ! -s "$stderr_file" ]] ||
        _fail "$shell_path locale 类别修复后仍有告警：$(<"$stderr_file")"
}

_check_env_loading_guard() {
    local shell_path=$1
    local clean_bin=$2
    local conflict_bin=$3
    local stderr_file=$test_root/conflict-guard.err
    local output

    output=$(_clean_env_shell "$shell_path" "$clean_bin:/usr/bin:/bin" -c '
        . "$1" 2>"$2" || exit $?
        first_path=$PATH
        alias scn >/dev/null 2>&1 || exit 11
        alias scl >/dev/null 2>&1 || exit 12
        alias scr >/dev/null 2>&1 || exit 13
        type _screen_new >/dev/null 2>&1 || exit 14
        alias screen-new >/dev/null 2>&1 && exit 15
        alias screen-list >/dev/null 2>&1 && exit 16
        alias screen-resume >/dev/null 2>&1 && exit 17
        env | grep -Fq "_CONFIGURE_ENV_LOADED_PATH=" && exit 18
        . "$1" 2>>"$2" || exit $?
        [[ "$PATH" == "$first_path" ]] || exit 19
        printf "loaded\n"
    ' configure-env-clean "$env_file" "$stderr_file") ||
        _fail "$shell_path 无冲突时应加载 env.sh，实际输出：$output"
    _assert_line "$output" 'loaded'
    [[ ! -s "$stderr_file" ]] || _fail "$shell_path 无冲突加载产生告警：$(<"$stderr_file")"

    output=$(_clean_env_shell "$shell_path" "$conflict_bin:/usr/bin:/bin" -c '
        alias scn=false
        git_current_branch() { :; }
        _SCREEN_GUIDE_PATH=/tmp/foreign-screen-guide
        export _SCREEN_GUIDE_PATH
        before_path=$PATH
        . "$1" 2>"$2" || exit 31
        [[ "$PATH" != "$before_path" ]] || exit 32
        alias scn | grep -Fq _screen_new || exit 33
        type _screen_new >/dev/null 2>&1 || exit 34
        [[ "$_SCREEN_GUIDE_PATH" == "${1%/*}/bin/_screen-guide.txt" ]] || exit 35
        env | grep -Fq "_CONFIGURE_ENV_LOADED_PATH=" && exit 36
        printf "conflicts-ignored\n"
    ' configure-env-clean "$env_file" "$stderr_file") ||
        _fail "$shell_path 冲突告警暂停后未继续加载 env.sh，实际输出：$output"
    _assert_line "$output" 'conflicts-ignored'
    [[ ! -s "$stderr_file" ]] || _fail "$shell_path 冲突告警暂停后仍产生告警：$(<"$stderr_file")"

}

main() {
    local fixture=$test_root/fixtures/path\ with\ spaces
    local readlink_failure=$test_root/failing-readlink
    local ls_failure=$test_root/failing-ls
    local python_failure=$test_root/failing-python
    local false_path
    local shell_paths=()
    local -a fallback_bins=()
    local -a fallback_labels=()
    local shell_path
    local output
    local stderr_file
    local index
    local large_files_repo=$test_root/large-files-repo
    local empty_repo=$test_root/empty-repo
    local non_repo=$test_root/non-repo
    local large_files_output
    local fake_screen=$test_root/screen-bin/screen
    local clean_bin=$test_root/clean-bin
    local conflict_bin=$test_root/conflict-bin

    mkdir -p "$fixture/nested" "$fixture/dir target" \
        "$fixture/.git" "$fixture/node_modules" \
        "$readlink_failure" "$ls_failure" "$python_failure"
    printf 'target\n' >"$fixture/target file.txt"
    ln -s 'target file.txt' "$fixture/valid link"
    ln -s 'target file.txt' "$fixture/.hidden link"
    ln -s '../target file.txt' "$fixture/nested/nested link"
    ln -s 'dir target' "$fixture/dir link"
    ln -s 'missing target' "$fixture/broken link"
    ln -s 'missing target' "$fixture/.git/ignored link"
    ln -s 'missing target' "$fixture/node_modules/ignored link"

    false_path=$(command -v false) || _fail '缺少 false 命令'
    ln -s "$false_path" "$readlink_failure/readlink"
    ln -s "$false_path" "$ls_failure/readlink"
    ln -s "$false_path" "$ls_failure/ls"
    ln -s "$false_path" "$python_failure/readlink"
    ln -s "$false_path" "$python_failure/ls"
    ln -s "$false_path" "$python_failure/python3"

    fallback_bins=("$readlink_failure")
    fallback_labels=(ls)
    if command -v python3 >/dev/null 2>&1; then
        fallback_bins+=("$ls_failure")
        fallback_labels+=(python3)
    fi
    if command -v perl >/dev/null 2>&1; then
        fallback_bins+=("$python_failure")
        fallback_labels+=(perl)
    fi

    command -v bash >/dev/null 2>&1 && shell_paths+=("$(command -v bash)")
    command -v zsh >/dev/null 2>&1 && shell_paths+=("$(command -v zsh)")
    ((${#shell_paths[@]} > 0)) || _fail '需要 bash 或 zsh'

    _create_large_files_repo "$large_files_repo"
    mkdir -p "$empty_repo" "$non_repo"
    git -C "$empty_repo" init -q -b main
    mkdir -p "${fake_screen%/*}"
    mkdir -p "$test_root/home" "$clean_bin" "$conflict_bin"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'if [[ -n "${SCREEN_FAKE_LOG:-}" ]]; then printf "%s\\n" "$*" >> "$SCREEN_FAKE_LOG"; fi' \
        'printf "%s\\n" "$*"' >"$fake_screen"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$conflict_bin/cl"
    chmod +x "$fake_screen" "$conflict_bin/cl"

    _create_fake_conda "$test_root/home/miniforge3"
    mkdir -p "$test_root/zda-empty-home"
    local zda_home=$test_root/home

    for shell_path in "${shell_paths[@]}"; do
        _check_env_loading_guard "$shell_path" "$clean_bin" "$conflict_bin"
        printf '通过：%s 的重复 source、marker 撤销与冲突告警暂停加载\n' "$shell_path"

        _check_zda_alias "$shell_path" "$zda_home"
        printf '通过：%s 的 zda base 激活、幂等、失败与缺失指南\n' "$shell_path"

        _check_locale_recovery "$shell_path"
        printf '通过：%s 的失效 LC_ALL 自动恢复\n' "$shell_path"

        _check_locale_category_recovery "$shell_path"
        printf '通过：%s 的部分失效 locale 类别自动恢复\n' "$shell_path"

        _check_screen_helpers "$shell_path" "$fake_screen"
        printf '通过：%s 的 screen 别名、标题、重连与缺失降级\n' "$shell_path"

        output=$(_run_case "$shell_path" "$fixture") ||
            _fail "$shell_path 的原生读取器链失败"
        _check_output "$shell_path" "$output" "$fixture"

        for index in "${!fallback_bins[@]}"; do
            output=$(_run_case "$shell_path" "$fixture" "${fallback_bins[index]}") ||
                _fail "$shell_path 的 ${fallback_labels[index]} 回退失败"
            _check_output "$shell_path" "$output" "$fixture"
            stderr_file=$test_root/stderr.txt
            _assert_line "$(<"$stderr_file")" '5 symlink(s), 1 broken'
        done
        printf '通过：%s 使用以下读取器链解析目标：readlink %s\n' \
            "$shell_path" "${fallback_labels[*]}"

        large_files_output=$(_run_git_large_files_case "$shell_path" "$large_files_repo" never) ||
            _fail "$shell_path 无法审计 Git 历史大文件"
        _check_git_large_files_output "$shell_path" "$large_files_repo" \
            "$large_files_output" never

        large_files_output=$(_run_git_large_files_case "$shell_path" "$large_files_repo" always) ||
            _fail "$shell_path 无法输出 Git 历史大文件颜色"
        _check_git_large_files_output "$shell_path" "$large_files_repo" \
            "$large_files_output" always
        _check_git_large_files_edge_cases "$shell_path" "$empty_repo" "$non_repo"
        printf '通过：%s 的历史大文件审计、颜色边界与异常边界\n' "$shell_path"
    done
}

main "$@"
