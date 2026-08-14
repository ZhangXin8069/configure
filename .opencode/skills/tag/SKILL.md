---
name: tag
description: |
  Git 标签管理技能，管理四类独立编号的标签：stab<N>（稳定里程碑）、dev<N>（开发快照）、bug<N>（修复标记）、test<N>（测试标记），
  支持子版本标签如 stab15_1（stab15 的后续修订）。
  当用户要求打标签、创建/应用 tag（"打标签"、"tag"、"标记一下"、"版本标记"、"子版本"）、
  暂存进度（"dev"、"暂存"、"保存进度"、"快照"）、标记完成（"stab"、"完成"、"稳定版"）、
  修复打标（"bug"、"修复"、"补丁"）、测试打标（"test"、"测试"、"测试完成"），或查看/列出/搜索标签（"查看tag"、"list tags"）、
  查看标签详情（"tag详情"）、删除标签（"删除tag"）、修改/重写标签（"修改tag"、"amend"）时使用此 skill。
metadata:
  openclaw:
    emoji: 🏷️
---

# tag — Git 四类标签管理技能

## 核心原则

1. **先看后打**：打标签前先分析基线以来的变更，构建诚实、分组的变更清单，不臆造内容。
2. **先推后打，默认同步远程**：打标签**之前**先 `git push origin <当前分支>`（确保远程已包含即将被打标的提交），
   创建/改写标签**之后**再 `git push origin <标签>`；全部**默认执行、无需逐次确认**。
   仅当无远程或用户明确要求仅本地（local-only）时跳过。push 失败自动重试并记入会话日志。
3. **非必要不确认**：创建标签时展示拟用消息后**直接执行**，不阻塞等待确认；仅破坏性操作
   （删除/改写已推送标签）与类型歧义时询问用户。
4. **注释标签**：一律 `git tag -a`，消息格式严格遵循约定（follow 链、编号项以 `;` 结尾、
   ` [opencode].` 后缀）。
5. **类型推断，歧义一次问清**：按上下文自动推断 stab/dev/bug；无法确定时**一次性列出候选类型与全部歧义点**提问，不逐次追问。
6. **循环尝试直至成功**：push/删除失败、标签冲突、重命名冲突时定位原因重试，
   直至成功或用户终止；失败与重试记入会话日志。
7. **破坏性操作预警**：改写/删除已推送标签会重写他人历史，先警告再执行。

## 会话日志

每次 tag 会话必须在**当前工作目录（仓库根）**生成详细日志：

- 文件名格式：`.tag.<时间戳>.log`（例如 `.tag.2026-08-12-19-19-43.log`）
- 时间戳格式：`%Y-%m-%d-%H-%M-%S`：`TS=$(date +%Y-%m-%d-%H-%M-%S)`
- 日志**不入库**（与仓库 `.agent.*.log` 约定一致），全程**追加**写入（`>>`）
- 记录内容（**会话头**）：
  1. 开始时间、工作目录、git 分支与 HEAD（`git rev-parse --abbrev-ref HEAD`、`git log -1 --oneline`）、
     操作请求（打/列/看/删/改 + 目标标签）；
- 记录内容（**过程**）：
  2. 类型判定与编号计算过程（输入信号 → 推断类型 → LAST_TAG/LAST_NUM → NEW_TAG）；
  3. 基线标签与变更调查输出（`git log <基线>..HEAD`、`git diff --stat` 统计）；
  4. 关键命令与实际输出（`$ <命令>` + `exit=<退出码>`），如 `git tag -l`、`git push`、`git tag -d`；
  5. 用户确认结果（如有询问）；push/创建/删除/改写结果；每次失败与重试：失败命令、
     错误输出、重试命令与次数；
- 记录内容（**会话尾**）：
  6. 最终汇总（结构化输出）；结束时间、总耗时；遗留项（如未推送、本地独有标签）与下一步建议。

**记录规范**：关键事件以分隔行标记 `---- [YYYY-MM-DD HH:MM:SS] 事件描述 ----`；
命令统一记作 `$ <命令>` 并在结果行标注退出码；全程不覆盖、只追加。

