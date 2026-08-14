---
name: init
description: |
  仓库/目录初始化技能：为仓库内目录创建或更新 AGENTS.md，归档其他 agent 的 init 文件
  （CLAUDE.md/CODEX.md/.claude 等），把 agent 生成内容对应的 skill 归档到技能目录。
  当用户要求初始化仓库或目录（"init"、"初始化"、"生成AGENTS.md"、"为每个目录生成AGENTS.md"、
  "归档agent配置"、"收集skill"、"整理仓库"）时使用此技能。
metadata:
  openclaw:
    emoji: 📦
---

# init — 逐目录初始化 AGENTS.md 并归档各 agent 的初始化文件

## TODO 管理（全局约定）

执行第一步用 **todowrite 工具**生成**详细 TODO 列表**：按任务分解为可独立验证的
子步骤、按依赖排序；**每完成一个子步骤立即调用 todowrite 更新状态**（进行中/完成）；
收尾时核对全部完成。约定全文见 `skills/AGENTS.md`「TODO 生成与实时更新约定」。

为本库的**每一个目录**执行初始化。

## 核心原则

1. **两阶段执行**：先只读调查（阶段 A），确认后再统一执行写操作（阶段 B），
   避免边扫边改导致信息丢失（如先重命名了 `.claude`，后续就无法再参考其内容）。
2. **先参考后归档**：归档对象仅作格式参考，任何 agent 文件/目录**先完整读取与复制，再重命名**。
3. **只复制，不移动**：skill 归集均为复制，原位置保留。
4. **幂等**：已归档（`*.bak`）与已归集内容不再处理；第二次运行应输出"无变更"。
5. **不确定就问，一次问全**：无法判定外来文件夹/agent 生成内容时询问用户，不臆断；
   所有问题在**第一次交互一次性全部提出**（编号列表），用户一次回答，不逐次追问。
6. **循环尝试直至成功**：阶段 B 中断或重命名冲突时重新运行即可收敛（幂等保证不重复处理）；
   多次失败向用户报告进展，不无限循环。
7. **全局配置禁区**：仅处理本库范围内内容；全局目录（`~/.claude`、`~/.codex` 等）只参考、不重命名。

## 会话日志

每次 init 会话必须在**本库根目录**生成详细日志：

- 文件名格式：`.init.<时间戳>.log`（例如 `.init.2026-08-12-19-19-43.log`）
- 时间戳格式：`%Y-%m-%d-%H-%M-%S`：`TS=$(date +%Y-%m-%d-%H-%M-%S)`
- 日志**不入库**（与仓库 `.agent.*.log` 约定一致），全程**追加**写入（`>>`）
- 记录内容（**会话头**）：
  1. 开始时间、工作目录、git 分支与 HEAD（`git rev-parse --abbrev-ref HEAD`、`git log -1 --oneline`）、
     触发任务描述；
- 记录内容（**过程**）：
  2. 扫描目录清单；待处理清单（新建/更新 AGENTS.md、归档、skill 归集、重命名），
     逐目录状态（新建/更新/跳过/外来）与判定依据；
  3. 关键命令与实际输出（`$ <命令>` + `exit=<退出码>`），命令输出过长时截断并注明；
  4. 用户确认结果（dry-run 计划表是否获批）；每次失败与重试：失败命令、错误输出、
     重试命令与次数；
- 记录内容（**会话尾**）：
  5. 最终汇总（结构化输出）；结束时间、总耗时；遗留项与下一步建议。

**记录规范**：关键事件以分隔行标记 `---- [YYYY-MM-DD HH:MM:SS] 事件描述 ----`；
命令统一记作 `$ <命令>` 并在结果行标注退出码；全程不覆盖、只追加。

## 历史日志预读（关键信息速览）

会话**第一步**只读预读本技能**最新一份**历史日志的**尾部汇总区**（只关注关键信息，不做深入解析）：

```bash
tail -20 "$(ls -1t .init.*.log 2>/dev/null | head -1)"   # 尾部汇总区：上次任务/结论/遗留项
```

