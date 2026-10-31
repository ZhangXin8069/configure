
#!/bin/sh
#
# give_git_ignore.sh
#
# POSIX Shell implementation.
# Compatible with: sh / dash / ash / bash / zsh
#
# 主 .gitignore 生成策略:
#   1. 默认忽略所有文件。
#   2. 开放普通目录，允许 Git 递归遍历。
#   3. 保留工作区已有的无后缀文件（包括软链接）。
#   4. 放行工作区已有的文件后缀。
#   5. 忽略所有隐藏文件和隐藏目录。
#   6. 放行常用配置文件、配置目录和用户自定义规则。
#
# 子目录策略:
#   data/  : 仅保留 .gitignore、AGENTS.md、README.md
#   logs/  : 保留 .gitignore、AGENTS.md、README.md、所有 .txt
#   docs/  : 忽略所有子目录
#
# 用法:
#   give_git_ignore.sh [-f] [-n] [-o OUT] [-k PATTERN]...
#                      [--no-default-keep] [-sub]
#
#   -f, --force          直接覆盖，不备份
#   -n, --dry-run        只预览，不写入
#   -o, --output OUT     指定主 .gitignore 输出位置
#   -k, --keep PATTERN   添加保留规则，可重复
#   --no-default-keep    禁用默认保留清单
#   -sub, --sub-only     只生成子目录 .gitignore
#   -h, --help           显示帮助
#
# 注意:
#   POSIX Shell 本身无法无损处理包含换行符的文件名。
#   本脚本针对常规项目文件名工作。

set -eu

# ============================================================
# 初始化
# ============================================================

SCRIPT_NAME=${0##*/}

FORCE=0
DRY=0
OUT=""
NO_DEFAULT=0
SUB_ONLY=0

# 临时目录
TMP_BASE=${TMPDIR:-/tmp}
TMP_DIR="${TMP_BASE%/}/give_git_ignore.$$"

umask 077

if ! mkdir "$TMP_DIR" 2>/dev/null; then
    echo "Cannot create temporary directory: $TMP_DIR" >&2
    exit 1
fi

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup 0
trap 'exit 1' HUP INT TERM

# ============================================================
# 参数解析
# ============================================================

KEEP_ARGS="$TMP_DIR/keep_args"
: > "$KEEP_ARGS"

while [ "$#" -gt 0 ]; do
    case "$1" in
        -f|--force)
            FORCE=1
            shift
            ;;

        -n|--dry-run)
            DRY=1
            shift
            ;;

        -o|--output)
            if [ "$#" -lt 2 ]; then
                echo "Missing argument for $1" >&2
                exit 1
            fi
            OUT=$2
            shift 2
            ;;

        -k|--keep)
            if [ "$#" -lt 2 ]; then
                echo "Missing argument for $1" >&2
                exit 1
            fi
            printf '%s\n' "$2" >> "$KEEP_ARGS"
            shift 2
            ;;

        --no-default-keep)
            NO_DEFAULT=1
            shift
            ;;

        -sub|--sub-only)
            SUB_ONLY=1
            shift
            ;;

        -h|--help)
            sed -n '2,39p' "$0"
            exit 0
            ;;

        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# ============================================================
# 定位 Git 仓库
# ============================================================

if ! ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "Not inside a Git repository." >&2
    exit 1
fi

cd "$ROOT"

if [ -z "$OUT" ]; then
    OUT="$ROOT/.gitignore"
fi

if [ "$SUB_ONLY" -eq 0 ]; then
    OUT_DIR=$(dirname "$OUT")

    if [ ! -d "$OUT_DIR" ]; then
        echo "Output directory does not exist: $OUT_DIR" >&2
        exit 1
    fi
fi

# ============================================================
# 默认保留清单
# ============================================================

DEFAULT_KEEP="$TMP_DIR/default_keep"

cat > "$DEFAULT_KEEP" <<'EOF'
# Git
.git*
.gitattributes
.gitignore
.gitmodules

# Build
Makefile
makefile
GNUmakefile
Dockerfile
dockerfile
Containerfile

# Project documentation
LICENSE
LICENSE.*
COPYING
COPYING.*
NOTICE
NOTICE.*
README
README.*
AUTHORS
CONTRIBUTORS
CHANGELOG
CHANGELOG.*

# Editor and development tools
.editorconfig
.clang*
.env.example
.env.sample
.env.template
.env.dist
.keep
.gitkeep

