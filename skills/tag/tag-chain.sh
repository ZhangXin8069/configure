#!/usr/bin/env bash

# Audit and, when explicitly requested, repair the follow chain of annotated
# stab/dev/bug/test tags.  The script changes tag objects only; it never moves
# the commit to which a tag peels.

set -u
set -o pipefail
export LC_ALL=C

usage() {
    cat <<'USAGE'
用法:
  tag-chain.sh [--check] [--repo PATH] [--remote NAME] [--root TAG]
  tag-chain.sh --repair [--dry-run] [--repo PATH] [--remote NAME]
  tag-chain.sh --repair --apply [--repo PATH]
  tag-chain.sh --repair --apply --remote NAME --confirm-remote-rewrite

选项:
  --check                    只读检查（默认）。
  --repair                   生成修正清单；不带 --apply 时不写入。
  --dry-run                  显式要求只生成清单。
  --apply                    应用可安全推导的本地 follow 前缀修正。
  --repo PATH                指定 Git 工作树或其子目录，默认当前目录。
  --remote NAME              同时核对远端 refs/tags；不代表会推送。
  --root TAG                指定历史根标签，覆盖自动识别的唯一 init 标签。
  --confirm-remote-rewrite  与 --apply、--remote 一起使用，明确授权远程标签重写。
  --help                     显示帮助。

排序与安全规则:
  1. 唯一的“<tag> init,”消息作为根；之后按 tagger 时间升序排列。
  2. tagger 时间并列、缺失根、非祖先提交、轻量/签名标签不自动改写。
  3. 远程应用使用 --force-with-lease，远端对象发生漂移时拒绝覆盖。
USAGE
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

is_managed_tag() {
    [[ "$1" =~ ^(stab|dev|bug|test)[0-9]+(_[0-9]+)?$ ]]
}

repo_path=''
remote_name=''
root_override=''
mode='check'
apply=0
confirm_remote=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check)
            mode='check'
            ;;
        --repair)
            mode='repair'
            ;;
        --dry-run)
            mode='repair'
            ;;
        --apply)
            mode='repair'
            apply=1
            ;;
        --repo)
            shift
            [ "$#" -gt 0 ] || die '--repo 缺少 PATH'
            repo_path=$1
            ;;
        --remote)
            shift
            [ "$#" -gt 0 ] || die '--remote 缺少 NAME'
            remote_name=$1
            ;;
        --root)
            shift
            [ "$#" -gt 0 ] || die '--root 缺少 TAG'
            root_override=$1
            ;;
        --confirm-remote-rewrite)
            confirm_remote=1
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

if [ "$confirm_remote" -eq 1 ] && { [ "$apply" -ne 1 ] || [ -z "$remote_name" ]; }; then
    die '--confirm-remote-rewrite 必须与 --apply --remote NAME 一起使用'
fi