- 关键信息：① 上次任务/对象；② 结论或收敛结果；③ 遗留项与下一步建议——其余（过程轮次、命令细节）一律跳过，不做深入 think
- 约束：只读不改；无历史日志（首次运行）时正常跳过，不视为错误；总耗时以秒级为限

### 前置上下文预读（工作目录说明文件与 agent 文件夹）

会话**第一步**与历史日志预读同步执行：只读当前工作目录的**说明文件**与 **agent 文件夹**
（清单可扩展，存在即读、缺失即跳过，不视为错误），只取关键信息、避免耗时过长：

```bash
# 1) 说明文件（按优先级取第一个存在的：AGENTS.md > README.md > CLAUDE.md > AGENT.md > CODEX.md）
for f in AGENTS.md README.md CLAUDE.md AGENT.md CODEX.md; do
  [ -f "$f" ] && { echo "== $f =="; head -40 "$f"; break; }
done
# 2) agent 文件夹（按优先级取第一个存在的：.opencode > .claude > .codex）
for d in .opencode .claude .codex; do
  [ -d "$d" ] || continue
  echo "== $d =="; ls "$d" | head -10
  [ -f "$d/AGENTS.md" ] && head -20 "$d/AGENTS.md"
  break
done
```

- 关键信息：项目约定/命令/目录结构/入口点/测试方式；agent 文件夹只列顶层结构（如 AGENTS.md、skills/）
- 约束：只读不改；文件/目录不存在时正常跳过；`head` 限行保证秒级耗时

### AGENTS.md 同步（必要时补充有益内容）

会话中如发现**当前工作目录的 AGENTS.md** 缺失本次任务相关且对后续会话有益的内容
（项目约定/命令/目录结构/入口点/测试方式/新功能说明），**必要时补充更新**，
保持约定文档与仓库状态同步：

- 只补充**确凿有益**的内容：本次任务确立的约定、验证过的命令、新入口点/结构变化；
  不写入个人化/临时性/未验证内容；
- **最小改动**：在既有章节内补充或新增小节，遵循原文档结构（表格/列表），不重写全文；
- **先读后写**：写入前先读 AGENTS.md 现状，避免重复条目与格式破坏；
- 补充位置与内容记入会话日志；改动不代提交（提示用户自行 git add/commit）。

以下为执行细则：

1. **init**：创建或更新 `AGENTS.md`（统一标准，**不重命名**）。如有其他 agent 的 init 文件
   （如 `CLAUDE.md`、`CODEX.md`、`GEMINI.md`、`.cursorrules` 等），先**参考之**（取其格式），
   再将其重命名为 `.<原文件名>.<时间戳>.bak`（**仅供格式参考**）。
2. **skill 补充**：如果目录中的**新建内容为 agent 生成**，则在本库根目录（git 家目录）的
   `.opencode/skills/` 下添加**生成此内容的完整 skill**（各目录收集后统一集中存放）。如有其他 agent
   的 skills 目录（如 `.claude`、`.codex`、`.cursor`、`.windsurf`），先**参考之**，再将其重命名为
   `.<原目录名>.md.<时间戳>.bak`（**仅供格式参考**）。
3. **skill 自动归档**：扫描本库内所有**不在本库根 `.opencode/skills/`** 的 skill（任意位置的
   `skills/`、`.claude/skills/`、`.codex/skills/` 等），完整读取后**合并存放**到
   `{本库根}/.opencode/skills/<skill-name>/SKILL.md`；同名同内容跳过，同名不同内容并列保留并注明；
   原位置保留不删除（如需清理另行处理，在汇总中注明）。
4. **外来文件夹排除**：`AGENTS.md` 仅存放于**本库所属目录**；显然的外来文件夹
   （如 `lib/_oh-my-zsh`、`agent/LQCD_Master` 等第三方/上游完整拷贝）**不生成** `AGENTS.md`，
   其下已有的 `AGENTS.md` 同样执行**归档**（`.AGENTS.md.<时间戳>.bak`）与**合并**
   （有价值内容并入本库根 `AGENTS.md`）。

## 触发时机