## 历史日志预读（关键信息速览）

会话**第一步**只读预读本技能**最新一份**历史日志的**尾部汇总区**（只关注关键信息，不做深入解析）：

```bash
tail -20 "$(ls -1t .tag.*.log 2>/dev/null | head -1)"   # 尾部汇总区：上次任务/结论/遗留项
```

- 关键信息：① 上次任务/对象；② 结论或收敛结果；③ 遗留项与下一步建议——其余（过程轮次、命令细节）一律跳过，不做深入 think
- 约束：只读不改；无历史日志（首次运行）时正常跳过，不视为错误；总耗时以秒级为限

## 四类标签

| 类型 | 用途 | 使用时机 |
| --- | --- | --- |
| `stab<N>` | 稳定里程碑 | 某工作**已完成**且稳定。这是里程碑。 |
| `dev<N>` | 开发快照 | 工作**进行中**——继续前保存当前状态。 |
| `bug<N>` | 修复标记 | 发现 **bug** 并已修复。标记修复点。 |
| `test<N>` | 测试标记 | **测试**相关工作已完成（新增/通过/回归）。标记测试点。 |

每类标签有**独立计数器**，从 0 开始。`stab0`、`dev0`、`bug0` 可以同时存在。

## 触发时机

用户提出以下请求时调用本技能：

- 创建/应用标签（"打标签"、"tag"、"标记一下"、"版本标记"）
  - "stab" / "稳定版" / "完成了" / "完成" → `stab<N>`
  - "dev" / "开发中" / "暂存" / "保存进度" / "快照" → `dev<N>`
  - "bug" / "修复" / "修bug" / "补丁" / "fix" → `bug<N>`
  - "test" / "测试" / "测试完成" / "回归通过" → `test<N>`
  - "stab15_1" / "子版本" / "修订" / "在stab15上补标签" → 该主版本号的子版本（如 `stab15_2`）
- 列出或搜索已有标签（"查看tag"、"list tags"、"有哪些标签"）
- 查看标签详情（"tag详情"、"show tag stab3"）
- 删除标签（"删除tag"、"delete tag stab5"）
- 改写/重写标签（"修改tag"、"amend tag"、"重写tag内容"）

**自动推断**：用户未明确指定类型时，按上下文推断：
- 提到带下划线的完整标签名（如 "stab15_1"、"删掉 dev2_1"）→ 该子版本标签，原样使用
- 提到 "子版本" / "修订" / "sub" + 主版本标签（如 "stab15的子版本"）→ 该主版本的下一子版本
- 提到 "bug"/"修复"/"fix"/"补丁"/"问题" → `bug`
- 提到 "test"/"测试"/"回归"/"验证" → `test`
- 提到 "dev"/"暂存"/"保存"/"快照"/"继续" → `dev`
- 提到 "stab"/"完成"/"稳定"/"版本"/"发布" → `stab`
- 无明确信号 → `dev`（默认）

无法确定时**一次性列出全部候选**提问："Which tag type? [stab/dev/bug/test]"（含全部歧义点，不逐次追问）

## 标签命名约定

```text
stab0, stab1, stab2, ... stabN, stabN_1, stabN_2, ...   (稳定里程碑)
dev0, dev1, dev2, ... devN, devN_1, ...                 (开发快照)
bug0, bug1, bug2, ... bugN, bugN_1, ...                 (修复标记)
test0, test1, test2, ... testN, testN_1, ...            (测试标记)
```

所有计数器从 0 开始独立递增。每类第一个标签用 `<type>0`。

**完整文法**：`^(stab|dev|bug|test)[0-9]+(_[0-9]+)?$` —— 如 `stab15`、`stab15_1`、`dev3_2`。

## 子版本标签（`<type><N>_<M>`）

子版本是**在既有主版本标签之上的后续修订**，不推进主版本计数器。用于主版本标签已放置后的小型定向修复或迭代。