# Common configuration directories
!.github/
!.github/**
EOF

# 这里的默认规则统一采用正向 Gitignore 白名单。
# 目录规则会在生成阶段转换成正确的否定规则。

# ============================================================
# Gitignore 字符转义
# ============================================================

escape_pattern() {
    printf '%s' "$1" |
        sed \
            -e 's/\\/\\\\/g' \
            -e 's/\*/\\*/g' \
            -e 's/?/\\?/g' \
            -e 's/\[/\\[/g'
}

# ============================================================
# 备份函数
# ============================================================

backup_existing() {
    file=$1

    timestamp=$(date '+%Y-%m-%d-%H-%M-%S')
    backup="${file}.${timestamp}.bak"
    index=1

    while [ -e "$backup" ] || [ -L "$backup" ]; do
        backup="${file}.${timestamp}-${index}.bak"
        index=$((index + 1))
    done

    mv -- "$file" "$backup"

    printf '%s\n' "$backup"
}

# ============================================================
# 通用子目录写入
# ============================================================

write_sub_ignore() {
    target=$1
    shift

    content_file="$TMP_DIR/sub_content"

    : > "$content_file"

    for line do
        printf '%s\n' "$line" >> "$content_file"
    done

    if [ -e "$target" ] || [ -L "$target" ]; then
        if [ "$FORCE" -eq 1 ]; then
            :

        elif [ "$DRY" -eq 1 ]; then
            echo "[dry-run] would back up: $target"

        else
            backup=$(backup_existing "$target")
            echo "backed up: $target -> $backup"
        fi
    fi

    if [ "$DRY" -eq 1 ]; then
        echo "--- $target (dry-run) ---"
        cat "$content_file"
        echo "--- end ---"
    else
        cat "$content_file" > "$target"
        echo "written: $target"
    fi
}

# ============================================================
# data/.gitignore
# ============================================================

apply_data_ignore() {
    if [ ! -d data ]; then
        echo "skip: data directory does not exist"
        return 0
    fi

    write_sub_ignore "data/.gitignore" \
        '*' \
        '!.gitignore' \
        '!AGENTS.md' \
        '!README.md'
}

# ============================================================
# logs/.gitignore
# ============================================================

apply_logs_ignore() {
    if [ ! -d logs ]; then
        echo "skip: logs directory does not exist"
        return 0
    fi

    write_sub_ignore "logs/.gitignore" \
        '*' \
        '*/' \
        '!.gitignore' \
        '!AGENTS.md' \
        '!README.md' \
        '!*.txt'
}

# ============================================================
# docs/.gitignore
# ============================================================

apply_docs_ignore() {
    if [ ! -d docs ]; then
        echo "skip: docs directory does not exist"
        return 0
    fi

    write_sub_ignore "docs/.gitignore" \
        '**/'
}

# ============================================================
# 收集工作区文件
# ============================================================

collect_worktree() {
    FILE_LIST="$TMP_DIR/files"
    EXT_LIST="$TMP_DIR/extensions"
    NO_EXT_LIST="$TMP_DIR/no_extensions"

    : > "$FILE_LIST"
    : > "$EXT_LIST"
    : > "$NO_EXT_LIST"

    git ls-files -co --exclude-standard > "$FILE_LIST"

    while IFS= read -r file || [ -n "$file" ]; do
        [ -n "$file" ] || continue

        base=${file##*/}

        case "$base" in
            .* )
                # 隐藏文件不参与普通扩展名白名单
                ;;

            *.* )
                ext=${base##*.}

                if [ -n "$ext" ]; then
                    printf '%s\n' "$ext" >> "$EXT_LIST"
                fi
                ;;

            * )
                # 保留无后缀文件，包括软链接
                printf '%s\n' "$file" >> "$NO_EXT_LIST"
                ;;
        esac

    done < "$FILE_LIST"

    sort -u "$EXT_LIST" -o "$EXT_LIST"
    sort -u "$NO_EXT_LIST" -o "$NO_EXT_LIST"
}

# ============================================================
# 合并 keep 清单
# ============================================================

build_keep_list() {
    KEEP_LIST="$TMP_DIR/keep"

    : > "$KEEP_LIST"

    if [ "$NO_DEFAULT" -eq 0 ]; then
        cat "$DEFAULT_KEEP" >> "$KEEP_LIST"
    fi

    cat "$KEEP_ARGS" >> "$KEEP_LIST"

    # 去除注释和空行，并去重
    grep -v '^[[:space:]]*#' "$KEEP_LIST" |
        grep -v '^[[:space:]]*$' |
        sort -u > "$TMP_DIR/keep_unique" || :

    mv "$TMP_DIR/keep_unique" "$KEEP_LIST"
}

