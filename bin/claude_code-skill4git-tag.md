# cctag — Git tag management with auto-generated stab tag

Manage `stab<N>` annotated tags: create, list, show, delete, and amend. Designed for Agent invocation — every operation returns structured output and handles edge cases explicitly.

## Trigger

Invoke this skill when the user asks to:

- Create/apply a tag ("打标签", "tag", "stab", "标记一下", "版本标记")
- List or search existing tags ("查看tag", "list tags", "有哪些标签")
- Show tag details ("tag详情", "show tag stab3")
- Delete a tag ("删除tag", "delete tag stab5")
- Amend/reword a tag ("修改tag", "amend tag", "重写tag内容")

## Tag naming convention

```text
stab0, stab1, stab2, ... stabN
```

Tags are **monotonically increasing integers** starting from 0. The first tag is always `stab0`.

## Tag message format

Every stab tag is an **annotated tag** with the following message format:

```text
stab<N> follow stab<N-1>, 1. 变更说明一; 2. 变更说明二; 3. 变更说明三; ...... [Claude Code]
```

- `stab0` uses `stab0 init, 1. ... [Claude Code]` (no predecessor)
- `stab<N>` (N>0) uses `stab<N> follow stab<N-1>, 1. ...`
- Changelog items are numbered, separated by Chinese semicolon + space (`; `)
- Each item is a concise Chinese sentence summarizing one logical group of changes
- The suffix `[Claude Code]` (preceded by a space) is always appended to identify the tag creator
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
stab9 follow stab8, 1. 重构lib目录结构，统一版本化配置模式; 2. 新增cctag Agent技能，替代ccgpush; 3. 修复zshrc中oh-my-zsh插件加载顺序; 4. 清理bin/中过期脚本 [Claude Code]
```

---

## Operations

### 1. Create a new tag

This is the primary operation. It analyzes changes since the last stab tag, builds a changelog, and creates an annotated tag.

#### Step 1.1 — Determine the next tag number

```bash
LAST_STAB=$(git tag -l 'stab*' --sort=-v:refname | head -1)
if [ -z "$LAST_STAB" ]; then
    NEW_NUM=0
else
    LAST_NUM=$(echo "$LAST_STAB" | sed 's/^stab//')
    NEW_NUM=$((LAST_NUM + 1))
fi
NEW_TAG="stab${NEW_NUM}"
```

**Edge case**: If `stab*` tags exist but are not integer-suffixed (e.g., `stab-foo`), fall back to `git tag -l 'stab[0-9]*'` to filter only numeric ones.

#### Step 1.2 — Review changes since last tag

If a previous stab tag exists:

```bash
# Commits since last tag
git log ${LAST_STAB}..HEAD --oneline --no-merges

# Files changed
git diff ${LAST_STAB}..HEAD --stat

# Full diff for detailed analysis (limit to 500 lines for context)
git diff ${LAST_STAB}..HEAD -- . | head -500
```

If this is the **first tag** (no previous stab tag):

```bash
# Recent commit history
git log --oneline --no-merges -30

# All tracked files for context
git diff --stat HEAD~20..HEAD 2>/dev/null || git diff --stat HEAD

# Full diff
git diff HEAD~20..HEAD -- . 2>/dev/null | head -500 || git diff HEAD -- . | head -500
```

**Edge case — no previous commits**: If the repo has no commits yet, skip the diff review. The changelog should simply state "初始提交" or similar.

**Edge case — no changes since last tag**: If `git diff ${LAST_STAB}..HEAD --stat` is empty, inform the user there are no new changes to tag. Do NOT create an empty tag unless the user explicitly requests it.

#### Step 1.3 — Build the changelog

Analyze the collected diffs and commit messages to produce the tag message. Apply the changelog guidelines from above. Present the proposed message to the user for confirmation:

```text
Tag:     stab9
Message: stab9 follow stab8, 1. 重构lib目录结构...; 2. 新增cctag技能... [Claude Code]
Changes: 5 files changed, 120 insertions(+), 45 deletions(-)

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
Tag stab9 created. Push to remote? [Y/n]
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

List all stab tags with their messages:

```bash
# List all stab tags with annotations
git tag -l 'stab[0-9]*' --sort=-v:refname --format='%(refname:short) | %(subject)'

# Count-only mode (when user asks "how many tags")
git tag -l 'stab[0-9]*' | wc -l
```