- `stab15_1` = `stab15` 的第一个子版本；属于类型 `stab`、主版本号 `15`。
- 子版本号 `M` 从 **1** 开始（`stab15_1` 是 `stab15` 的第一个子版本；`_0` 从不使用）。
- 消息格式与其他标签完全一致：`follow stab15, 1. 修复...; [opencode].` —— `follow <任意类型的前一标签>` 规则使父主版本（或前一子版本）成为自然前驱。
- 版本排序（`--sort=-v:refname`）正确排序：`stab15 < stab15_1 < stab15_2 < stab16`。
- 子版本**仅显式请求**——自动编号（下文 Case C）总是产生普通主版本标签。若最新标签是 `stab15_1`，自动创建 `stab` 标签得到 `stab16` 而非 `stab15_2`。要再打子版本需显式说明（如 "在 stab15 上再补一个标签"）。

## 标签消息格式

每个标签都是**注释标签**，消息格式如下：

```text
follow <任意类型的前一标签>, 1. 变更说明一; 2. 变更说明二; 3. 变更说明三; [opencode].
```

- 仓库中**第一个标签**使用 `<type>0 init, 1. ...; [opencode].`（无前驱）
- **后续所有标签**（无论类型）使用 `follow <前一标签>, 1. ...;` —— 引用紧邻的前一标签，不论其类型
- 变更项用英文句点 + 空格编号（`1. `、`2. `、`3. `）
- **每项以 `;` 结尾**（英文分号），包括最后一项——无例外
- 所有标点用英文：`.` `,` `;`（内容文字本身可为中文）
- 后缀 ` [opencode].`（前有空格、后接英文句点）始终追加
- 消息作为标签注释存储（`git tag -a -m "..."`）

### 变更项编写准则

从 diff 与提交信息构造变更项时：

1. **相关改动分组**——同一子系统/功能的全部改动算一项
2. **按重要性排序**——结构/架构 → 新功能 → 修复 → 清理
3. **每项一句话**——不嵌套列表、不多行
4. **省略琐碎改动**——空白、纯注释、生成文件
5. **用动作导向措辞**——"重构env.sh加载逻辑" 而非 "env.sh被修改了"

示例：

```text
follow stab8, 1. 重构lib目录结构，统一版本化配置模式; 2. 新增cctag Agent技能，替代ccgpush; 3. 修复zshrc中oh-my-zsh插件加载顺序; 4. 清理bin/中过期脚本; [opencode].
```

## 操作

### 1. 创建新标签

这是主要操作。确定标签类型，分析该类型最近标签以来的变更，构建变更清单，创建注释标签。

#### Step 1.1 — 确定标签类型与下一个编号

确定标签类型（`TYPE`）：`stab`、`dev`、`bug`、`test` 之一。按「触发时机」的自动推断规则确定；有歧义时**一次性列出全部候选类型与歧义点**询问用户，不逐次追问。

然后处理三种情形之一：

**Case A — 显式完整标签名**：用户精确指定标签名（如 "打 stab15_1 标签"）。原样使用：

```bash
NEW_TAG="stab15_1"   # 用户指定，必须匹配 ^(stab|dev|bug|test)[0-9]+(_[0-9]+)?$
if git rev-parse -q --verify "refs/tags/${NEW_TAG}" >/dev/null; then
    echo "Tag ${NEW_TAG} already exists — offer to amend it or use the next number"
fi
```

**Case B — 泛化子版本请求**：用户想在既有主版本标签上补打而不指定子版本号（如 "在 stab15 上补一个标签" / "stab15 的子版本"）。计算该主版本的下一子版本号（子版本从 1 开始）：

```bash
TYPE="stab"; MAJOR=15   # 来自用户输入
SUB_TAGS=$(git tag -l "${TYPE}${MAJOR}_[0-9]*" --sort=-v:refname)
if [ -z "$SUB_TAGS" ]; then
    NEXT_MINOR=1
else
    LAST_SUB=$(echo "$SUB_TAGS" | head -1)
    NEXT_MINOR=$(($(echo "$LAST_SUB" | sed "s/^${TYPE}${MAJOR}_//") + 1))
fi
NEW_TAG="${TYPE}${MAJOR}_${NEXT_MINOR}"
```

**Case C — 自动编号**：无显式名称或子版本请求。找出该类型的最近标签，**去掉任何 `_M` 后缀**，取下一个**主版本号**。子版本标签计入其主版本，所以 `stab15_1` 之后自动创建的是 `stab16`：