# ============================================================
# 生成主 .gitignore
# ============================================================

generate_main() {
    echo "# Auto-generated by $SCRIPT_NAME"
    echo "# Generated at: $(date '+%F %T')"
    echo "# Strategy: extension whitelist + extensionless files + common keep"
    echo

    # --------------------------------------------------------
    # 1. 默认忽略所有内容
    # --------------------------------------------------------

    echo "# =================================================="
    echo "# 1. Ignore everything by default"
    echo "# =================================================="

    echo '*'

    # 允许 Git 递归遍历目录
    echo '!*/'

    echo

    # --------------------------------------------------------
    # 2. 保留无后缀文件
    # --------------------------------------------------------

    echo "# =================================================="
    echo "# 2. Keep existing extensionless files"
    echo "# =================================================="

    if [ ! -s "$NO_EXT_LIST" ]; then
        echo "# (none)"
    else
        while IFS= read -r file; do
            escaped=$(escape_pattern "$file")
            printf '!/%s\n' "$escaped"
        done < "$NO_EXT_LIST"
    fi

    echo

    # --------------------------------------------------------
    # 3. 保留工作区现有扩展名
    # --------------------------------------------------------

    echo "# =================================================="
    echo "# 3. Keep existing file extensions"
    echo "# =================================================="

    if [ ! -s "$EXT_LIST" ]; then
        echo "# (none)"
    else
        while IFS= read -r ext; do
            escaped=$(escape_pattern "$ext")
            printf '!*.%s\n' "$escaped"
        done < "$EXT_LIST"
    fi

    echo

    # --------------------------------------------------------
    # 4. 忽略所有隐藏文件和隐藏目录
    # --------------------------------------------------------

    echo "# =================================================="
    echo "# 4. Ignore hidden files and directories"
    echo "# =================================================="

    echo '.*'

    echo

    # --------------------------------------------------------
    # 5. 放行常用配置和用户 keep 规则
    # --------------------------------------------------------

    echo "# =================================================="
    echo "# 5. Keep common files and directories"
    echo "# =================================================="

    if [ ! -s "$KEEP_LIST" ]; then
        echo "# (none)"
    else
        while IFS= read -r pattern; do
            case "$pattern" in
                !*)
                    # 用户显式传入否定规则
                    printf '%s\n' "$pattern"
                    ;;

                */)
                    # 目录规则需要开放目录本身和内容
                    escaped=$(escape_pattern "${pattern%/}")
                    printf '!%s/\n' "$escaped"
                    printf '!%s/**\n' "$escaped"
                    ;;

                *)
                    escaped=$(escape_pattern "$pattern")
                    printf '!%s\n' "$escaped"
                    ;;
            esac
        done < "$KEEP_LIST"
    fi
}

# ============================================================
# 主流程
# ============================================================

if [ "$SUB_ONLY" -eq 0 ]; then

    # 先收集，再备份，避免 .bak 文件进入扩展名清单
    collect_worktree
    build_keep_list

    if [ -e "$OUT" ] || [ -L "$OUT" ]; then
        if [ "$FORCE" -eq 1 ]; then
            :

        elif [ "$DRY" -eq 1 ]; then
            echo "[dry-run] would back up: $OUT"

        else
            backup=$(backup_existing "$OUT")
            echo "backed up: $OUT -> $backup"
        fi
    fi

    if [ "$DRY" -eq 1 ]; then
        generate_main
    else
        generate_main > "$OUT"

        echo "written: $OUT"
        echo
        echo "kept extensions:"

        if [ -s "$EXT_LIST" ]; then
            sed 's/^/  ./' "$EXT_LIST"
        else
            echo "  (none)"
        fi

        echo
        echo "kept extensionless files:"

        if [ -s "$NO_EXT_LIST" ]; then
            sed 's/^/  /' "$NO_EXT_LIST"
        else
            echo "  (none)"
        fi

        echo
        echo "kept special patterns:"

        if [ -s "$KEEP_LIST" ]; then
            sed 's/^/  /' "$KEEP_LIST"
        else
            echo "  (none)"
        fi
    fi
fi

# ============================================================
# 子目录规则
# ============================================================

echo
echo "# === Subdirectory .gitignore ==="

apply_data_ignore
apply_logs_ignore
apply_docs_ignore

echo
echo "done."