- 用户要求初始化仓库/目录："init"、"初始化"、"生成AGENTS.md"、"为每个目录生成AGENTS.md"
- 用户要求归档 agent 初始化文件："归档agent配置"、"重命名CLAUDE.md"、"处理.claude/.codex"
- 用户要求整理/收集 skills："收集skill"、"把生成内容的skill放到git家目录的.opencode/skills"、
  "归档skill"、"合并skill到.opencode/skills"、"收集散落的skill"
- 用户要求预演/确认："dry-run"、"预演"、"先看看会改什么"（只读调查，不写文件）
- 与其他技能配合：归档前后查看改动 → diff；初始化完成打标 → tag；初始化报错 → debug；
  仓库结构梳理 → analy；优化 skill 库 → up；生成类任务全流程 → make

## 各 agent 的初始化文件与配置目录（识别清单）

| Agent | init 文件 | 配置/技能目录 |
|---|---|---|
| Claude Code | `CLAUDE.md` | `.claude/`（skills、commands、agents） |
| OpenAI Codex | `CODEX.md`（也读 AGENTS.md） | `.codex/`（skills、prompts） |
| Cursor | `.cursorrules`、`.cursor/rules/*.mdc` | `.cursor/`（skills、rules） |
| GitHub Copilot | `.github/copilot-instructions.md` | `.copilot/`、`.github/prompts/` |
| 百度 Comate | 无独立 init 文件（读 AGENTS.md） | `.comate/` |
| 腾讯 CodeBuddy | 无独立 init 文件（读 AGENTS.md） | `.codebuddy/` |
| Windsurf | `.windsurf/rules/*.md` | `.windsurf/`（skills） |
| Gemini CLI | `GEMINI.md` | `.gemini/` |
| opencode | `AGENTS.md`（标准，不重命名） | `.opencode/`（agents、commands、skills） |
| 其他 | 上述未列出的 `*.md`/隐藏目录 | 同类处理 |

> 若某目录出现清单外的新 agent 文件/目录，按同一规则处理并**在汇总中登记**，
> 便于后续维护清单。

## 命名与时间戳约定

| 对象类型 | 示例 | 重命名后 |
|---|---|---|
| init 文件 | `CLAUDE.md` | `.CLAUDE.md.<时间戳>.bak` |
| init 文件 | `CODEX.md` | `.CODEX.md.<时间戳>.bak` |
| init 文件 | `GEMINI.md` | `.GEMINI.md.<时间戳>.bak` |
| init 文件 | `.cursorrules` | `.cursorrules.<时间戳>.bak` |
| init 文件 | `.github/copilot-instructions.md` | `.github/copilot-instructions.md.<时间戳>.bak` |
| 技能目录 | `.claude` | `.claude.md.<时间戳>.bak` |
| 技能目录 | `.codex` | `.codex.md.<时间戳>.bak` |
| 技能目录 | `.cursor` | `.cursor.md.<时间戳>.bak` |
| 技能目录 | `.copilot` | `.copilot.md.<时间戳>.bak` |
| 技能目录 | `.comate` | `.comate.md.<时间戳>.bak` |
| 技能目录 | `.codebuddy` | `.codebuddy.md.<时间戳>.bak` |
| 技能目录 | `.windsurf` | `.windsurf.md.<时间戳>.bak` |

统一规则：**`<原文件/目录名>.<时间戳>.bak`**（技能目录在原名后加 `.md`）。

时间戳格式：`%Y-%m-%d-%H-%M-%S`（例如 `2026-07-29-11-37-27`），生成方式：

```bash
TS=$(date +%Y-%m-%d-%H-%M-%S)   # 例如 2026-07-29-11-37-27
mv CLAUDE.md ".CLAUDE.md.${TS}.bak"
mv CODEX.md  ".CODEX.md.${TS}.bak"
mv .claude   ".claude.md.${TS}.bak"
mv .codex    ".codex.md.${TS}.bak"
mv .comate   ".comate.md.${TS}.bak"
mv .codebuddy ".codebuddy.md.${TS}.bak"
```

⚠️ **禁止重命名全局配置**：`~/.claude`、`~/.codex`、`~/.cursor`、`~/.copilot`、`~/.comate`、
`~/.codebuddy`、`~/.config/opencode` 等为工具**全局配置/技能目录**，仅处理**本库范围以内**的
agent 文件与目录；本库根即 `$HOME` 时，对全局目录（如 `~/.codex` 全局技能库）**只参考、不重命名**，
并在汇总中注明。