```bash
TYPE="stab"   # 或 dev、bug、test——由上一步确定
LAST_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | grep -E "^${TYPE}[0-9]+(_[0-9]+)?$" | head -1)
if [ -z "$LAST_TAG" ]; then
    NEW_NUM=0
else
    LAST_NUM=$(echo "$LAST_TAG" | sed "s/^${TYPE}//" | cut -d_ -f1)
    NEW_NUM=$((LAST_NUM + 1))
fi
NEW_TAG="${TYPE}${NEW_NUM}"
```

**边界情形**：共享前缀但非数字后缀的标签（如 `stab-final`）被 `grep -E` 过滤排除，不影响编号。

#### Step 1.2 — 查看基线以来的变更

**基线** = 最近一个**任意类型**（stab/dev/bug/test）的标签。若无标签，用第一个提交。

```bash
# 基线 = 任意类型的最新标签（含子版本标签；版本排序将其排在父标签之上，
# 所以 stab15_1 优先于 stab15 被选中）
BASELINE=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug|test)[0-9]+(_[0-9]+)?$' | head -1)
# 无标签时用第一个提交
if [ -z "$BASELINE" ]; then
    BASELINE=$(git rev-list --max-parents=0 HEAD)
fi
```

查看变更：

```bash
# 基线以来的提交
git log ${BASELINE}..HEAD --oneline --no-merges

# 变更文件
git diff ${BASELINE}..HEAD --stat

# 完整 diff 用于详细分析（限制 500 行）
git diff ${BASELINE}..HEAD -- . | head -500
```

**边界情形 — 无历史提交**：仓库尚无提交时跳过 diff 查看，变更清单直接写"初始提交"。

**边界情形 — 基线以来无变更**：`git diff ${BASELINE}..HEAD --stat` 为空时告知用户没有可打标的新变更。除非用户明确要求，否则**不创建空标签**。

#### Step 1.3 — 构建变更清单

分析收集到的 diff 与提交信息生成标签消息，套用上文变更项编写准则。

- `bug` 标签：聚焦什么坏了、如何修复、影响范围。
- `test` 标签：聚焦测试了什么（新增/回归/覆盖项）、结果如何。
- `dev` 标签：描述已做工作、仍在进行中的部分（可选）与当前状态。
- `stab` 标签：全面描述已完成的工作。

展示拟用消息，然后**直接继续——默认不等待确认**，展示后直接进入 Step 1.4：

```text
Type:    dev
Tag:     dev3
Message: follow stab9, 1. 初步实现xxx功能; 2. 添加yyy模块框架; [opencode].
Changes: 3 files changed, 85 insertions(+), 12 deletions(-)
→ 展示后直接创建并推送，不阻塞等待确认。
```

**若用户介入/否决**，询问要改什么——重写某一条、补一条缺失项或删除某项。

#### Step 1.4 — 先推送当前提交（打标签前）

**打标签的前置必需步骤**：先 push 当前分支，确保远程已包含即将被打标的提交，之后才能执行 Step 1.5 创建标签。**默认执行，无需确认**；push 失败按循环重试原则处理并记入日志，重试仍未成功则**暂停打标签并报告用户**，不创建指向本地独有提交的标签：

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"
```

**边界情形 — 无远程**：`git remote` 为空时跳过所有 push 步骤并注明未配置远程。

#### Step 1.5 — 创建标签

```bash
git tag -a "$NEW_TAG" -m "$TAG_MESSAGE"
```

验证创建：

```bash
git tag -l "$NEW_TAG"                        # 确认标签存在
git tag -l --format='%(subject)' "$NEW_TAG"  # 显示标签消息
```

#### Step 1.6 — 推送标签（打标签后）

创建标签后推送到远程。**默认执行，无需确认**（push 失败自动重试并记入日志）：

```bash
git push origin "$NEW_TAG"
```

---

### 2. 列出标签

列出标签，可按类型过滤：

```bash
# 列出全部标签（四类全部，含子版本）
git tag -l --sort=-v:refname --format='%(refname:short) | %(taggername) | %(taggerdate:short) | %(subject)' | grep -E '^(stab|dev|bug|test)[0-9]+(_[0-9]+)? \|'

