# cctag — Git tag management with three tag types

Manage annotated tags across three categories — `stab<N>`, `dev<N>`, `bug<N>` — each with independent numbering. Supports create, list, show, delete, and amend. Designed for Agent invocation — every operation returns structured output and handles edge cases explicitly.

## Three tag types

| Type | Purpose | When to use |
| --- | --- | --- |
| `stab<N>` | Stable checkpoint | A piece of work is **completed** and stable. This is a milestone. |
| `dev<N>` | Development snapshot | Work is **in progress** — save current state before continuing. |
| `bug<N>` | Bug fix | A **bug was discovered** and fixed. Marks the fix point. |

Each type has its **own independent counter** starting from 0. `stab0`, `dev0`, `bug0` can all coexist.

## Trigger

Invoke this skill when the user asks to:

- Create/apply a tag ("打标签", "tag", "标记一下", "版本标记")
  - "stab" / "稳定版" / "完成了" / "完成" → `stab<N>`
  - "dev" / "开发中" / "暂存" / "保存进度" / "快照" → `dev<N>`
  - "bug" / "修复" / "修bug" / "补丁" / "fix" → `bug<N>`
- List or search existing tags ("查看tag", "list tags", "有哪些标签")
- Show tag details ("tag详情", "show tag stab3")
- Delete a tag ("删除tag", "delete tag stab5")
- Amend/reword a tag ("修改tag", "amend tag", "重写tag内容")

**Auto-detection**: When the user doesn't explicitly specify a type, infer from context:
- Mentioning "bug"/"修复"/"fix"/"补丁"/"问题" → `bug`
- Mentioning "dev"/"暂存"/"保存"/"快照"/"继续" → `dev`
- Mentioning "stab"/"完成"/"稳定"/"版本"/"发布" or no clear signal → `stab` (default)

If ambiguous, ask: "Which tag type? [stab/dev/bug]"

## Tag naming convention

```text
stab0, stab1, stab2, ... stabN     (stable checkpoints)
dev0, dev1, dev2, ... devN         (development snapshots)
bug0, bug1, bug2, ... bugN         (bug fixes)
```

All counters start from 0 and increment independently. The first tag in each category uses `<type>0`.

## Tag message format

Every tag is an **annotated tag** with the following message format:

```text
follow <previous-tag-of-any-type>, 1. 变更说明一; 2. 变更说明二; 3. 变更说明三; ...... [Claude Code].
```

- The **first tag** uses `<type>0 init, 1. ... [Claude Code].` (no predecessor)
- `<type><N>` (N>0) uses `follow <previous-tag>, 1. ...` — references the **immediately previous tag regardless of type**
- For example, if the tag history is `stab3 → dev0 → bug1 → dev1`, then `dev1` uses `follow bug1, 1. ...`
- Changelog items are numbered, separated by Chinese semicolon + space (`; `)
- Each item is a concise Chinese sentence summarizing one logical group of changes
- The suffix ` [Claude Code].` (preceded by a space, trailing period) is always appended
- The message is stored as the tag annotation (`git tag -a -m "..."`)

### Changelog item guidelines

When constructing changelog items from diffs and commit messages:

1. **Group related changes** — all changes to a single subsystem/feature count as one item
2. **Order by importance** — structural/architectural → new features → fixes → cleanups
3. **One sentence each** — no nested lists, no multi-line items
4. **Omit trivial changes** — whitespace, comment-only edits, generated files
5. **Use action-oriented phrasing** — "重构env.sh加载逻辑" not "env.sh被修改了"

Example:

```text
follow stab8, 1. 重构lib目录结构，统一版本化配置模式; 2. 新增cctag Agent技能，替代ccgpush; 3. 修复zshrc中oh-my-zsh插件加载顺序; 4. 清理bin/中过期脚本 [Claude Code].
```

---

## Operations

### 1. Create a new tag

This is the primary operation. It determines the tag type, analyzes changes since the last tag of that type, builds a changelog, and creates an annotated tag.

#### Step 1.1 — Determine tag type and next number

First, determine the tag type (`TYPE`): one of `stab`, `dev`, or `bug`. Use auto-detection rules from the Trigger section. If ambiguous, ask the user.

Then find the latest tag of that type and compute the next number:

```bash
TYPE="stab"   # or dev, bug — determined in the step above
LAST_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | head -1)
if [ -z "$LAST_TAG" ]; then
    NEW_NUM=0
else
    LAST_NUM=$(echo "$LAST_TAG" | sed "s/^${TYPE}//")
    NEW_NUM=$((LAST_NUM + 1))
fi
NEW_TAG="${TYPE}${NEW_NUM}"
```