---

## 工作流程（两阶段执行：先只读调查，后统一执行）

**核心原则**：
- **两阶段**：先只读扫描并产出变更计划（阶段 A），确认后再执行写操作（阶段 B），
  避免边扫边改导致信息丢失（如先重命名了 `.claude`，后续就无法再参考其内容）。
- **重命名最后统一执行**：所有 `mv ... .bak` 放在阶段 B 的**最后一步**批量完成，
  确保归档前所有来源（init 文件、skill 目录）都已被完整读取与复制。
- **幂等**：已归档对象（`*.bak`）不再处理；第二次运行应输出"无变更"。
- **只复制，不移动**：所有 skill 归集均为复制，原位置保留。

### Step 0. 运行模式

- 默认 **dry-run（只读调查）**：执行阶段 A，输出完整变更计划表，询问用户确认后
  再执行阶段 B；或用户明确要求（"直接执行"、"apply"）时跳过确认。
- 阶段 A 与阶段 B 的边界：阶段 A 不改动任何文件系统内容。

### Step 1. 确定本库范围

- 本库根目录 = 最近的包含 `.git` 的祖先目录；若无 `.git`，则以用户指定的目录（或当前工作目录）为准。
- 收集根目录下所有子目录，**自顶向下**遍历：

```bash
find <repo_root> -type d \
  -not -path "*/.git*" \
  -not -path "*/node_modules*" \
  -not -path "*/__pycache__*" \
  -not -path "*/.venv*" \
  -not -path "*/build/*" \
  -not -path "*/dist/*" \
  -not -path "*/tmp/*"
```

排除项：`.git`、`node_modules`、`__pycache__`、`.venv`、`build/`、`dist/`、`tmp/`、
`site-packages` 等构建产物/依赖目录。被排除目录**不生成** `AGENTS.md`，但其中的
`CLAUDE.md` / `.claude` 仍按规则归档（重命名）。

**外来文件夹判定**（不生成 AGENTS.md，仅处理其下已有 AGENTS.md 的归档+合并），满足其一即可：
- git 子模块（`.gitmodules` 中登记、`git submodule status` 列出）或内含独立 `.git` 目录；
- 知名第三方/上游项目的完整拷贝（如 `lib/_oh-my-zsh`、`agent/LQCD_Master`）；
- 与当前仓库用途无关的完整外来源码，目录名明显非本库命名惯例；
- 无法确定时：**询问用户**（与其余不确定点**一次性全部列出**，用户一次回答，不逐次追问）。

### Step 2. 阶段 A — 只读调查（不写任何文件）

对每个目录（含根目录），只读收集：