Output format:

```text
stab9  | stab9 follow stab8, 1. 重构lib目录结构; 2. ...
stab8  | stab8 follow stab7, 1. 新增xxx功能; 2. ...
...
stab0  | stab0 init, 1. 初始化配置仓库 [Claude Code]
```

**Edge case — no tags**: Report "No stab tags found in this repository."

---

### 3. Show a specific tag

Show detailed information about a single tag:

```bash
# Show tag annotation
git tag -l --format='%(subject)%0a%(body)' "$TAG_NAME"

# Show tag author info and date
git tag -l --format='Tag: %(refname:short)%0aAuthor: %(taggername) <%(taggeremail)>%0aDate: %(taggerdate:iso)%0aMessage: %(subject)' "$TAG_NAME"

# Show commits between this tag and previous
PREV_STAB=$(git tag -l 'stab[0-9]*' --sort=-v:refname | grep -A1 "^$TAG_NAME$" | tail -1)
if [ -n "$PREV_STAB" ]; then
    git log ${PREV_STAB}..${TAG_NAME} --oneline --no-merges
fi
```

**Edge case — tag not found**: Report "Tag 'stabX' does not exist. Use 'list' to see available tags."

**Edge case — first tag (stab0)**: Note that there is no previous tag to diff against.

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

Rewrite the message of the most recent stab tag (or a specified one):

#### Step 5.1 — Identify the target tag

```bash
# Default: amend the latest stab tag
TARGET_TAG=$(git tag -l 'stab[0-9]*' --sort=-v:refname | head -1)

# Or user-specified
TARGET_TAG="stab7"   # from user input
```

#### Step 5.2 — Show current tag content

```bash
git tag -l --format='%(subject)' "$TARGET_TAG"
```

#### Step 5.3 — Review changes since previous tag (to rebuild changelog)

Same as Step 1.2 in "Create", using `$TARGET_TAG`'s predecessor as the baseline.

#### Step 5.4 — Build new message

Propose a new message. This may be entirely rewritten or just partially edited — follow the user's instructions.

#### Step 5.5 — Replace the tag

```bash
# Delete old tag locally
git tag -d "$TARGET_TAG"

# Delete old tag remotely (if needed)
git push origin :refs/tags/"$TARGET_TAG" 2>/dev/null

# Re-create with new message
git tag -a "$TARGET_TAG" -m "$NEW_MESSAGE"

# Push updated tag (ask user first)
git push origin "$TARGET_TAG"
```

**Warning**: Amending a pushed tag rewrites history for anyone who has already pulled the old tag. Always warn the user before deleting a remote tag.

---

### 6. Cherry-pick: tag a specific range

When the user wants to tag changes between two specific points (not from the last stab):

```bash
# Use a specified base ref instead of the last stab tag
BASE_REF="stab5"         # user-specified
HEAD_REF="HEAD"          # default, or user-specified
git log ${BASE_REF}..${HEAD_REF} --oneline --no-merges
git diff ${BASE_REF}..${HEAD_REF} --stat
```

Proceed with Steps 1.1–1.5, substituting `$BASE_REF` for the previous stab tag.

---

## Error handling summary

| Scenario | Action |
| --- | --- |
| No previous stab tags | Treat as stab0, use all repo history |
| No commits in repo | Abort; report nothing to tag |
| No changes since last tag | Report and ask user whether to proceed |
| No remote configured | Skip push; note the absence |
| Tag name collision | Increment N and retry (should not happen if using the auto-numbering) |
| Tag already exists remotely | Warn if local and remote messages differ |
| Amend on non-existent tag | Report the tag doesn't exist; suggest listing |
| User rejects changelog | Allow reword of specific items or full rewrite |

## Agent output conventions

After each operation, report a structured summary:

```text
✓ Tag stab9 created
  Message: stab9 follow stab8, 1. 重构lib目录结构; 2. 新增cctag技能 [Claude Code]
  Pushed:  yes (origin)
  Files:   5 changed, 120 insertions(+), 45 deletions(-)
```

For listing:

```text
stab9  2026-07-09  重构lib目录结构; 新增cctag技能
stab8  2026-07-08  新增xxx功能; 修复yyy
stab7  2026-07-07  ...
stab0  2026-07-01  初始化配置仓库
```