**Edge case**: If tags of this type exist but are not integer-suffixed, fall back to `git tag -l "${TYPE}[0-9]*"` to filter only numeric ones.

#### Step 1.2 — Review changes since baseline

The **baseline** is the most recent tag of **any type** (stab, dev, or bug). If no tags exist, use the first commit.

```bash
# Baseline = latest tag of ANY type
BASELINE=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug)[0-9]+$' | head -1)
# If no tags exist, use the first commit
if [ -z "$BASELINE" ]; then
    BASELINE=$(git rev-list --max-parents=0 HEAD)
fi
```

Review changes:

```bash
# Commits since baseline
git log ${BASELINE}..HEAD --oneline --no-merges

# Files changed
git diff ${BASELINE}..HEAD --stat

# Full diff for detailed analysis (limit to 500 lines)
git diff ${BASELINE}..HEAD -- . | head -500
```

**Edge case — no previous commits**: If the repo has no commits yet, skip the diff review. The changelog should simply state "初始提交".

**Edge case — no changes since baseline**: If `git diff ${BASELINE}..HEAD --stat` is empty, inform the user there are no new changes to tag. Do NOT create an empty tag unless the user explicitly requests it.

#### Step 1.3 — Build the changelog

Analyze the collected diffs and commit messages to produce the tag message. Apply the changelog guidelines from above.

- For `bug` tags: focus on what was broken, how it was fixed, and what was affected.
- For `dev` tags: describe what was done so far, what's still in progress (optional), and the current state.
- For `stab` tags: describe completed work comprehensively.

Present the proposed message to the user for confirmation:

```text
Type:    dev
Tag:     dev3
Message: follow stab9, 1. 初步实现xxx功能; 2. 添加yyy模块框架 [Claude Code].
Changes: 3 files changed, 85 insertions(+), 12 deletions(-)

Proceed? [Y/n]
```

**If the user rejects**, ask what to change — reword a specific item, add a missing item, or remove an item.

#### Step 1.4 — Create the tag

```bash
git tag -a "$NEW_TAG" -m "$TAG_MESSAGE"
```

Verify creation:

```bash
git tag -l "$NEW_TAG"                        # Confirm tag exists
git tag -l --format='%(subject)' "$NEW_TAG"  # Show the tag message
```

#### Step 1.5 — Push (optional, ask user)

After creating the tag, ask the user whether to push:

```text
Tag dev3 created. Push to remote? [Y/n]
```

If yes:

```bash
git push origin "$NEW_TAG"     # Push the specific tag
# OR
git push origin --tags          # Push all tags (use only if user wants to push all)
```

**Edge case — no remote**: If `git remote` is empty, skip the push step and note that no remote is configured.

---

### 2. List tags

List tags, optionally filtered by type:

```bash
# List all tags (all three types)
git tag -l --sort=-v:refname --format='%(refname:short) | %(taggername) | %(taggerdate:short) | %(subject)' | grep -E '^(stab|dev|bug)[0-9]+'

# Filter by type (e.g., only stab tags)
TYPE="dev"
git tag -l "${TYPE}[0-9]*" --sort=-v:refname --format='%(refname:short) | %(taggerdate:short) | %(subject)'

# Count by type
git tag -l 'stab[0-9]*' | wc -l
git tag -l 'dev[0-9]*'  | wc -l
git tag -l 'bug[0-9]*'  | wc -l
```

Output format (grouped by type):

```text
=== stab (3 tags) ===
stab9  | 2026-07-09 | follow stab8, 1. 重构lib目录结构; 2. ...
stab8  | 2026-07-08 | follow stab7, 1. 新增xxx功能; 2. ...
stab0  | 2026-07-01 | stab0 init, 1. 初始化配置仓库 [Claude Code].

=== dev (2 tags) ===
dev1   | 2026-07-09 | follow dev0, 1. 实现xxx模块框架 [Claude Code].
dev0   | 2026-07-09 | dev0 init, 1. 开始yyy功能开发 [Claude Code].

=== bug (1 tag) ===
bug0   | 2026-07-09 | bug0 init, 1. 修复zzz空指针异常 [Claude Code].
```

**Edge case — no tags**: Report "No cctag tags found in this repository."

---

### 3. Show a specific tag

Show detailed information about a single tag (any type):

