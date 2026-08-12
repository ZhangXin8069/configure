#!/usr/bin/env bash
# mv-small — mv 的包装：自动跳过大小大于 1MB 的文件（被放弃的文件保留在源位置），
# 并将被放弃文件的清单保存到目标目录（.too-large-files.<时间戳>.list），
# 其余参数语义与行为等同 mv。

_PATH=$(
    cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
    pwd
)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

LIMIT=$((1024 * 1024))
TS=$(date "+%Y-%m-%d-%H-%M-%S")

usage() {
    echo "usage: ${_NAME} [OPTION]... SOURCE... DEST" >&2
    echo "       ${_NAME} [OPTION]... -t DIRECTORY SOURCE..." >&2
    echo "files larger than ${LIMIT} bytes are skipped (kept at source);" >&2
    echo "skipped-file list: DEST/.too-large-files.${TS}.list" >&2
}

if [ "$#" -lt 2 ]; then
    usage
    exit 1
fi

args=("$@")
opts=()
sources=()
dest=""
t_mode=0

i=0
while [ "$i" -lt "$#" ]; do
    a="${args[$i]}"
    case "$a" in
        -t | --target-directory)
            i=$((i + 1))
            if [ "$i" -ge "$#" ]; then
                echo "${_NAME}: option '$a' requires an argument" >&2
                exit 1
            fi
            dest="${args[$i]}"
            t_mode=1
            opts+=("$a" "${args[$i]}")
            ;;
        --target-directory=*)
            dest="${a#*=}"
            t_mode=1
            opts+=("$a")
            ;;
        -*)
            opts+=("$a")
            ;;
        *)
            sources+=("$a")
            ;;
    esac
    i=$((i + 1))
done

if [ "$t_mode" -eq 0 ]; then
    if [ "${#sources[@]}" -lt 2 ]; then
        echo "${_NAME}: missing destination file operand" >&2
        exit 1
    fi
    dest="${sources[${#sources[@]} - 1]}"
    sources=("${sources[@]:0:${#sources[@]} - 1}")
else
    if [ "${#sources[@]}" -lt 1 ]; then
        echo "${_NAME}: missing source file operand" >&2
        exit 1
    fi
    if [ ! -d "$dest" ]; then
        echo "${_NAME}: with -t, DEST must be an existing directory: '$dest'" >&2
        exit 1
    fi
fi

list_dir="$dest"
[ -d "$dest" ] || list_dir="$(dirname "$dest")"
mkdir -p "$list_dir" 2>/dev/null || {
    echo "${_NAME}: cannot create '$list_dir'" >&2
    exit 1
}
list="$list_dir/.too-large-files.${TS}.list"
: > "$list"
echo "skipped-file list: ${list}"

# 解析单个源的目标路径（等同 mv 语义）
resolve_target() {
    local src="$1"
    if [ -d "$dest" ]; then
        echo "$dest/$(basename "$src")"
    elif [ "${#sources[@]}" -eq 1 ]; then
        echo "$dest"
    else
        echo "${_NAME}: target '$dest' is not a directory (multiple sources)" >&2
        return 1
    fi
}

move_file() {
    local src="$1" tgt
    if [ ! -e "$src" ] && [ ! -L "$src" ]; then
        echo "${_NAME}: cannot stat '$src': No such file or directory" >&2
        return 1
    fi
    if [ -d "$src" ]; then
        if [ "$t_mode" -eq 1 ]; then
            echo "${_NAME}: directory source with -t is not supported (use SOURCE... DEST form)" >&2
            return 1
        fi
        if [ -e "$dest" ] && [ ! -d "$dest" ]; then
            echo "${_NAME}: cannot overwrite non-directory '$dest' with directory '$src'" >&2
            return 1
        fi
        tgt=$(resolve_target "$src") || return 1
        local d f rel size
        while IFS= read -r -d '' d; do
            rel="${d#"$src"}"
            rel="${rel#/}"
            mkdir -p "$tgt/$rel" || {
                echo "${_NAME}: cannot create directory '$tgt/$rel'" >&2
                return 1
            }
        done < <(find "$src" -type d -print0 2>/dev/null)
        while IFS= read -r -d '' entry; do
            size="${entry%%$'\t'*}"
            f="${entry#*$'\t'}"
            rel="${f#"$src"/}"
            if [ "$size" -gt "$LIMIT" ]; then
                echo "$f" >>"$list"
                echo "skipped (${size} bytes > ${LIMIT}): $f"
            else
                mv "${opts[@]}" "$f" "$tgt/$rel" || {
                    echo "${_NAME}: mv failed: $f" >&2
                    return 1
                }
            fi
        done < <(find "$src" ! -type d -printf '%s\t%p\0' 2>/dev/null)
        # 清理源端被移空的目录（含被放弃大文件的目录因非空而保留）
        find "$src" -depth -type d -empty -delete 2>/dev/null
    elif [ -f "$src" ] || [ -L "$src" ]; then
        local size
        size=$(stat -c %s "$src")
        if [ "$size" -gt "$LIMIT" ]; then
            echo "$src" >>"$list"
            echo "skipped (${size} bytes > ${LIMIT}): $src"
        elif [ "$t_mode" -eq 1 ]; then
            mv "${opts[@]}" "$src" || {
                echo "${_NAME}: mv failed: $src" >&2
                return 1
            }
        else
            tgt=$(resolve_target "$src") || return 1
            mv "${opts[@]}" "$src" "$tgt" || {
                echo "${_NAME}: mv failed: $src" >&2
                return 1
            }
        fi
    else
        echo "${_NAME}: cannot handle special file '$src'" >&2
        return 1
    fi
}

rc=0
for s in "${sources[@]}"; do
    move_file "$s" || rc=1
done

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
exit "$rc"
