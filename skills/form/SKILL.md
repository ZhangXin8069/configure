---
name: form
description: |
  当用户要求审计、整改或初始化 Git 库的命名、目录结构、代码框架、文档/日志/数据/测试
  布局、仓库清洁度与交付格式，检查命名/目录重构是否合规，或说 form / 格式治理 /
  命名规范 / 目录规范 / 结构治理 / 仓库规范化 / 格式审计 / dry-run form 时使用；
  不用于单点语法错误或性能优化。
metadata:
  openclaw:
    emoji: 📐
---

# form — Git 库命名、结构与交付格式治理技能

## 执行前置

遵循当前目录 `AGENTS.md`「技能执行公共契约」；仅按需读取技能正文与 reference。

把目标 Git 库整理成可持续维护的统一格式：先判定简单库或复杂库，再核对命名、框架、
目录职责和 Git 交付流程，形成全库冲突表，按批准后的批次整改，最后通过功能复现与
`~diff → ~init → ~tag(dev)` 收尾。

明确文字规则的优先级高于范例链接；范例只用于确认风格，不覆盖本 skill 的规则。

## configure 特化

- 当前仓库为 simple 库，主导语言为 bash；框架参照
  `references/source-snapshots/configure-main/bin/`。
- 代码文件全小写；批量 Git 命令使用 `gz-<repo>-push.sh` 和 `zg-<repo>-pull.sh`，
  聚合入口为 `gz-all-push.sh`、`zg-all-pull.sh`。
- 顶层目录白名单为 `bin/data/docs/hooks/lib/logs/plugins/refer/skills/tools`。
- 包依赖清单位于 `lib/requirements/{apt,pip}.txt`，由 `bin/{apt,pip}_install.sh` 消费。
- `docs/` 只允许 `md/tex/pdf` 和图片；`logs/` 只允许 `log/json/tsv/csv/txt`。
- 本库缺少独立构建系统时，验证入口为 `bash -n bin/*.sh`、
  `scripts/form-audit.sh --root /root/configure --strict --quiet` 和
  `scripts/form-snapshot-verify.sh --quiet`。

## 核心原则

1. **规则先于范例**：用户明确规则 > 目标库已有特化规则 > 本 skill 通用规则 > 参考库范例。
   远程链接不可访问时仍可依明文规则工作，不因示例失效而停止。
2. **先分类再命名**：先识别语言族、构件类型和简单库/复杂库，再套用命名法；直接批量小写
   会破坏单位矩阵 `'I'`、路径变量 `_SRC`、领域缩写和简短自然词等有意义例外。
3. **语义可读优先**：所有名称应短、准确、无歧义。驼峰、下划线、点划分和 `-` 连接符是
   表达层级关系的工具，不是机械格式化目标。
4. **全库审计先于改动**：先建立覆盖文件、符号、目录、引用关系、构建入口和测试入口的
   冲突表；跨文件重命名必须作为同一批处理，避免留下导入、文档或配置断链。
5. **目录有单一职责**：`docs/`、`logs/`、`data/`、`testing/` 分别承载任务文档、日志、
   数据和测试；不把临时产物混入功能源码。历史受 Git 保护时，已跟踪且可恢复的当前工作区
   整理可放宽；未跟踪或来源不明文件仍须先审计并入计划。
6. **整改必须功能复现**：格式整改不是“看起来整齐”即完成；必须运行原项目可用的构建、
   测试或主入口冒烟验证，并检查重命名后的全部旧引用。
7. **~form 默认较高权限**：调用 `~form` 即授权计划列明的仓库内可恢复清理、常规提交、
   push 和最终标签；force push、改写已推送标签、系统配置和凭据操作仍须单独确认。
8. **本地特化是最终产物**：整改完成后，目标库必须得到自己的 `skills/form/SKILL.md`
   和根 `AGENTS.md` 本地规则，记录该库的语言、目录和例外，不能只留一个远程链接。
9. **标签不作为语义来源**：标签名只用于版本定位；命名、注释、文档和提交消息应使用时间、
   目的、功能或领域名词，禁止从 `stabN`、`devN` 等标签名反推业务语义。

## Git 检查

有 Git 且本次产生文件改动时，执行 `git diff --check` 和定向复查。只读审计不提交；
完整 `~form` 流程按 Step 8 使用较高权限完成提交、推送和最终标签。
无 Git 或无本次改动时立即跳过。

## 触发时机

- 用户要求格式审计或整改：“form”、“检查命名”、“统一目录”、“仓库规范化”、
  “按 skill 约定整改这个库”、“同步 AGENTS.md 和文档”。