```bash
# Show tag annotation
git tag -l --format='%(subject)%0a%(body)' "$TAG_NAME"

# Show tag author info and date
git tag -l --format='Type: %(refname:short)%0aAuthor: %(taggername) <%(taggeremail)>%0aDate: %(taggerdate:iso)%0aMessage: %(subject)' "$TAG_NAME"

# Show commits between this tag and its predecessor (any type)
PREV_TAG=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug)[0-9]+$' | grep -A1 "^$TAG_NAME$" | tail -1)
if [ -n "$PREV_TAG" ]; then
    git log ${PREV_TAG}..${TAG_NAME} --oneline --no-merges
fi
```

**Edge case — tag not found**: Report "Tag 'xxx' does not exist. Use 'list' to see available tags."

**Edge case — first tag of a type**: Note that there is no previous tag of this type to diff against.

---

### 4. Delete a tag

Delete a tag both locally and remotely:

```bash
# Confirm before deleting
git tag -l --format='%(subject)' "$TAG_NAME"

# Delete locally
git tag -d "$TAG_NAME"

# Delete remotely (if it exists there)
git push origin :refs/tags/"$TAG_NAME" 2>/dev/null
```

**Edge case — tag not found locally**: Check remote: `git ls-remote --tags origin "$TAG_NAME"`. If found remotely but not locally, fetch first then delete.

**Edge case — force delete**: If the user passes `--force` or the tag has already been pushed, confirm explicitly before deleting the remote tag — this is a destructive operation that affects all collaborators.

---

### 5. Amend a tag

Rewrite the message of an existing tag (any type):

#### Step 5.1 — Identify the target tag

```bash
# User-specified tag
TARGET_TAG="dev2"   # from user input

# Or amend latest of a given type
TYPE="stab"   # from user input or auto-detected
TARGET_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | head -1)
```

#### Step 5.2 — Show current tag content

```bash
git tag -l --format='%(subject)' "$TARGET_TAG"
```

#### Step 5.3 — Review changes since the tag's predecessor

Use the immediate predecessor tag of any type as baseline (same logic as Step 1.2).

#### Step 5.4 — Build new message

Propose a new message. This may be entirely rewritten or just partially edited — follow the user's instructions. Keep the same tag type.

#### Step 5.5 — Replace the tag

```bash
# Delete old tag locally
git tag -d "$TARGET_TAG"

# Delete old tag remotely (if needed)
git push origin :refs/tags/"$TARGET_TAG" 2>/dev/null

# Re-create with new message (at the same commit)
git tag -a "$TARGET_TAG" -m "$NEW_MESSAGE"

# Push updated tag (ask user first)
git push origin "$TARGET_TAG"
```

**Warning**: Amending a pushed tag rewrites history for anyone who has already pulled the old tag. Always warn the user before deleting a remote tag.

---

### 6. Cherry-pick: tag a specific range

When the user wants to tag changes between two specific points:

```bash
# Use a specified base ref
BASE_REF="stab5"         # user-specified
HEAD_REF="HEAD"          # default, or user-specified
git log ${BASE_REF}..${HEAD_REF} --oneline --no-merges
git diff ${BASE_REF}..${HEAD_REF} --stat
```

Proceed with Steps 1.1–1.5, substituting `$BASE_REF` for the baseline.

---

## Error handling summary

| Scenario | Action |
| --- | --- |
| Ambiguous tag type | Ask user: "Which tag type? [stab/dev/bug]" |
| No previous tags at all | Use first commit as baseline |
| No commits in repo | Abort; report nothing to tag |
| No changes since baseline | Report and ask user whether to proceed |
| No remote configured | Skip push; note the absence |
| Tag name collision | Increment N and retry (should not happen with auto-numbering) |
| Tag already exists remotely | Warn if local and remote messages differ |
| Amend on non-existent tag | Report the tag doesn't exist; suggest listing |
| User rejects changelog | Allow reword of specific items or full rewrite |

## Agent output conventions

After each operation, report a structured summary:

```text
✓ Tag dev3 created
  Type:    dev
  Message: follow stab9, 1. 实现xxx模块框架; 2. 添加yyy接口 [Claude Code].
  Pushed:  yes (origin)
  Files:   3 changed, 85 insertions(+), 12 deletions(-)
```

For listing:

```text
stab9  2026-07-09  follow stab8, 1. 重构lib目录结构; 2. 新增cctag技能 [Claude Code].
stab8  2026-07-08  follow stab7, 1. 新增xxx功能; 2. ...
dev1   2026-07-09  follow dev0, 1. 实现xxx模块框架 [Claude Code].
dev0   2026-07-09  dev0 init, 1. 开始yyy功能开发 [Claude Code].
bug0   2026-07-09  bug0 init, 1. 修复zzz空指针异常 [Claude Code].
```