# 按类型过滤（如仅 stab 标签）——子版本包含在内
TYPE="dev"
git tag -l "${TYPE}[0-9]*" --sort=-v:refname --format='%(refname:short) | %(taggerdate:short) | %(subject)'

# 按类型计数（子版本计入其类型）
git tag -l 'stab[0-9]*' | wc -l
git tag -l 'dev[0-9]*'  | wc -l
git tag -l 'bug[0-9]*'  | wc -l
git tag -l 'test[0-9]*' | wc -l
```

输出格式（按类型分组，子版本列在父标签之上；dev/bug/test 组同格式）：

```text
=== stab (4 tags) ===
stab15_1 | 2026-08-07 | follow stab15, 1. 修复set-env.sh相对路径引用; [opencode].
stab15   | 2026-08-07 | follow stab14, 1. 新增save-env.sh脚本; [opencode].
stab9    | 2026-07-09 | follow stab8, 1. 重构lib目录结构; [opencode].
stab0    | 2026-07-01 | stab0 init, 1. 初始化配置仓库; [opencode].
```

**边界情形 — 无标签**：报告 "No cctag tags found in this repository."

---

### 3. 查看单个标签

显示单个标签（任意类型）的详细信息：

```bash
# 显示标签注释
git tag -l --format='%(subject)%0a%(body)' "$TAG_NAME"

# 显示标签作者信息与日期
git tag -l --format='Type: %(refname:short)%0aAuthor: %(taggername) <%(taggeremail)>%0aDate: %(taggerdate:iso)%0aMessage: %(subject)' "$TAG_NAME"

# 显示该标签与其前驱之间的提交（任意类型，含子版本）
PREV_TAG=$(git tag -l --sort=-v:refname | grep -E '^(stab|dev|bug|test)[0-9]+(_[0-9]+)?$' | grep -A1 "^$TAG_NAME$" | tail -1)
if [ -n "$PREV_TAG" ]; then
    git log ${PREV_TAG}..${TAG_NAME} --oneline --no-merges
fi
```

**边界情形 — 标签不存在**：报告 "Tag 'xxx' does not exist. Use 'list' to see available tags."

**边界情形 — 该类型首个标签**：注明该类型没有可对比的前一标签。

---

### 4. 删除标签

在本地与远程同时删除标签：

```bash
# 删除前确认
git tag -l --format='%(subject)' "$TAG_NAME"

# 删除本地
git tag -d "$TAG_NAME"

# 删除远程（若存在于远程）
git push origin :refs/tags/"$TAG_NAME" 2>/dev/null
```

**边界情形 — 本地找不到标签**：检查远程：`git ls-remote --tags origin "$TAG_NAME"`。若远程存在而本地没有，先 fetch 再删除。

**边界情形 — 强制删除**：用户传入 `--force` 或标签已推送时，删除远程标签前必须显式确认——这是影响所有协作者的破坏性操作。

---

### 5. 改写标签

重写既有标签（任意类型）的消息：

#### Step 5.1 — 确定目标标签

```bash
# 用户指定的标签（子版本同理，如 "stab15_1"）
TARGET_TAG="dev2"   # 来自用户输入

# 或改写某类型的最新标签
TYPE="stab"   # 来自用户输入或自动推断
TARGET_TAG=$(git tag -l "${TYPE}[0-9]*" --sort=-v:refname | grep -E "^${TYPE}[0-9]+(_[0-9]+)?$" | head -1)
```

#### Step 5.2 — 显示当前标签内容

```bash
git tag -l --format='%(subject)' "$TARGET_TAG"
```

#### Step 5.3 — 查看标签前驱以来的变更

用任意类型的紧邻前驱标签作为基线（逻辑同 Step 1.2）。

#### Step 5.4 — 构建新消息

提出新消息。可整体重写或仅部分编辑——遵循用户指示。保持同一标签类型。

#### Step 5.5 — 推送当前提交、替换标签、推送标签

**改写已推送标签属破坏性操作，整体流程须先经用户确认（见核心原则与下方警告）；确认之后推送步骤默认执行，不再逐次询问**：

```bash
# 先推送当前分支
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"

