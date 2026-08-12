---
name: tag
description: |
  Git 标签管理技能，管理三类独立编号的标签：stab<N>（稳定里程碑）、dev<N>（开发快照）、bug<N>（修复标记），
  支持子版本标签如 stab15_1（stab15 的后续修订）。
  当用户要求打标签、创建/应用 tag（"打标签"、"tag"、"标记一下"、"版本标记"、"子版本"）、
  暂存进度（"dev"、"暂存"、"保存进度"、"快照"）、标记完成（"stab"、"完成"、"稳定版"）、
   修复打标（"bug"、"修复"、"补丁"），或查看/列出/搜索标签（"查看tag"、"list tags"）、
   查看标签详情（"tag详情"）、删除标签（"删除tag"）、修改/重写标签（"修改tag"、"amend"）时使用此 skill。
   description 中未明确类型时按上下文自动推断：bug/修复→bug，dev/暂存/快照→dev，否则默认 stab。
   创建/改写标签后默认自动推送当前分支与标签到远程（无需逐次确认）；破坏性操作（删除/改写已推送标签）先确认。
metadata:
  openclaw:
    emoji: 🏷️
---

# tag — Git tag management with three tag types

## 核心原则

1. **先看后打**：打标签前先分析基线以来的变更，构建诚实、分组的变更清单，不臆造内容。
2. **先推后打，默认同步远程**：打标签**之前**先 `git push origin <当前分支>`（确保远程已包含即将被打标的提交），
   创建/改写标签**之后**再 `git push origin <标签>`；全部**默认执行、无需逐次确认**。
   仅当无远程或用户明确要求仅本地（local-only）时跳过。push 失败自动重试并记入会话日志。
3. **操作前确认**：创建前展示拟用消息；删除/改写（尤其已推送的标签）等破坏性操作必须先经用户确认。
4. **注释标签**：一律 `git tag -a`，消息格式严格遵循约定（follow 链、编号项以 `;` 结尾、
   ` [opencode].` 后缀）。
5. **类型推断，歧义就问**：按上下文自动推断 stab/dev/bug；无法确定时提问，不擅断。
6. **循环尝试直至成功**：push/删除失败、标签冲突、重命名冲突时定位原因重试，
   直至成功或用户终止；失败与重试记入会话日志。
7. **破坏性操作预警**：改写/删除已推送标签会重写他人历史，先警告再执行。

## 会话日志

每次 tag 会话必须在**当前工作目录（仓库根）**生成详细日志：

- 文件名格式：`.tag.<时间戳>.log`（例如 `.tag.2026-08-12-19-19-43.log`）
- 时间戳格式：`%Y-%m-%d-%H-%M-%S`：`TS=$(date +%Y-%m-%d-%H-%M-%S)`
- 日志**不入库**（与仓库 `.agent.*.log` 约定一致），全程**追加**写入（`>>`）
- 记录内容：操作类型与目标标签、基线、拟用消息、用户确认结果、push/删除结果、
  失败与重试原因、最终汇总

Manage annotated tags across three categories — `stab<N>`, `dev<N>`, `bug<N>` — each with independent numbering, plus optional sub-versions (`stab15_1`). Supports create, list, show, delete, and amend. Designed for Agent invocation — every operation returns structured output and handles edge cases explicitly.

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
  - "stab15_1" / "子版本" / "修订" / "在stab15上补标签" → sub-version of that major (e.g. `stab15_2`)
- List or search existing tags ("查看tag", "list tags", "有哪些标签")
- Show tag details ("tag详情", "show tag stab3")
- Delete a tag ("删除tag", "delete tag stab5")
- Amend/reword a tag ("修改tag", "amend tag", "重写tag内容")

**Auto-detection**: When the user doesn't explicitly specify a type, infer from context:
- Mentioning a full tag name with an underscore (e.g. "stab15_1", "删掉 dev2_1") → that sub-version tag, used verbatim
- Mentioning "子版本" / "修订" / "sub" + a major tag (e.g. "stab15的子版本") → next sub-version of that major
- Mentioning "bug"/"修复"/"fix"/"补丁"/"问题" → `bug`
- Mentioning "dev"/"暂存"/"保存"/"快照"/"继续" → `dev`
- Mentioning "stab"/"完成"/"稳定"/"版本"/"发布" or no clear signal → `stab` (default)

