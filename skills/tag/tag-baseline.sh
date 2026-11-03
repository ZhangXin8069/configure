#!/usr/bin/env bash

# Resolve managed stab/dev/bug/test tags by tagger date.  Version sorting alone
# is wrong across mixed prefixes (for example stab84 sorts before dev51), so the
# baseline and previous-tag lookups must use creatordate as the primary key.

set -u
set -o pipefail
export LC_ALL=C

usage() {
    cat <<'USAGE'
用法:
  tag-baseline.sh [--latest] [--repo PATH]
  tag-baseline.sh --list [--repo PATH]
  tag-baseline.sh --previous TAG [--repo PATH]

选项:
  --latest          输出按 tagger 时间最新的受管标签（默认）。
  --list            按 tagger 时间从新到旧列出全部受管标签。
  --previous TAG    输出 TAG 在时间序中的前一个受管标签。
  --repo PATH       指定 Git 工作树或其子目录，默认当前目录。
  --help            显示帮助。

受管标签文法: ^(stab|dev|bug|test)[0-9]+(_[0-9]+)*$
排序: tagger 时间降序；时间并列时按版本号降序，保证结果确定。
无匹配时输出为空且退出码为 0；TAG 不存在或不受管时退出码为 2。
USAGE
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

is_managed_tag() {
    [[ "$1" =~ ^(stab|dev|bug|test)[0-9]+(_[0-9]+)*$ ]]
}

repo_path=''
mode='latest'
target=''

while [ "$#" -gt 0 ]; do
    case "$1" in
        --latest)
            mode='latest'
            ;;
        --list)
            mode='list'
            ;;
        --previous)
            shift
            [ "$#" -gt 0 ] || die '--previous 缺少 TAG'
            mode='previous'
            target=$1
            ;;
        --repo)
            shift
            [ "$#" -gt 0 ] || die '--repo 缺少 PATH'
            repo_path=$1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "未知选项: $1"
            ;;
    esac
    shift
done

if [ "$mode" = 'previous' ] && ! is_managed_tag "$target"; then
    die "目标不是受管标签: $target"
fi

if [ -n "$repo_path" ]; then
    cd "$repo_path" || die "无法进入仓库路径: $repo_path"
fi

git rev-parse --show-toplevel >/dev/null 2>&1 || die '当前路径不在 Git 工作树中'

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/tag-baseline.XXXXXX") || die '无法创建临时目录'
cleanup() {
    rm -rf "$tmp_dir"
}
trap cleanup EXIT HUP INT TERM

tag_list="$tmp_dir/tags"
: > "$tag_list"

while IFS= read -r tag_name; do
    [ -n "$tag_name" ] || continue
    is_managed_tag "$tag_name" || continue
    printf '%s\n' "$tag_name" >> "$tag_list"
done < <(git for-each-ref \
    --sort=-v:refname \
    --sort=-creatordate \
    --format='%(refname:short)' \
    refs/tags)

case "$mode" in
    latest)
        head -n 1 "$tag_list"
        ;;
    list)
        cat "$tag_list"
        ;;
    previous)
        grep -Fqx "$target" "$tag_list" || die "目标标签不存在: $target"
        awk -v target="$target" '
            found {
                print
                exit
            }
            $0 == target {
                found = 1
            }
        ' "$tag_list"
        ;;
esac