- 新库初始化或大型重构后，需要统一语言框架、文件/函数/变量/对象命名和顶层目录。
- 用户要求清理上一任务遗留的文档、日志、测试代码和非功能性文件，但必须保留 Git 回溯能力。
- 用户要求把通用格式约定特化到当前库，并在根 `AGENTS.md` 写明本地规则。
- 与其他技能配合：先读改动用 `diff`；多步骤方案用 `plan`；报错用 `debug`；
  功能回归用 `test`；最终同步用 `init`；完成后用 `tag(dev)`；
  技能自身的描述或结构问题用 `skill-creator`；多库只读审计可并行调用 `dispatch`。

## 参考文件

- `references/naming-and-layout.md`：语言/构件命名矩阵、文件夹白名单、简单库与复杂库规则。
- `references/observed-conventions.md`：从固定明文快照归纳的 C++/Python/Bash/静态前端规则。
- `references/source-snapshots/README.md`：四个参考 URL 的提交、文件清单、排除项和校验方式。
- `references/git-artifacts-and-workflow.md`：目录职责、清理边界、提交消息、验收和本地特化模板。
- `scripts/form-audit.sh`：只读检查已跟踪路径的顶层目录、代码文件名、docs/logs/data 和测试位置。
- `scripts/form-snapshot-verify.sh`：离线校验快照哈希、manifest、二进制排除项和符号链接。

执行命名或目录审计前读取第一个和第二个；需要核对参考原义、提交或例外证据时读取第三个。
涉及清理、Git 交付、文档/日志/数据/测试或根 `AGENTS.md` 特化时读取第四个。脚本只提供
确定性基线信号，函数、变量、对象和公开接口的语义命名仍须按规则人工判断。

## 工作流程

### Step 1. 锁定仓库、语言与任务边界

1. 从 Git 根目录开始，不扫描仓库外的无关内容：

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
REPO_NAME="${REPO_ROOT##*/}"
case "$REPO_NAME" in
  *[A-Z]*) REPO_CLASS=complex ;;
  *) REPO_CLASS=simple ;;