1. **收集 agent init 文件**：`AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`GEMINI.md`、
   `.cursorrules`、`.cursor/rules/`、`.github/copilot-instructions.md`、
   `.windsurf/rules/` 等（见识别清单）。**完整读取内容**，作为后续格式参考。
2. **外来文件夹判定**：按 Step 1 标准确认；是则登记（其下已有 `AGENTS.md` 也登记待归档）。
3. **检测 agent 生成的新建内容**（非 SKILL.md 的普通内容），判定依据（满足其一即可）：
   - 文件内容含 agent 标记，如 "generated by Claude Code / opencode"、"Created by Claude"、
     "Generated by Codex"、"Comate" / "CodeBuddy" 生成标记、`[Claude Code]`（git tag 消息后缀）、
     "AGENTS.md" 引用等；
   - git 证据：未跟踪文件（`git status --porcelain` 中 `??` 开头）、agent 工具身份提交
     （`git log --format='%an|%ae'` 匹配 Claude/opencode/Codex/Comate/CodeBuddy 等）、
     近期新增的非源码文件（`git log --diff-filter=A`）；
   - 内容符合已知 skill 的输出模式（例如 `stab<N>/dev<N>/bug<N>` 注释标签 → `tag` 技能；
     IMA 笔记/知识库产物 → `ima-skill`）；
   - **SKILL.md 本身不在此步判定**（其本身就是 skill，归 Step 2.5 处理），避免自我递归；
   - 无法确定时：**询问用户**（与其余不确定点**一次性全部列出**，用户一次回答，不逐次追问）。
4. **识别生成此内容的 skill**（针对 Step 2.3 确认的内容）：
   - 在现有 skill 库中查找：`<repo>/.claude/skills/`、`<repo>/.codex/skills/`、
     `<repo>/configure/skills/`、`<repo>/.opencode/skills/`、`~/.claude/skills/`、
     `~/.codex/skills/`、`~/.config/opencode/skills/`；
   - 按内容模式匹配已知 skill；若匹配到，取该 skill 的**完整目录**（`SKILL.md` + 全部附属文件，
     如脚本、子文档 —— 参考 `ima-skill` 的多文件结构，而非仅 `SKILL.md`）；
   - 若无法识别但确为 agent 生成：询问用户（与其余不确定点**一次性全部列出**）；或根据内容反向撰写一份完整 skill
     （说明该内容是如何生成的）。
5. **扫描散落 skill**（全库只读）：

```bash
find <repo_root> -name "SKILL.md" \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/build/*" \
  -not -path "*/dist/*" \
  -not -path "*/tmp/*" \
  -not -path "*/.claude.md.*.bak/*" \
  -not -path "*/.codex.md.*.bak/*" \
  -not -path "*/.AGENTS.md.*.bak" \
  -not -path "<repo_root>/.opencode/skills/*"
```

   - 每个 `SKILL.md`：读取 frontmatter 的 `name`（**无 frontmatter 时用所在目录名**），
     登记待归集；**已归档 `.bak` 目录内**的 SKILL.md 跳过（防重复处理）。
6. **汇总变更计划**：输出完整计划表（新建/更新 AGENTS.md 清单、待归档 init 文件清单、
   skill 归集清单、待重命名目录清单、外来文件夹清单），交用户确认（dry-run 结束）。

### Step 3. 阶段 B — 执行（按以下顺序写操作）

1. **创建/更新 `AGENTS.md`**（不重命名，统一标准；外来文件夹跳过）：
   - 已存在：**就地更新** —— 保留已验证有效的内容，删除过时/臆断内容，与当前代码核对；
   - 不存在：按阶段 A 收集的参考格式新建。可参考仓库根 `/root/AGENTS.md` 作为范本。
   - 内容规则（只保留高信号、agent 易出错的信息）：
     - 确切的命令与执行顺序（lint → typecheck → test 等）；
     - 目录结构、入口点、包边界；框架/工具链怪癖（生成代码、环境变量、构建产物）；
     - 与默认约定不同的仓库惯例；测试怪癖、必需的前置条件；
     - 排除：通用建议、冗长教程、显而易见的语言常识、无法验证的推测。
   - 保持简洁；不确定时宁可省略。
2. **在本库根目录（git 家目录）的 `.opencode/skills/` 归集 skill**（全部为**复制**）：
   ```bash
   # 目录 D 中的内容为 agent 生成 → 生成它的完整 skill 集中复制到本库根（git 家目录）的 .opencode/skills/
   # 散落 skill（configure/skills/、.claude/skills/ 等任意位置）同样归集于此
   mkdir -p "<repo_root>/.opencode/skills/<skill-name>"
   cp -r <skill-source-dir>/ <repo_root>/.opencode/skills/<skill-name>/   # 整个目录，非仅 SKILL.md
   ```
   - 所有 skill 统一集中存放于本库根（git 家目录）的 `.opencode/skills/`；
   - 同名同内容不重复添加（内容比对用 `sha256sum`，目录则比对关键文件或 `diff -r`）；
     同名不同内容时并列保留并注明（如 `<name>.v2`）；
   - 原位置**保留不删除**，仅在汇总中登记来源。
3. **外来文件夹下 `AGENTS.md` 的归档+合并**：
   - 按 Step 1 判定为外来文件夹的目录，若其下已有 `AGENTS.md`：
   - **归档**：`mv AGENTS.md ".AGENTS.md.${TS}.bak"`（原地保留供参考）；
   - **合并**：读取其内容，**有价值部分并入本库根 `AGENTS.md`**（外来组件在本库中的使用方式、
     加载关系等），与本库根已有内容重复的跳过；纯外来组件自身细节不合并。
4. **统一重命名归档（最后一步，批量执行）**：
   - 对阶段 A 登记的全部 agent init 文件与配置/技能目录统一执行：
   ```bash
   TS=$(date +%Y-%m-%d-%H-%M-%S)   # 全程使用同一时间戳
   mv CLAUDE.md  ".CLAUDE.md.${TS}.bak"
   mv CODEX.md   ".CODEX.md.${TS}.bak"
   mv .claude    ".claude.md.${TS}.bak"
   mv .codex     ".codex.md.${TS}.bak"
   mv .comate    ".comate.md.${TS}.bak"
   mv .codebuddy ".codebuddy.md.${TS}.bak"
   ```
   - 执行前先核对：所有来源已在阶段 A/阶段 B 前序步骤中被完整读取或复制（防丢失）；
   - 若某个目标名已存在（如上次运行遗留同名 `.bak`），以当前秒级时间戳重试；
   - 若目录同时是某 agent 的全局配置（本库根即 `$HOME` 时，如 `~/.codex`）：只参考，不重命名。

### Step 4. 验证与汇总

- 每个应初始化的目录均已有 `AGENTS.md`（外来文件夹除外）；
- 各 agent 的 init 文件 / 配置目录均已按 `.X.md.<时间戳>.bak` 规则归档，内容完好；
- 所有 agent 生成内容对应的完整 skill 均已集中复制到本库根（git 家目录）的 `.opencode/skills/` 下，内容一致；
- 散落 skill 均已归集到本库根 `.opencode/skills/`（同名同内容跳过、差异并列保留），原位置保留；
- 外来文件夹下的 `AGENTS.md` 均已归档（`.AGENTS.md.<时间戳>.bak`）且价值内容已并入本库根 `AGENTS.md`；
- **幂等校验**：再次以 dry-run 运行阶段 A，应输出"无变更"；
- 输出结构化汇总（见下）；若有重命名涉及 git 跟踪文件，提示用户自行 `git add -A` + 提交（不代提交）。

---

## 错误处理

| 场景 | 处理 |
|---|---|
| 目录无 `.git` 且无用户指定目录 | 以当前工作目录为根，并在汇总中注明 |
| `AGENTS.md` 已存在 | 就地更新，不重建；保留已验证内容 |
| 多个 agent init 文件并存（CLAUDE.md + CODEX.md + .cursorrules） | 全部参考格式，全部按规则归档（同一时间戳） |
| 无法判定内容是否 agent 生成 | 询问用户（**一次问全**，不逐次追问），不臆断 |
| 无法定位生成内容的 skill | 询问用户（**一次问全**）；或据内容撰写完整 skill |
| 本库根 `.opencode/skills/` 中已有同名 skill | 内容一致（`sha256sum`/`diff -r`）则跳过；不一致则并列保留并注明 |
| 散落 skill 与目标同名不同内容 | 并列保留（如 `<name>.v2`）并在汇总中注明 |
| 外来文件夹判定不确定 | 询问用户（**一次问全**），不臆断 |
| 外来文件夹下无 AGENTS.md | 不创建，仅登记为外来文件夹 |
| 全局配置目录（~/.claude、~/.codex、~/.cursor、~/.copilot、~/.comate、~/.codebuddy 等）被误指 | 拒绝重命名，说明只处理本库范围内；本库根即 $HOME 时只参考不重命名 |
| 清单外的新 agent 文件/目录 | 按同一规则处理，并在汇总中登记 |
| 重命名目标已存在 | 以当前秒级时间戳重试 |
| 执行中途中断 | 重新运行即可：阶段 A 只读无副作用，阶段 B 幂等（已归档/已归集的自动跳过）；中断与失败原因记入会话日志 |
| 阶段 B 多次失败 | 基于会话日志定位失败步骤（重命名冲突、权限、磁盘等），修正后重新执行（循环尝试直至成功）；无法解决时向用户报告 |
| 用户未确认计划即要求执行 | dry-run 默认不写任何文件；执行前必须展示计划表并获确认（除非用户明确 "apply"） |

## Agent 输出约定

每次运行后输出结构化汇总：

```text
✓ init 完成 (repo: /root/xxx, 模式: dry-run → apply)
  已初始化目录:  12 (AGENTS.md 新建 9 / 更新 3)
  已归档 init:   CLAUDE.md → .CLAUDE.md.2026-07-29-11-37-27.bak (3)
                 CODEX.md  → .CODEX.md.2026-07-29-11-37-27.bak (1)
                 .cursorrules → .cursorrules.2026-07-29-11-37-27.bak (1)
  skills 补充:   tag → /root/xxx/.opencode/skills/tag/ (3 个来源目录, 含附属文件)
  skill 归集:    configure/skills/{init,tag} → /root/xxx/.opencode/skills/{init,tag} (2)
  外来 AGENTS.md: lib/_oh-my-zsh/AGENTS.md → .AGENTS.md.2026-07-29-11-37-27.bak, 内容并入根 AGENTS.md (1)
  已归档配置目录: .claude → .claude.md.2026-07-29-11-37-27.bak (1)
                 .codex  → .codex.md.2026-07-29-11-37-27.bak (1, 仅参考未重命名: ~/.codex 全局)
                 .comate → .comate.md.2026-07-29-11-37-27.bak (1)
                 .codebuddy → .codebuddy.md.2026-07-29-11-37-27.bak (1)
  跳过目录:      node_modules, build, dist, tmp (4 类)
  清单外新登记:  .gemini/ (Gemini CLI, 2 处)
  幂等校验:      再次 dry-run 无变更 ✓
  日志:          .init.2026-08-12-19-19-43.log (重试 0 次)
  提示:          git 跟踪的重命名请自行 git add -A 后提交（未代提交）
```

dry-run 阶段输出计划表（仅列有动作项）：

```text
计划 (dry-run, 未写文件):
  AGENTS.md 新建: lattice-pdf, snsc, PyQCU  (3)
  AGENTS.md 更新: configure (1)
  归档:          CLAUDE.md ×3, CODEX.md ×1, .claude ×1, .comate ×1
  skill 归集:    configure/skills/init,tag → .opencode/skills/ (2)
  外来文件夹:    lib/_oh-my-zsh (AGENTS.md 归档+合并), agent/LQCD_Master (无 AGENTS.md)
  确认后执行 (输入 "apply" 或 "直接执行")
```

逐目录明细（仅列出有动作的目录）：

```text
/root/xxx/lattice-pdf      AGENTS.md 新建; CLAUDE.md → .CLAUDE.md.2026-07-29-11-37-27.bak
/root/xxx/.opencode/skills tag 技能已存在; 目录含 agent 生成内容 → 本库根 .opencode/skills/tag 已确认
/root/xxx/lib/_oh-my-zsh      外来文件夹: 跳过 AGENTS.md 生成; 既有 AGENTS.md → .AGENTS.md.<ts>.bak + 合并入根
/root/xxx/configure/skills    散落 skill 归集: init/tag → /root/xxx/.opencode/skills/ (原位置保留)
/root/xxx/snsc             CODEX.md → .CODEX.md.2026-07-29-11-37-27.bak; AGENTS.md 更新
```

## 注意事项

- 先只读后写入（两阶段）：阶段 A 不改动任何文件；重命名统一放在阶段 B 最后批量执行；
- 所有归档/归集均为**复制优先**，先完整读取再重命名，防信息丢失；
- 不确定（外来文件夹判定、是否 agent 生成、生成技能的归属）时先询问用户（**所有不确定点一次全部列出**，不逐次追问），不臆断；
- 幂等：已归档（`*.bak`）与已归集内容不再处理，重复运行应输出"无变更"；
- 不代用户提交代码；涉及 git 跟踪文件的重命名与删除提示用户自行提交；
- 全局配置目录（`~/.claude`、`~/.codex` 等）只参考、不重命名；
- 会话日志 `.init.<时间戳>.log` 不入库，由用户决定保留或清理。
