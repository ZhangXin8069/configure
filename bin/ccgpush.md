# ccgpush — Git push with auto-generated stab tag

Stage all changes, commit, create an annotated `stab<N>` tag with a structured changelog, and push everything.

## Tag format

```
stab<N> follow stab<N-1>, 1. 变更说明1; 2. 变更说明2; 3. 变更说明3; ...... [Claude Code]
```

For the first tag (`stab0`), use `stab0 init, 1. ... [Claude Code]`.

## Procedure

### 1. Determine the next tag number

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

### 2. Review changes since last tag

If a previous stab tag exists, review changes since that tag:

```bash
git log ${LAST_STAB}..HEAD --oneline --no-merges
git diff ${LAST_STAB}..HEAD --stat
```

If this is the first tag, review recent commits:

```bash
git log --oneline --no-merges -20
git diff --stat HEAD~10..HEAD 2>/dev/null || git diff --stat HEAD
```

### 3. Build the changelog

Analyze the diffs and commit messages to produce a **numbered Chinese changelog**. Each item should be one concise sentence summarizing a logical group of changes. Use `; ` (Chinese semicolon) as the separator.

Guidelines for changelog items:
- Group related file changes into one item (e.g., all env.sh refactors in one item)
- Order by importance: structural/architectural changes first, then new features, then fixes/cleanups
- Keep each item to one line, no nested lists
- Omit trivial/internal-only changes (whitespace, comments)

### 4. Stage, commit, and tag

```bash
# Stage everything
git add -A

# Commit (skip if nothing to commit)
COMMIT_MSG="$(date "+%Y-%m-%d-%H-%M-%S") [Claude Code]"
git commit -m "$COMMIT_MSG"

# Create annotated tag
git tag -a "$NEW_TAG" -m "$TAG_MESSAGE"
```

### 5. Push

```bash
git push origin --tags
git push
```

## Amend mode

When the user says `--amend` or asks to amend/reword the last tag:

1. Delete the local tag: `git tag -d <last_stab>`
2. Delete the remote tag: `git push origin :refs/tags/<last_stab>`
3. Re-create with the updated changelog, reusing the same tag number
4. Push again: `git push origin --tags`

## No changes to commit

If `git diff --cached --quiet` shows no staged changes but the tag needs updating (e.g., amend mode), skip the commit and only create/push the tag.

## Confirmation

Always show the final tag and message to the user and ask for confirmation before creating the tag:

```
Tag:     stab9
Message: stab9 follow stab8, 1. 重构env.sh...; 2. 新增xxx... [Claude Code]

Proceed? [Y/n]
```