# 删除旧标签（本地）
git tag -d "$TARGET_TAG"

# 删除旧标签（远程）
git push origin :refs/tags/"$TARGET_TAG" 2>/dev/null

# 以新消息重新创建（同一提交）
git tag -a "$TARGET_TAG" -m "$NEW_MESSAGE"

# 推送更新后的标签
git push origin "$TARGET_TAG"
```

**警告**：改写已推送标签会为任何已拉取旧标签的人重写历史。删除远程标签前必须警告用户。

---

### 6. 指定区间打标（cherry-pick）

用户想对两个特定点之间的变更打标签时：

```bash
# 使用指定的基线 ref
BASE_REF="stab5"         # 用户指定
HEAD_REF="HEAD"          # 默认，或用户指定
git log ${BASE_REF}..${HEAD_REF} --oneline --no-merges
git diff ${BASE_REF}..${HEAD_REF} --stat
```

以 `$BASE_REF` 替代基线，按 Steps 1.1–1.6 继续。

---

## 错误处理

| 场景 | 处理 |
| --- | --- |
| 标签类型有歧义 | **一次性列出全部候选**："Which tag type? [stab/dev/bug/test]" 及全部歧义点 |
| 用户指定子版本标签（如 `stab15_1`） | 原样识别；用于查看/删除/改写/创建 |
| 请求的子版本标签已存在 | 报告；提供改写或下一个子版本号 |
| 子版本标签之后自动编号 | 下一主版本（`stab15_1` → `stab16`）；要另一子版本须显式请求 `stab15_2` |
| 完全没有之前的标签 | 用第一个提交作为基线 |
| 仓库无提交 | 中止；报告无内容可打标签 |
| 基线以来无变更 | 报告；除非用户明确要求，否则不创建空标签 |
| 未配置远程 | 跳过两个 push 步骤；注明无远程 |
| 打标签前的分支推送失败 | 诊断、修复、重试；仍失败则暂停并报告——不创建标签 |
| 用户要求仅本地 | 仅本地创建/改写，跳过 push；记入会话日志 |
| 标签名冲突 | 递增编号重试（自动编号下不应发生） |
| 远程已有同标签 | 本地与远程消息不一致时警告 |
| 改写不存在的标签 | 报告标签不存在；建议列出 |
| push/创建/删除失败（网络、冲突） | 从错误诊断、修复并重试（循环直至成功）；重试记入会话日志 |
| 用户否决变更清单（介入） | 允许重写特定项或整体重写 |

## Agent 输出约定

每次操作后报告结构化汇总：

```text
✓ Tag dev3 created
  Type:    dev
  Message: follow stab9, 1. 实现xxx模块框架; 2. 添加yyy接口; [opencode].
  Pushed:  yes (origin)
  Files:   3 changed, 85 insertions(+), 12 deletions(-)
  Log:     .tag.2026-08-12-19-19-43.log (retries 0)
```

列出时：

```text
stab9  2026-07-09  follow stab8, 1. 重构lib目录结构; 2. 新增cctag技能; [opencode].
stab8  2026-07-08  follow stab7, 1. 新增xxx功能; 2. ...;
dev1   2026-07-09  follow bug0, 1. 实现xxx模块框架; [opencode].
dev0   2026-07-09  follow stab3, 1. 开始yyy功能开发; [opencode].
bug0   2026-07-09  follow dev1, 1. 修复zzz空指针异常; [opencode].
test0  2026-07-10  follow bug0, 1. 新增yyy回归测试; [opencode].
```

## 注意事项

- 操作结果以实测为准（`git tag -l`、`git push` 输出），不虚报已推送/已创建；
- 不代用户提交代码；创建/改写标签后**默认自动**推送当前分支与标签到远程（无需逐次确认），
  push 失败自动重试并记入会话日志；其他机器由用户自行 `git fetch --tags` 同步；
- 会话日志 `.tag.<时间戳>.log` 不入库，由用户决定保留或清理。