If ambiguous, ask: "Which tag type? [stab/dev/bug]"

## Tag naming convention

```text
stab0, stab1, stab2, ... stabN, stabN_1, stabN_2, ...   (stable checkpoints)
dev0, dev1, dev2, ... devN, devN_1, ...                 (development snapshots)
bug0, bug1, bug2, ... bugN, bugN_1, ...                 (bug fixes)
```

All counters start from 0 and increment independently. The first tag in each category uses `<type>0`.

**Full grammar**: `^(stab|dev|bug)[0-9]+(_[0-9]+)?$` — e.g. `stab15`, `stab15_1`, `dev3_2`.

## Sub-version tags (`<type><N>_<M>`)

A sub-version is a **follow-up revision on top of an existing major tag** without advancing the major counter. It is used for small targeted fixes or iterations after a major tag is already placed.

- `stab15_1` = first sub-version of `stab15`; it belongs to type `stab` and major `15`.
- Minor `M` starts at **1** (`stab15_1` is the first sub-version of `stab15`; `_0` is never used).
- Message format is identical to any other tag: `follow stab15, 1. 修复...; [opencode].` — the `follow <previous-tag-of-any-type>` rule makes the parent major (or the previous sub-version) the natural predecessor.
- Version sort (`--sort=-v:refname`) orders them correctly: `stab15 < stab15_1 < stab15_2 < stab16`.
- Sub-versions are **explicit requests only** — auto-numbering (Case C below) always produces a plain major tag. If the latest tag is `stab15_1`, auto-creating a `stab` tag yields `stab16`, not `stab15_2`. To get another sub-version, say so explicitly (e.g. "在 stab15 上再补一个标签").

## Tag message format

Every tag is an **annotated tag** with the following message format:

```text
follow <previous-tag-of-any-type>, 1. 变更说明一; 2. 变更说明二; 3. 变更说明三; [opencode].
```

- The **very first tag** in the repo uses `<type>0 init, 1. ...; [opencode].` (no predecessor)
- **All subsequent tags** (regardless of type) use `follow <previous-tag>, 1. ...;` — references the immediately previous tag regardless of type
- Changelog items are numbered with English period + space (`1. `, `2. `, `3. `)
- **Every item ends with `;`** (English semicolon), including the last item — no exceptions
- All punctuation is English: `.` `,` `;` (the content text itself may be Chinese)
- The suffix ` [opencode].` (preceded by a space, trailing English period) is always appended
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
follow stab8, 1. 重构lib目录结构，统一版本化配置模式; 2. 新增cctag Agent技能，替代ccgpush; 3. 修复zshrc中oh-my-zsh插件加载顺序; 4. 清理bin/中过期脚本; [opencode].
```

---

## Operations

### 1. Create a new tag

This is the primary operation. It determines the tag type, analyzes changes since the last tag of that type, builds a changelog, and creates an annotated tag.

#### Step 1.1 — Determine tag type and next number

Determine the tag type (`TYPE`): one of `stab`, `dev`, or `bug`. Use auto-detection rules from the Trigger section. If ambiguous, ask the user.

Then handle one of three cases:

**Case A — Explicit full tag name**: The user names the tag exactly (e.g. "打 stab15_1 标签"). Use it verbatim:

```bash
NEW_TAG="stab15_1"   # user-specified, must match ^(stab|dev|bug)[0-9]+(_[0-9]+)?$
if git rev-parse -q --verify "refs/tags/${NEW_TAG}" >/dev/null; then
    echo "Tag ${NEW_TAG} already exists — offer to amend it or use the next number"
fi
```

**Case B — Generic sub-version request**: The user wants a follow-up on an existing major tag without naming the minor (e.g. "在 stab15 上补一个标签" / "stab15 的子版本"). Compute the next minor of that major (minors start at 1):

```bash
TYPE="stab"; MAJOR=15   # from user input
SUB_TAGS=$(git tag -l "${TYPE}${MAJOR}_[0-9]*" --sort=-v:refname)
if [ -z "$SUB_TAGS" ]; then
    NEXT_MINOR=1
else
    LAST_SUB=$(echo "$SUB_TAGS" | head -1)
    NEXT_MINOR=$(($(echo "$LAST_SUB" | sed "s/^${TYPE}${MAJOR}_//") + 1))