esac
printf 'repo=%s class=%s\n' "$REPO_NAME" "$REPO_CLASS"
git status --short --branch
git tag --list --sort=-creatordate | head -n 10
```

2. 按名称含大写字母判定复杂库，否则为简单库；用户明确指定时以其指定为准。
3. 统计语言树和文件类型，映射为 `cpp`、`python`、`bash` 或 `other`；混合库允许并存，
   但每个目录必须能说明主导语言。
4. 输出一句任务定义：目标库、库类型、主要语言、整改范围、功能复现入口和停止条件。

### Step 2. 只读审计

1. 盘点已跟踪文件、顶层目录和未跟踪内容：

```bash
cd "$REPO_ROOT"
git ls-files | sort
find . -maxdepth 3 -type d -not -path './.git*' -not -path './data*' | sort
git status --short
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-audit.sh" --root "$REPO_ROOT" --quiet
```

`FORM_SKILL_DIR` 指向当前正在执行的 `form` 技能目录；使用全局技能而目标库尚无本地副本时，
显式设置为该技能的实际路径。

`form-audit.sh` 仅审计 Git 已跟踪路径，默认不跟随 `data/`、`refer/`、
`source-snapshots/` 和 vendored/generated 目录；输出是候选冲突，不是自动改名授权。

2. 读取与本次范围相关的根 `AGENTS.md`、各目录 `AGENTS.md`、构建/测试入口和现有
   `skills/form/SKILL.md`；不递归读取无关文档。需要参考范例时，先读
   `references/observed-conventions.md`，再按其中的相对路径进入明文快照。
3. 逐项建立冲突表：

| 对象 | 类型 | 语言 | 当前名称/位置 | 预期规则 | 冲突 | 处理 |
|---|---|---|---|---|---|---|
| `path` 或 `symbol` | 文件/函数/变量/对象/目录 | cpp/python/bash/other | 实际值 | 引用规则 | 是/否/例外 | rename/move/update/keep |

4. 命名冲突必须保留 `文件:行号` 或路径证据；引用快照时同时给出快照根、commit 和文件行号。
   把真正例外单列，不把普通违规伪装成例外。
5. 使用本地快照前校验完整性；任一失败都停止引用该快照，不使用损坏副本推断规则：

```bash
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-snapshot-verify.sh" --quiet
```

6. 运行 `~diff` 查看上一基线以来的改动；若尚未有基线，记录 `git status` 与当前提交作为基线。

### Step 3. 生成整改方案

1. 按依赖排序：功能基线 → 目录骨架 → 文件名 → 符号与导入 → 配置/注释/文档 →
   AGENTS/skill → 测试归集 → 清理 → 全量验证 → Git 收尾。
2. 每个任务写明：
   - 输入与输出；
   - 涉及文件；
   - 可独立执行的验证命令；
   - 失败时的回退点。
3. 将删除、覆盖、移动生成文件、远程推送和历史改写单列为风险项；禁止“顺手清理”。
4. 首次交互一次性展示完整计划。`~form` 默认较高权限覆盖计划中列明的仓库内清理与常规
   Git 交付；无回复时继续，计划外或不可逆操作立即停止。
5. 用户明确要求 dry-run 时只输出审计表和计划，不执行 Step 4 以后写操作。

### Step 4. 分批实施格式整改

1. 先运行目标库已有测试或冒烟命令，保存基线退出码；没有入口时明确记录验证缺口。
2. 先建/整理目录，再使用 `git mv` 或补丁做重命名；一次提交批内的移动与引用更新必须
   在同一逻辑批次完成。
3. 符号重命名后用仓库级搜索确认旧名清零，或只保留明确兼容别名：

```bash
rg -n --hidden --glob '!.git/**' '旧名称|OldName|old_name'
```

4. 更新构建清单、导入、文档、注释、测试、hook、脚本和 AGENTS.md 中的全部引用。
5. 命名例外必须符合 `references/naming-and-layout.md` 的可观察条件；不能仅写“特殊”后跳过。
   新增规则来自快照时，在 `references/observed-conventions.md` 同步证据和适用边界。
6. 每个批次完成即运行该批次的最小验证，不把全部风险积累到最后。

### Step 5. 整理交付目录

1. `docs/` 仅保留本次任务文档及附件图片，格式限定为 TeX、PDF、Markdown 和图片。
2. `logs/` 仅保留本次任务日志、用户自定义历史日志，以及 `log/json/tsv/csv/txt`；
   清理前列出候选并检查是否被源码或脚本引用。
3. `data/` 汇集历史数据文件；通过 `.gitignore` 排除内容，仅保留 `.gitignore`、
   `AGENTS.md` 和 `README.md`。
4. 复杂库测试归入小写库名下的 `testing/`，简单库测试可保留在功能目录并采用
   `*.test.sh` 一类“小写点划分”入口；合并后的通用测试必须附可直接调用的脚本。
5. 测试入口应具备完整默认值，优先无参数即可运行；参数只用于覆盖默认行为。
6. 所有删除先展示候选、Git 保护状态和恢复命令；计划已列明且调用为 `~form` 时按较高权限
   执行，计划外候选不删除。

### Step 6. 全面功能复现

1. 按仓库 `AGENTS.md` 和构建系统依次执行可用的语法检查、构建、测试、安装与主入口冒烟；
   纯 shell 库至少执行 `bash -n`，并运行主要脚本的 `--help` 或安全只读入口。
2. 对改名/移动前后运行同一验证集，比较退出码和关键输出；不能运行的功能写明原因和风险。
3. 检查旧路径、旧符号、格式规范和冲突标记：

```bash
git diff --check
git status --short
rg -n --hidden --glob '!.git/**' '<<<<<<<|=======|>>>>>>>|TBD|FIXME'
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-audit.sh" --root "$REPO_ROOT" --strict --quiet
```

4. 自动检查不覆盖函数、变量、对象、公开接口和既有兼容例外；这些项目逐条回填审计表，
   每条给出 `文件:行号` 和修正或保留理由。
5. 若测试失败，转 `~debug` 定位根因，不以修改期望值或删除测试绕过；修复后重跑完整验证。

### Step 7. 生成当前库特化版本

1. 将本 skill 的通用流程与目标库的实际语言、目录、入口、例外和验证命令合成
   `skills/form/SKILL.md`；已存在时保留有效本地信息并补齐，不直接覆盖旧规则。
2. 在目标库根 `AGENTS.md` 新增“form 约定”章节，明文列出：
   - 库类型与主导语言；
   - 文件、函数、变量、对象和目录命名规则；
   - 允许的顶层目录及各目录职责；
   - 测试入口和功能复现命令；
   - Git 交付、标签与清理边界；
   - 仅限本库的已批准例外。
   本地规则必须完整可执行，不只写“参见通用 skill”或远程链接。
3. 同步相关目录 `AGENTS.md`、README、注释和 skill 表；删除已失效说明，保留历史依据。
4. 重新执行 Step 6，确认文档/配置同步没有破坏功能。

### Step 8. Git 交付与收尾

`~form` 默认较高权限覆盖以下常规交付；出现 force push、改写已推送标签或仓库外写入时停止：

1. 调用 `~diff` 审计全部本次改动；不得使用 `git add -A`，只暂存本任务文件。
2. 每个独立整改批次生成详实提交消息，结构见
   `references/git-artifacts-and-workflow.md`；提交后推送当前分支，禁止 force push。
3. 调用 `~init` 同步 AGENTS.md 和 agent 配置归档；随后调用 `~tag(dev)` 保存开发快照。
4. 在 `docs/` 写入该技术任务的 Markdown 文档，记录目标、冲突表摘要、改动、验证证据、
   未决项和恢复方法；文档纳入最终提交与推送。
5. 最终确认本地分支、远程分支和 `dev` 标签指向同一验收提交，并确认标签已推送；
   有漂移时停止并报告，不猜测远程状态。

## 验收矩阵

| 维度 | 证据 | 通过条件 |
|---|---|---|
| 规则来源 | 快照 metadata、commit、manifest、SHA-256 | 使用的四条示例规则均来自固定提交，校验通过 |
| 目录布局 | `form-audit.sh` TSV 输出、根 AGENTS 白名单 | 计划内冲突清零，例外逐条登记 |
| 文件命名 | 自动 TSV、文件路径、重命名后旧引用搜索 | 代码文件名符合规则，兼容例外有理由 |
| 符号命名 | 审计表 `文件:行号`、公开接口清单 | 函数/变量/对象逐项判定，例外可追溯 |
| 交付目录 | docs/logs/data/testing 清单 | 内容类型和职责符合边界 |
| 功能复现 | 构建、测试、主入口冒烟命令与退出码 | 整改前后同一验证集通过；缺口明确写出 |
| Git 收尾 | diff、init、dev tag、远程对象 | 提交消息有意义，分支与标签指向验收提交 |

## 错误处理

| 场景 | 处理 |
|---|---|
| 库名大小写无法判定类型 | 以大小写规则给默认值，并把“可能误分类”列为待确认项；用户指定优先 |
| 工作区已有改动 | 先区分本任务与用户改动，只记录不覆盖；无法安全分离时停止写操作 |
| 文件重命名破坏引用 | 用 `~debug` 定位全部引用点，将移动和引用更新合并为同一批次后重试 |
| 规则与功能约束冲突 | 保留功能正确性，建立具名例外并写入根 AGENTS；不能 silent 跳过 |
| 参考链接不可访问 | 使用本 skill 和 references 的明文规则继续，不把网络失败当作整改失败 |
| 清理候选可能被引用 | 运行仓库级引用搜索；计划未列明或仍有歧义时不删除 |
| 没有测试入口 | 至少执行语法检查和主入口冒烟；在特化 skill 与最终报告写明覆盖缺口 |
| 用户未回复计划 | `~form` 的较高权限允许继续计划内整改；计划外和不可逆项停止 |
| 快照校验失败 | 停止引用该快照，先恢复固定提交内容；不能用损坏副本推断命名规则 |
| 自动审计命中合法例外 | 在根 AGENTS 登记理由，并通过 `--exclude` 或本地包装脚本精确豁免，不禁用整项检查 |
| 审计脚本不可执行或缺失 | 恢复脚本并执行 `chmod +x`，随后运行 `form-scripts.test.sh` |
| 提交/推送失败 | 保留已完成的本地改动与本地产物，检查分支和远端后重试；禁止强推掩盖冲突 |
| 标签或远程对象漂移 | 停止自动修正，交 `tag` 技能检查，不擅自改写已推送对象 |

## 注意事项

- 不允许把所有名字机械转成小写、`snake_case` 或驼峰；先判断构件语义与公开范围。
- `-` 只表示补充关系连接，不代替语言内已有的层级分隔规则。
- 目录白名单之外的名称只有用户明确批准或目标库特化规则明确登记后才能保留。
- 清理不等于删除历史；需要回顾旧文件时使用 `git show <revision>:<path>`。
- `data/` 中的历史数据默认不作为提交对象，文档和日志不得混入数据目录。
- 修改任一步脚本后运行 `scripts/form-scripts.test.sh`；修改快照后立即运行
  `scripts/form-snapshot-verify.sh`，以测试和哈希输出作为脚本可用性的证据。
- 本 skill 负责格式治理，不替代 `debug`、`test`、`optim` 或 `tag` 的专业实现。