script_path=$0
case "$script_path" in
    /*) ;;
    *) script_path="$(pwd)/$script_path" ;;
esac

if [ -n "$repo_path" ]; then
    cd "$repo_path" || die "无法进入仓库路径: $repo_path"
fi

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || die '当前路径不在 Git 工作树中'
cd "$repo_root" || die "无法进入 Git 根目录: $repo_root"

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/tag-chain.XXXXXX") || die '无法创建临时目录'
cleanup() {
    rm -rf "$tmp_dir"
}
trap cleanup EXIT HUP INT TERM

tab=$(printf '\t')
raw_records="$tmp_dir/raw-records"
sorted_records="$tmp_dir/sorted-records"
ordered_records="$tmp_dir/ordered-records"
repair_candidates="$tmp_dir/repair-candidates"
prepared_repairs="$tmp_dir/prepared-repairs"
remote_refs="$tmp_dir/remote-refs"
: > "$raw_records"
: > "$repair_candidates"
: > "$prepared_repairs"

tag_count=0
init_count=0
root_name=''
root_record=''
record_index=0

while IFS=' ' read -r tag_name object_oid object_type created; do
    [ -n "$tag_name" ] || continue
    is_managed_tag "$tag_name" || continue

    tag_count=$((tag_count + 1))
    target_oid=''
    message_file="$tmp_dir/message-$record_index"
    payload_file="$tmp_dir/payload-original-$record_index"
    record_index=$((record_index + 1))

    if [ "$object_type" = 'tag' ]; then
        target_oid=$(git rev-parse -q --verify "$tag_name^{}" 2>/dev/null) || target_oid=''
        if git cat-file tag "$tag_name" > "$payload_file" 2>/dev/null; then
            awk 'seen { if (started || NF) { started=1; print } } /^$/ { seen=1 }' \
                "$payload_file" > "$message_file"
        else
            : > "$payload_file"
            : > "$message_file"
        fi
    else
        : > "$payload_file"
        : > "$message_file"
    fi

    first_line=$(sed -n '1p' "$message_file")
    init_flag=0
    case "$first_line" in
        "$tag_name init,"*)
            init_flag=1
            init_count=$((init_count + 1))
            ;;
    esac

    record=$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
        "$created" "$tag_name" "$object_oid" "$object_type" "$target_oid" "$message_file" "$payload_file" "$init_flag")
    printf '%s\n' "$record" >> "$raw_records"
    if [ "$init_flag" -eq 1 ]; then
        root_record=$record
    fi
done < <(git for-each-ref \
    --format='%(refname:short) %(objectname) %(objecttype) %(creatordate:unix)' \
    refs/tags)

if [ "$tag_count" -eq 0 ]; then
    printf 'Repository: %s\n' "$repo_root"
    printf 'PASS: 未发现 stab/dev/bug/test 标签。\n'
    exit 0
fi

sort -t "$tab" -k1,1n -k2,2 "$raw_records" > "$sorted_records" || die '标签排序失败'

if [ -n "$root_override" ]; then
    is_managed_tag "$root_override" || die "根标签名称不符合约定: $root_override"
    root_record=$(awk -F '\t' -v wanted="$root_override" '$2 == wanted { print; exit }' "$raw_records")
    [ -n "$root_record" ] || die "指定根标签不存在: $root_override"
    root_name=$root_override
elif [ "$init_count" -eq 1 ]; then
    root_name=$(printf '%s\n' "$root_record" | awk -F '\t' '{print $2}')
elif [ "$init_count" -eq 0 ]; then
    printf 'Repository: %s\n' "$repo_root"
    printf 'BLOCK: 未找到唯一 init 标签；请用 --root TAG 指定历史根。\n'
    exit 1
else
    printf 'Repository: %s\n' "$repo_root"
    printf 'BLOCK: 找到 %s 个 init 标签；请用 --root TAG 消除根歧义。\n' "$init_count"
    exit 1
fi

printf '%s\n' "$root_record" > "$ordered_records"
while IFS="$tab" read -r created tag_name object_oid object_type target_oid message_file payload_file init_flag; do
    [ "$tag_name" = "$root_name" ] && continue
    printf '%s\n' "$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
        "$created" "$tag_name" "$object_oid" "$object_type" "$target_oid" "$message_file" "$payload_file" "$init_flag")" >> "$ordered_records"
done < "$sorted_records"

printf 'Repository: %s\n' "$repo_root"
printf 'Root: %s\n' "$root_name"
printf 'Order: init root, then annotated tagger timestamp ascending\n'
printf 'Managed tags: %s\n' "$tag_count"

issue_count=0
blocking_count=0
repair_count=0
order_tie=0
previous_date=''
previous_name=''
previous_target=''
seen_parents="$tmp_dir/seen-parents"
: > "$seen_parents"

while IFS="$tab" read -r created tag_name object_oid object_type target_oid message_file payload_file init_flag; do
    if [ "$object_type" != 'tag' ]; then
        printf '[BLOCK] %s 不是附注标签（object type=%s）\n' "$tag_name" "$object_type"
        issue_count=$((issue_count + 1))
        blocking_count=$((blocking_count + 1))
    elif [ -z "$target_oid" ]; then
        printf '[BLOCK] %s 无法解析 peeled commit\n' "$tag_name"
        issue_count=$((issue_count + 1))
        blocking_count=$((blocking_count + 1))
    fi

    if [ -n "$previous_date" ] && [ "$created" = "$previous_date" ]; then
        printf '[BLOCK] tagger 时间并列: %s 与 %s (%s)\n' "$previous_name" "$tag_name" "$created"
        issue_count=$((issue_count + 1))
        blocking_count=$((blocking_count + 1))
        order_tie=1
    fi

    if [ -z "$previous_name" ]; then
        case "$(sed -n '1p' "$message_file")" in
            "$tag_name init,"*) ;;
            *)
                printf '[BLOCK] 根标签 %s 缺少“%s init,”前缀\n' "$tag_name" "$tag_name"
                issue_count=$((issue_count + 1))
                blocking_count=$((blocking_count + 1))
                ;;
        esac
    else
        expected_parent=$previous_name
        subject=$(sed -n '1p' "$message_file")
        actual_parent=''
        if [[ "$subject" =~ ^follow[[:space:]]+([^,]+), ]]; then
            actual_parent=${BASH_REMATCH[1]}
        fi

        if [ -z "$actual_parent" ]; then
            printf '[FIX] %s: 缺少 follow 前缀 -> 补 follow %s\n' "$tag_name" "$expected_parent"
            issue_count=$((issue_count + 1))
            if [ "$object_type" != 'tag' ] || [ -z "$target_oid" ] || [ ! -s "$message_file" ]; then
                printf '[BLOCK] %s 不是可安全补前缀的有效附注标签\n' "$tag_name"
                blocking_count=$((blocking_count + 1))
            elif grep -q '^gpgsig ' "$payload_file"; then
                printf '[BLOCK] %s 含签名，自动改写会破坏签名\n' "$tag_name"
                blocking_count=$((blocking_count + 1))
            else
                printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
                    "$tag_name" "$object_oid" "$created" "$target_oid" "$message_file" "$payload_file" "$expected_parent" 'prepend' >> "$repair_candidates"
                repair_count=$((repair_count + 1))
            fi
        elif [ "$actual_parent" != "$expected_parent" ]; then
            printf '[FIX] %s: follow %s -> follow %s\n' "$tag_name" "$actual_parent" "$expected_parent"
            issue_count=$((issue_count + 1))
            if [ "$object_type" != 'tag' ] || [ -z "$target_oid" ]; then
                printf '[BLOCK] %s 不是可安全重写的有效附注标签\n' "$tag_name"
                blocking_count=$((blocking_count + 1))
            elif grep -q '^gpgsig ' "$payload_file"; then
                printf '[BLOCK] %s 含签名，自动改写会破坏签名\n' "$tag_name"
                blocking_count=$((blocking_count + 1))
            else
                printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
                    "$tag_name" "$object_oid" "$created" "$target_oid" "$message_file" "$payload_file" "$expected_parent" 'replace' >> "$repair_candidates"
                repair_count=$((repair_count + 1))
            fi
        fi

        if [ -n "$actual_parent" ] && grep -Fqx "$actual_parent" "$seen_parents"; then
            printf '[DUPLICATE] %s 重复引用 follow %s（随前缀修正一并消除）\n' "$tag_name" "$actual_parent"
            issue_count=$((issue_count + 1))
        fi
        if [ -n "$actual_parent" ]; then
            grep -Fqx "$actual_parent" "$seen_parents" || printf '%s\n' "$actual_parent" >> "$seen_parents"
        fi

        if [ -z "$previous_target" ] || [ -z "$target_oid" ]; then
            printf '[BLOCK] %s -> %s 缺少可验证的提交目标\n' "$previous_name" "$tag_name"
            issue_count=$((issue_count + 1))
            blocking_count=$((blocking_count + 1))
        elif ! git merge-base --is-ancestor "$previous_target" "$target_oid"; then
            printf '[BLOCK] %s 的 peeled commit 不是 %s 的祖先，不能只改消息\n' "$previous_name" "$tag_name"
            issue_count=$((issue_count + 1))
            blocking_count=$((blocking_count + 1))
        fi
    fi

    previous_date=$created
    previous_name=$tag_name
    previous_target=$target_oid
done < "$ordered_records"

if [ "$order_tie" -eq 1 ]; then
    repair_count=0
fi

remote_error=0
if [ -n "$remote_name" ]; then
    if ! git ls-remote --tags "$remote_name" > "$remote_refs" 2> "$tmp_dir/remote-error"; then
        printf '[BLOCK] 无法读取远端 %s: %s\n' "$remote_name" "$(sed -n '1p' "$tmp_dir/remote-error")"
        issue_count=$((issue_count + 1))
        blocking_count=$((blocking_count + 1))
        remote_error=1
    else
        while IFS="$tab" read -r created tag_name object_oid object_type target_oid message_file payload_file init_flag; do
            remote_object=$(awk -F '[[:space:]]+' -v ref="refs/tags/$tag_name" '$2 == ref { print $1; exit }' "$remote_refs")
            remote_target=$(awk -F '[[:space:]]+' -v ref="refs/tags/$tag_name^{}" '$2 == ref { print $1; exit }' "$remote_refs")
            if [ -z "$remote_object" ]; then
                printf '[REMOTE] %s: 远端缺失\n' "$tag_name"
                issue_count=$((issue_count + 1))
                blocking_count=$((blocking_count + 1))
            elif [ "$remote_object" != "$object_oid" ] || [ "$remote_target" != "$target_oid" ]; then
                printf '[REMOTE] %s: local object/target=%s/%s, remote=%s/%s\n' \
                    "$tag_name" "$object_oid" "$target_oid" "$remote_object" "${remote_target:-missing}"
                issue_count=$((issue_count + 1))
                blocking_count=$((blocking_count + 1))
            fi
        done < "$ordered_records"
    fi
fi

if [ "$mode" = 'check' ]; then
    if [ "$issue_count" -eq 0 ]; then
        printf 'PASS: follow 链、提交祖先关系%s均正常。\n' \
            "${remote_name:+，远端 $remote_name 对象一致}"
        exit 0
    fi
    printf 'FAIL: 发现 %s 个问题；可安全修正候选 %s 个。\n' "$issue_count" "$repair_count"
    exit 1
fi

if [ "$repair_count" -eq 0 ]; then
    if [ "$issue_count" -eq 0 ]; then
        printf 'PASS: 没有需要修正的 follow 链。\n'
        exit 0
    fi
    printf 'STOP: 没有可安全自动修正的候选。\n'
    exit 1
fi

printf 'Repair mode: %s candidate(s), %s blocking issue(s)\n' "$repair_count" "$blocking_count"
if [ "$apply" -ne 1 ]; then
    printf 'DRY-RUN: 未写入任何本地或远程标签。\n'
    exit 1
fi

if [ "$blocking_count" -ne 0 ]; then
    printf 'STOP: 存在阻断项，未应用任何修正。\n'
    exit 1
fi

if [ -n "$remote_name" ] && [ "$confirm_remote" -ne 1 ]; then
    printf 'STOP: 指定了远端但未提供 --confirm-remote-rewrite，未改写远端。\n'
    exit 1
fi

candidate_index=0
while IFS="$tab" read -r tag_name object_oid created target_oid message_file payload_file expected_parent repair_kind; do
    [ -n "$tag_name" ] || continue
    candidate_index=$((candidate_index + 1))
    original_payload_file=$payload_file
    payload_file="$tmp_dir/payload-$candidate_index"
    body_file="$tmp_dir/body-$candidate_index"
    new_body_file="$tmp_dir/new-body-$candidate_index"

    if grep -q '^gpgsig ' "$original_payload_file"; then
        printf 'STOP: %s 含签名，未应用任何修正。\n' "$tag_name"
        exit 1
    fi

    sed -n '1,$p' "$message_file" > "$body_file"
    if [ "$repair_kind" = 'prepend' ]; then
        {
            printf 'follow %s, ' "$expected_parent"
            sed -n '1,$p' "$body_file"
        } > "$new_body_file"
    else
        sed "1s/^follow[[:space:]]*[^,]*,/follow ${expected_parent},/" "$body_file" > "$new_body_file"
    fi
    {
        sed -n '1,/^$/p' "$original_payload_file" | sed '$d'
        printf '\n'
        sed -n '1,$p' "$new_body_file"
    } > "$payload_file"

    new_oid=$(git mktag < "$payload_file" 2> "$tmp_dir/mktag-error-$candidate_index") || {
        printf 'STOP: %s 无法创建新附注对象: %s\n' "$tag_name" "$(sed -n '1p' "$tmp_dir/mktag-error-$candidate_index")"
        exit 1
    }
    new_target=$(git rev-parse -q --verify "$new_oid^{}" 2>/dev/null) || new_target=''
    if [ "$new_target" != "$target_oid" ]; then
        printf 'STOP: %s 新附注对象的 peeled commit 改变（%s -> %s）\n' \
            "$tag_name" "$target_oid" "${new_target:-missing}"
        exit 1
    fi
    printf '[PLAN] %s: object %s -> %s; peeled=%s\n' \
        "$tag_name" "$object_oid" "$new_oid" "$target_oid"
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$tag_name" "$object_oid" "$new_oid" "$expected_parent" "$target_oid" >> "$prepared_repairs"
done < "$repair_candidates"

if [ -n "$remote_name" ]; then
    push_args=()
    refspecs=()
    while IFS="$tab" read -r tag_name object_oid new_oid expected_parent target_oid; do
        push_args+=("--force-with-lease=refs/tags/$tag_name:$object_oid")
        refspecs+=("$new_oid:refs/tags/$tag_name")
    done < "$prepared_repairs"
    # The explicit remote confirmation above is the destructive-operation gate.
    # --atomic prevents a multi-tag repair from leaving a partially rewritten
    # remote when the server supports atomic receive-pack.
    if ! git push --atomic "${push_args[@]}" "$remote_name" "${refspecs[@]}"; then
        printf 'STOP: 远端标签推送失败，未更新本地 refs/tags。\n'
        exit 1
    fi
    printf 'REMOTE: 已用 force-with-lease 原子改写 %s 的 %s 个标签。\n' "$remote_name" "$repair_count"
fi

updates="$tmp_dir/updates"
: > "$updates"
while IFS="$tab" read -r tag_name object_oid new_oid expected_parent target_oid; do
    printf 'update refs/tags/%s %s %s\n' "$tag_name" "$new_oid" "$object_oid" >> "$updates"
done < "$prepared_repairs"
if ! git update-ref --stdin < "$updates"; then
    printf 'STOP: 远端已更新但本地 refs/tags 更新失败，请按清单手工执行 update-ref。\n'
    exit 1
fi
printf 'LOCAL: 已保留 peeled commit，改写本地 %s 个标签注释。\n' "$repair_count"

if [ -n "$remote_name" ]; then
    "$script_path" --check --repo "$repo_root" --remote "$remote_name"
else
    "$script_path" --check --repo "$repo_root"
fi