fi
NEW_TAG="${TYPE}${MAJOR}_${NEXT_MINOR}"
```

**Case C — Auto-numbering**: No explicit name or sub-version request. Find the latest tag of this type, **strip any `_M` suffix**, and take the next **major**. A sub-version tag counts toward its own major, so after `stab15_1` the next auto tag is `stab16`:

```bash
TYPE="stab"   # or dev, bug — determined in the step above
LAST_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | grep -E "^${TYPE}[0-9]+(_[0-9]+)?$" | head -1)
if [ -z "$LAST_TAG" ]; then
    NEW_NUM=0
else
    LAST_NUM=$(echo "$LAST_TAG" | sed "s/^${TYPE}//" | cut -d_ -f1)
    NEW_NUM=$((LAST_NUM + 1))
fi
NEW_TAG="${TYPE}${NEW_NUM}"
```

**Edge case**: Tags sharing the prefix but not numeric-suffixed (e.g. `stab-final`) are excluded by the `grep -E` filter and do not affect numbering.

#### Step 1.2 — Review changes since baseline

The **baseline** is the most recent tag of **any type** (stab, dev, or bug). If no tags exist, use the first commit.

```bash
# Baseline = latest tag of ANY type (sub-version tags included; version sort
# places them above their parent, so stab15_1 is picked over stab15)
BASELINE=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug)[0-9]+(_[0-9]+)?$' | head -1)
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
Message: follow stab9, 1. 初步实现xxx功能; 2. 添加yyy模块框架; [opencode].
Changes: 3 files changed, 85 insertions(+), 12 deletions(-)

Proceed? [Y/n]
```

**If the user rejects**, ask what to change — reword a specific item, add a missing item, or remove an item.

#### Step 1.4 — Push current commits (before tag)

**打标签的前置必需步骤**：先 push 当前分支，确保远程已包含即将被打标的提交，之后才能执行 Step 1.5 创建标签。**默认执行，无需确认**；push 失败按循环重试原则处理并记入日志，重试仍未成功则**暂停打标签并报告用户**，不创建指向本地独有提交的标签：

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"
```

**Edge case — no remote**: If `git remote` is empty, skip all push steps and note that no remote is configured.

#### Step 1.5 — Create the tag

```bash
git tag -a "$NEW_TAG" -m "$TAG_MESSAGE"
```

Verify creation:

```bash
git tag -l "$NEW_TAG"                        # Confirm tag exists
git tag -l --format='%(subject)' "$NEW_TAG"  # Show the tag message
```

#### Step 1.6 — Push the tag (after tag)

After creating the tag, push it to remote. **默认执行，无需确认**（push 失败自动重试并记入日志）：

```bash
git push origin "$NEW_TAG"
```

---

### 2. List tags

List tags, optionally filtered by type:

```bash
# List all tags (all three types, sub-versions included)
git tag -l --sort=-v:refname --format='%(refname:short) | %(taggername) | %(taggerdate:short) | %(subject)' | grep -E '^(stab|dev|bug)[0-9]+(_[0-9]+)?$'

# Filter by type (e.g., only stab tags) — sub-versions are included
TYPE="dev"
git tag -l "${TYPE}[0-9]*" --sort=-v:refname --format='%(refname:short) | %(taggerdate:short) | %(subject)'

# Count by type (sub-versions count toward their type)
git tag -l 'stab[0-9]*' | wc -l
git tag -l 'dev[0-9]*'  | wc -l
git tag -l 'bug[0-9]*'  | wc -l
```

Output format (grouped by type, sub-version listed above its parent):

```text
=== stab (4 tags) ===
stab15_1 | 2026-08-07 | follow stab15, 1. 修复set-env.sh相对路径引用; [opencode].
stab15   | 2026-08-07 | follow stab14, 1. 新增save-env.sh脚本; 2. ...; [opencode].
stab9    | 2026-07-09 | follow stab8, 1. 重构lib目录结构; 2. ...
stab0    | 2026-07-01 | stab0 init, 1. 初始化配置仓库; [opencode].

=== dev (2 tags) ===
dev1   | 2026-07-09 | follow bug0, 1. 实现xxx模块框架; [opencode].
dev0   | 2026-07-09 | follow stab3, 1. 开始yyy功能开发; [opencode].

=== bug (1 tag) ===
bug0   | 2026-07-09 | follow dev1, 1. 修复zzz空指针异常; [opencode].
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

# Show commits between this tag and its predecessor (any type, sub-versions included)
PREV_TAG=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug)[0-9]+(_[0-9]+)?$' | grep -A1 "^$TAG_NAME$" | tail -1)
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
# User-specified tag (sub-versions work the same, e.g. "stab15_1")
TARGET_TAG="dev2"   # from user input

# Or amend latest of a given type
TYPE="stab"   # from user input or auto-detected
TARGET_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | grep -E "^${TYPE}[0-9]+(_[0-9]+)?$" | head -1)
```

#### Step 5.2 — Show current tag content

```bash
git tag -l --format='%(subject)' "$TARGET_TAG"
```

#### Step 5.3 — Review changes since the tag's predecessor

Use the immediate predecessor tag of any type as baseline (same logic as Step 1.2).

#### Step 5.4 — Build new message

Propose a new message. This may be entirely rewritten or just partially edited — follow the user's instructions. Keep the same tag type.

#### Step 5.5 — Push current commits, replace tag, push tag

**改写已推送标签属破坏性操作，整体流程须先经用户确认（见核心原则与下方 Warning）；确认之后推送步骤默认执行，不再逐次询问**：

```bash
# Push current branch first
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"

# Delete old tag locally
git tag -d "$TARGET_TAG"

# Delete old tag remotely
git push origin :refs/tags/"$TARGET_TAG" 2>/dev/null

# Re-create with new message (at the same commit)
git tag -a "$TARGET_TAG" -m "$NEW_MESSAGE"

# Push updated tag
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

Proceed with Steps 1.1–1.6, substituting `$BASE_REF` for the baseline.

---

## Error handling summary

| Scenario | Action |
| --- | --- |
| Ambiguous tag type | Ask user: "Which tag type? [stab/dev/bug]" |
| User names a sub-version tag (e.g. `stab15_1`) | Recognize verbatim; use for show/delete/amend/create |
| Requested sub-version tag already exists | Report; offer amend or the next minor number |
| Auto-numbering after a sub-version tag | Next major (`stab15_1` → `stab16`); request `stab15_2` explicitly for another sub-version |
| No previous tags at all | Use first commit as baseline |
| No commits in repo | Abort; report nothing to tag |
| No changes since baseline | Report and ask user whether to proceed |
| No remote configured | Skip both push steps; note the absence |
| Branch push before tagging fails | Diagnose, fix, retry; if still failing, pause and report — do not create the tag |
| User requests local-only | Create/amend locally only, skip push; record in session log |
| Tag name collision | Increment N and retry (should not happen with auto-numbering) |
| Tag already exists remotely | Warn if local and remote messages differ |
| Amend on non-existent tag | Report the tag doesn't exist; suggest listing |
| Push/create/delete fails (network, conflict) | Diagnose from error, fix, and retry (loop until success); record attempts in the session log |
| User rejects changelog | Allow reword of specific items or full rewrite |

## Agent output conventions

After each operation, report a structured summary:

```text
✓ Tag dev3 created
  Type:    dev
  Message: follow stab9, 1. 实现xxx模块框架; 2. 添加yyy接口; [opencode].
  Pushed:  yes (origin)
  Files:   3 changed, 85 insertions(+), 12 deletions(-)
  Log:     .tag.2026-08-12-19-19-43.log (retries 0)
```

For listing:

```text
stab9  2026-07-09  follow stab8, 1. 重构lib目录结构; 2. 新增cctag技能; [opencode].
stab8  2026-07-08  follow stab7, 1. 新增xxx功能; 2. ...;
dev1   2026-07-09  follow bug0, 1. 实现xxx模块框架; [opencode].
dev0   2026-07-09  follow stab3, 1. 开始yyy功能开发; [opencode].
bug0   2026-07-09  follow dev1, 1. 修复zzz空指针异常; [opencode].
```

## 注意事项

- 操作结果以实测为准（`git tag -l`、`git push` 输出），不虚报已推送/已创建；
- 不代用户提交代码；创建/改写标签后**默认自动**推送当前分支与标签到远程（无需逐次确认），
  push 失败自动重试并记入会话日志；其他机器由用户自行 `git fetch --tags` 同步；
- 会话日志 `.tag.<时间戳>.log` 不入库，由用户决定保留或清理。
