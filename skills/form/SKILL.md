---
name: form
description: |
  当用户要求审计、整改或初始化 Git 库的命名、目录结构、代码框架、文档/日志/数据/测试
  布局、仓库清洁度与交付格式，检查命名/目录重构是否合规、Git 标签名是否被误用为路径或标识符，
  规整 `refer/git-rep` 参考 Git 子库及其 README/分析文档布局，要求把 form 约定固化到当前
  Git 库根规则文件、阻止超限文件进入 Git，或说 form / 格式治理 / 命名规范 / 目录规范 /
  结构治理 / 仓库规范化 / 格式审计 / dry-run form 时使用；不用于单点语法错误或性能优化。
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

参考 Git 库统一作为 submodule 放在 `refer/git-rep/<name>`；本库对这些子库的分析文档集中到
`refer/git-rep/docs/`，来源与致谢写入 `refer/git-rep/README.md`。子库工作树是只读外部内容，
不把上游代码或上游文档混入本库源码和 `docs/`。

## configure 特化

- 当前仓库为 simple 库，主导语言为 bash；框架参照
  `references/source-snapshots/configure-main/bin/`。
- 代码文件全小写；批量 Git 命令使用 `gz-<repo>-push.sh` 和 `zg-<repo>-pull.sh`，
  聚合入口为 `gz-all-push.sh`、`zg-all-pull.sh`。
- 顶层目录白名单为 `bin/data/docs/hooks/lib/logs/plugins/refer/skills/tools`。
- 参考 Git 库统一放在 `refer/git-rep/<name>`，新增时使用
  `git submodule add <url> refer/git-rep/<name>`；本库对参考库的分析文档放
  `refer/git-rep/docs/`，来源与致谢写入 `refer/git-rep/README.md`。存量普通拷贝按
  Step 5 的参考子库流程迁移。
- 包依赖清单位于 `lib/requirements/{apt,pip}.txt`，由 `bin/{apt,pip}_install.sh` 消费。
- `docs/` 只允许 `md/tex/pdf` 和图片；`logs/` 允许 `AGENTS.md` 索引以及
  `log/json/tsv/csv/txt`，agent 日志按 `log` 技能的三态时间戳命名。
- 本库缺少独立构建系统时，验证入口为 `bash -n bin/*.sh`、
  `scripts/form-audit.sh --root /root/configure --strict --quiet` 和
  `scripts/form-snapshot-verify.sh --quiet`。

## 核心原则

1. **规则先于范例**：用户明确规则 > 目标库已有特化规则 > 本 skill 通用规则 > 参考库范例。
   远程链接不可访问时仍可依明文规则工作，不因示例失效而停止。
2. **先分类再命名**：先识别语言族、构件类型和简单库/复杂库，再套用命名法；直接批量小写
   会破坏单位矩阵 `'I'`、路径变量 `_SRC`、领域缩写和简短自然词等有意义例外。
3. **语义可读优先**：所有名称应短、准确、无歧义，并在最短长度内承载最大实际意义。
   驼峰、下划线、点划分和 `-` 连接符是表达层级关系的工具，不是机械格式化目标。
4. **全库审计先于改动**：先建立覆盖文件、符号、目录、引用关系、构建入口和测试入口的
   冲突表；跨文件重命名必须作为同一批处理，避免留下导入、文档或配置断链。
5. **目录有单一职责**：`docs/`、`logs/`、`data/`、`testing/` 分别承载任务文档、日志、
   数据和测试；不把临时产物混入功能源码。历史受 Git 保护时，已跟踪且可恢复的当前工作区
   整理可放宽；未跟踪或来源不明文件仍须先审计并入计划。
6. **整改必须功能复现**：格式整改不是“看起来整齐”即完成；必须运行原项目可用的构建、
   测试或主入口冒烟验证，并检查重命名后的全部旧引用。
7. **~form 默认较高权限**：调用 `~form` 即授权计划列明的仓库内可恢复清理、常规提交、
   push 和最终标签；force push、改写已推送标签、系统配置、凭据操作和超过文件大小闸门的
   提交仍须单独确认。
8. **本地特化是最终产物**：每次在 Git 库执行本 skill，都要把与目标库实际结构相关的规则
   同步到根 `AGENTS.md`；不存在时创建该文件。目标库原有明确约定与通用规则冲突时保留原约定，并把冲突登记为本地例外，
   不能为了统一格式覆盖原规则。整改完成后还须生成本库的 `skills/form/SKILL.md`。
9. **标签名边界**：Git 标签名只用于版本定位和版本引用，可在更新说明、提交说明、注释、
   日志和审计记录中出现；不得进入文件、目录、对象、函数、变量、类型、字段、测试标识、
   配置键等名称。发现违规时必须整批重命名，并修复所有导入、引用、文档、配置和测试。
10. **Agent 规则文件只用复数名**：所有目录的 agent 指令文件统一为 `AGENTS.md`；
    `AGENT.md` 是历史输入错误，不是兼容别名。只存在单数文件时直接重命名为复数；同目录
    两者并存时，以 `AGENTS.md` 为主文件，先合并并去重 `AGENT.md` 中的有效规则，确认
    无内容丢失后再移除单数文件，并同步全部现行引用。历史日志可保留旧路径作为既往证据。
11. **参考库与自有内容分离**：参考 Git 库以 submodule 引入，路径为 `refer/git-rep/<name>`；
    本库对参考库的分析文档统一放 `refer/git-rep/docs/`，来源、用途和致谢写入
    `refer/git-rep/README.md`。不得把参考库整树拷贝进主库，也不得把本库文档写进子库工作树。

## Git 检查

有 Git 且本次产生文件改动时，执行 `git diff --check` 和定向复查。参考子库变更时同时检查
`.gitmodules`、gitlink 和 `refer/git-rep/README.md`，不暂存子库工作树内容。只读审计不提交；
完整 `~form` 流程按 Step 8 使用较高权限完成提交、推送和最终标签。任何提交前都运行
`scripts/form-large-files-check.sh`；命中超限暂存文件时该闸门优先于 `~form` 的常规较高权限。
无 Git 或无本次改动时立即跳过。

## 触发时机

- 用户要求格式审计或整改：“form”、“检查命名”、“统一目录”、“仓库规范化”、
  “按 skill 约定整改这个库”、“同步 AGENTS.md 和文档”。
- 名称中出现 `stabN`、`devN`、`bugN`、`testN` 等标签形片段，或需要确认标签名是否可用于
  更新说明、注释、日志及其他版本引用场景。
- 新库初始化或大型重构后，需要统一语言框架、文件/函数/变量/对象命名和顶层目录。
- 用户要求清理上一任务遗留的文档、日志、测试代码和非功能性文件，但必须保留 Git 回溯能力。
- 用户要求把通用格式约定特化到当前库，并在根 `AGENTS.md` 写明本地规则。
- 用户要求统一 `AGENT.md`/`AGENTS.md`，或修复 agent 规则文件的单复数命名冲突。
- 用户要求添加、更新或移除 `refer/git-rep` 参考 Git 库，或整理参考库的 README 来源/致谢与
  分析文档目录。
- `refer/git-rep/<name>` 是普通拷贝而不是 submodule，或本库分析文档散落在子库 `docs/` 内。
- 与其他技能配合：先读改动用 `diff`；多步骤方案用 `plan`；报错用 `debug`；
  功能回归用 `test`；最终同步用 `init`；完成后用 `tag(dev)`；
  日志命名与索引一致性用 `log`；技能自身的描述或结构问题用 `skill-creator`；
  多库只读审计可并行调用 `dispatch`；参考库分析文档由 `analy`/`pure`/`report` 产生时，
  按本 skill 的 `refer/git-rep/docs/` 位置归档。

## 参考文件

- `references/naming-and-layout.md`：名称质量、Git 标签边界、语言/构件命名矩阵、
  `logs/` 日志命名、文件夹白名单、参考 Git 子库布局、简单库与复杂库规则。
- `references/observed-conventions.md`：从固定明文快照归纳的 C++/Python/Bash/静态前端规则。
- `references/source-snapshots/README.md`：四个参考 URL 的提交、文件清单、排除项和校验方式。
- `references/git-artifacts-and-workflow.md`：目录职责、参考子库交付、清理边界、提交消息、
  验收和本地特化模板。
- `scripts/form-audit.sh`：只读检查已跟踪路径的顶层目录、代码文件名、docs/logs/data、测试位置
  和 `refer/git-rep` 子库/README/docs 基线。
- `scripts/form-agents-sync.sh`：把与目标库相关的 form 规则写入根 `AGENTS.md`
  的标记块；只更新标记块，保留块外全部本地约定。
- `scripts/form-large-files-check.sh`：只读检查暂存的新增、修改、复制或重命名文件，
  默认阻止单个索引 blob 超过 `10,000,000` 字节。
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

2. 读取与本次范围相关的根 `AGENTS.md`、各目录 `AGENTS.md`、
   构建/测试入口和现有 `skills/form/SKILL.md`；不递归读取无关文档。需要参考范例时，先读
   `references/observed-conventions.md`，再按其中的相对路径进入明文快照。
3. 逐项建立冲突表：

| 对象 | 类型 | 语言 | 当前名称/位置 | 预期规则 | 冲突 | 处理 |
|---|---|---|---|---|---|---|
| `path` 或 `symbol` | 文件/函数/变量/对象/目录 | cpp/python/bash/other | 实际值 | 引用规则 | 是/否/例外 | rename/move/update/keep |

4. 命名冲突必须保留 `文件:行号` 或路径证据；引用快照时同时给出快照根、commit 和文件行号。
   把真正例外单列，不把普通违规伪装成例外。
5. 审计 agent 规则文件命名。所有 `AGENT.md` 都是待整改对象：同目录没有
   `AGENTS.md` 时登记为重命名；同目录两者并存时登记为语义合并并删除单数文件。
   `form-audit.sh` 的 `AGENT_FILE_SINGULAR` 是确定性基线信号，合并内容仍须人工核对。
6. 审计参考 Git 子库布局。存在 `refer/git-rep/` 时：

```bash
git ls-files -s -- refer/git-rep
git submodule status -- refer/git-rep 2>/dev/null || true
test -f refer/git-rep/README.md && sed -n '1,160p' refer/git-rep/README.md
```

   - `refer/git-rep/<name>` 的索引模式必须是 `160000`；普通文件模式表示 vendored 拷贝，
     登记为待迁移。`.gitmodules` 必须有对应的 `path` 和 `url`。
   - `refer/git-rep/README.md` 必须存在，至少逐项写出子库来源 URL 和致谢；可参考 PyQCD
     仓库的 `refer/git-rep/README.md` 清单写法。缺项登记为待补。
   - 本库分析文档必须位于 `refer/git-rep/docs/`；若出现在非 gitlink 的
     `refer/git-rep/<name>/docs/`，先用 `git log --diff-filter=A` 和上游树确认归属，
     登记为待迁移，不直接改动子库工作树。
   - 子库工作树内的上游文件不属于本库整改范围，不读取、不修改、不纳入冲突表。
7. 检查名称质量和 Git 标签名边界。标签文法为
   `^(stab|dev|bug|test)[0-9]+(_[0-9]+)*$`；路径命中由审计脚本报告，符号命中需人工判定：

```bash
git grep -n -E '\b(stab|dev|bug|test)[0-9]+(_[0-9]+)*\b' -- \
  ':!skills/form/references/source-snapshots/**' ':!logs/**' || true
```

更新说明、提交说明、注释和日志中的标签引用是允许的版本证据；若标签出现在文件名、
目录名、对象、函数、变量、类型、字段、测试标识或配置键中，登记为违规并要求整批纠正。
8. 使用本地快照前校验完整性；任一失败都停止引用该快照，不使用损坏副本推断规则：

```bash
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-snapshot-verify.sh" --quiet
```

9. 运行 `~diff` 查看上一基线以来的改动；若尚未有基线，记录 `git status` 与当前提交作为基线。

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

1. 先运行目标库已有测试或冒烟命令，保存退出码；没有入口时明确记录验证缺口。
2. 对 `AGENT.md` 先执行语义迁移：同目录仅单数文件时使用 `git mv` 改为 `AGENTS.md`；
   两者并存时读取两份内容，将 `AGENTS.md` 作为主文件并合并去重单数文件中的有效规则，
   确认无误后删除 `AGENT.md`。历史日志可保留旧路径，现行脚本、配置和文档必须同步引用。
3. 先建/整理目录，再使用 `git mv` 或补丁做其他重命名；一次提交批内的移动与引用更新必须
   在同一逻辑批次完成。
4. 符号重命名后用仓库级搜索确认旧名清零，或只保留明确兼容别名：

```bash
rg -n --hidden --glob '!.git/**' '旧名称|OldName|old_name'
```

5. 标签名进入路径或标识符时，以业务语义重新命名；同时更新构建清单、导入、调用点、
   配置键、文档、测试、hook、脚本和 AGENTS.md，不能只改声明而保留旧引用。
6. 更新构建清单、导入、文档、注释、测试、hook、脚本和 AGENTS.md 中的全部引用。
7. 命名例外必须符合 `references/naming-and-layout.md` 的可观察条件；不能仅写“特殊”后跳过。
   新增规则来自快照时，在 `references/observed-conventions.md` 同步证据和适用边界。
7. 每个批次完成即运行该批次的最小验证，不把全部风险积累到最后。

### Step 5. 整理交付目录

1. `docs/` 仅保留本次任务文档及附件图片，格式限定为 TeX、PDF、Markdown 和图片。
2. `logs/` 仅保留 `AGENTS.md`、任务需求单、agent 三态日志、用户自定义历史日志，以及
   `log/json/tsv/csv/txt`；agent 日志必须符合 `vYYYYMMDD[HH[MM[SS]]].txt`、
   对应连字符格式或冲突后缀。清理前列出候选并检查是否被源码或脚本引用。
3. `data/` 汇集历史数据文件；通过 `.gitignore` 排除内容，仅保留 `.gitignore`、
   `AGENTS.md` 和 `README.md`。
4. 复杂库测试归入小写库名下的 `testing/`，简单库测试可保留在功能目录并采用
   `*.test.sh` 一类“小写点划分”入口；合并后的通用测试必须附可直接调用的脚本。
5. 测试入口应具备完整默认值，优先无参数即可运行；参数只用于覆盖默认行为。
6. 所有删除先展示候选、Git 保护状态和恢复命令；计划已列明且调用为 `~form` 时按较高权限
   执行，计划外候选不删除。
7. 参考 Git 子库按“先迁移本库分析文档、再移除旧拷贝、最后重建 submodule”的顺序规整。
   普通拷贝不是最终状态。示例：

```bash
# 1) 迁移本库添加的分析文档；上游自带文档留在子库内
mkdir -p refer/git-rep/docs
git mv refer/git-rep/<name>/docs/<file> refer/git-rep/docs/
# 2) 移除旧的 vendored 副本；先确认 Git 可回溯，残留项逐项确认
git rm -r -- refer/git-rep/<name>
# 3) 以 submodule 重新引入，保留上游仓库名
git submodule add <url> refer/git-rep/<name>
git submodule update --init --recursive -- refer/git-rep/<name>
```

   具体示例：

```bash
git submodule add https://gitee.com/zhangxin8069/PyQCU.git refer/git-rep/PyQCU
git submodule add https://github.com/IHEP-LQCD/EasyDistillation.git \
  refer/git-rep/EasyDistillation
```

   文档已跟踪时用 `git mv`；未跟踪时先登记来源，再用普通 `mv`，随后统一暂存。
   `git rm -r` 只删除已跟踪内容；若旧目录还含 `.git` 或未跟踪残留，先列出并确认来源，
   再按计划清理，不能为了 `git submodule add` 成功而静默 `rm -rf`。旧目录未被跟踪时，
   先按清理边界确认，再删除工作树副本。禁止用 `git add -A` 或 `git add .` 把整树加入主库。
   已经正确配置的 submodule 只更新 README 或执行 `git submodule update`，不要无谓删除重建；
   URL 变更用 `git submodule set-url <path> <url>` 并同步 README。
8. 更新 `refer/git-rep/README.md`：至少逐项写出子库 `path`、来源 URL、用途和致谢；
   参考 PyQCD 的清单式写法时也要补齐缺失项，不能只留链接列表。README 与 `.gitmodules`、
   gitlink 在同一批次提交。
9. 验证参考子库布局：

```bash
git ls-files -s -- refer/git-rep/<name>   # 期望 160000
git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url)$'
git submodule status -- refer/git-rep
test -d refer/git-rep/docs && find refer/git-rep/docs -maxdepth 1 -type f | sort
```

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
5. 参考子库变更时额外验证：

```bash
git submodule status -- refer/git-rep
git ls-files -s -- refer/git-rep | awk '$1=="160000"'
git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url)$'
test -f refer/git-rep/README.md
test -d refer/git-rep/docs && find refer/git-rep/docs -maxdepth 2 -type f | sort
```

   确认每个参考目录是 gitlink、README 有来源/致谢、本库分析文档只在 `refer/git-rep/docs/`；
   上游文件仍在子库工作树内。`form-audit.sh` 的 `REFERENCE_DOC_MISPLACED`、
   `REFERENCE_README_MISSING`、`REFERENCE_SUBMODULE_METADATA` 和
   `REFERENCE_README_SOURCE_MISSING` 是确定性基线信号，最终以索引模式和
   `git submodule status` 判定。
6. 若测试失败，转 `~debug` 定位根因，不以修改期望值或删除测试绕过；修复后重跑完整验证。

### Step 7. 生成当前库特化版本

1. 无论是否执行了重命名或目录整改，都把本 skill 中与目标库实际类型相关的规则投影到根
   规则文件。先读取根 `AGENTS.md`；不存在时由同步脚本创建根 `AGENTS.md`。
2. 根据 Step 2 的审计结果生成本库专用的 `form` 标记块，至少写明：
   - 库类型与主导语言；
   - 文件、函数、变量、对象和目录命名规则；
   - 允许的顶层目录及各目录职责；
   - 测试入口和功能复现命令；
   - 参考 Git 子库布局：`refer/git-rep/<name>` 必须是 submodule，README 记录来源/致谢，
     本库分析文档放 `refer/git-rep/docs/`，子库工作树只读；
   - Git 交付、标签、清理边界与 `10,000,000` 字节大文件闸门；
   - 根规则文件中的优先级：目标库原有明确约定 > 本 skill 通用规则；
   - 仅限本库的已批准例外。
   只写入与目标库有关且可执行的规则，不复制无关语言或目录模板。与根文件原有约定冲突的
   通用规则不得写入；保留原约定，并在冲突表中记录“本地原约定优先”。
3. 将待同步内容放入临时文件，调用确定性同步器：

```bash
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-agents-sync.sh" \
  --root "$REPO_ROOT" \
  --content "$form_section_file"
"$FORM_SKILL_DIR/scripts/form-agents-sync.sh" \
  --root "$REPO_ROOT" \
  --content "$form_section_file" \
  --check
```

脚本使用 `<!-- form-skill:start -->` / `<!-- form-skill:end -->` 管理唯一区块，幂等更新，
不改写标记块外内容。目标库已有未标记的同义章节时，先把其中有效本地规则纳入
`form_section_file`，再同步，避免产生相互矛盾的重复条目。标记不完整或重复时停止，
修复标记后再运行，不能绕过脚本手工覆盖整份根规则文件。
4. 将本 skill 的通用流程与目标库实际语言、目录、入口、例外和验证命令合成
   `skills/form/SKILL.md`；已存在时保留有效本地信息并补齐，不直接覆盖旧规则。
5. 同步相关目录 `AGENTS.md`、README、注释和 skill 表；删除已失效说明，保留历史依据。
6. 重新执行 Step 6，确认文档/配置同步没有破坏功能。

### Step 8. Git 交付与收尾

`~form` 默认较高权限覆盖以下常规交付；出现 force push、改写已推送标签或仓库外写入时停止：

1. 调用 `~diff` 审计全部本次改动；不得使用 `git add -A` 或 `git add .`，只逐个暂存本任务文件。
   参考子库变更同时暂存 `.gitmodules`、gitlink 和 `refer/git-rep/README.md`，不暂存子库工作树内容。
2. 每批暂存后、提交前运行大文件闸门：

```bash
FORM_SKILL_DIR=${FORM_SKILL_DIR:-skills/form}
"$FORM_SKILL_DIR/scripts/form-large-files-check.sh" --root "$REPO_ROOT"
```

默认阈值为 `10,000,000` 字节，可通过 `--max-bytes` 或
`FORM_MAX_COMMIT_FILE_BYTES` 显式覆盖。检查非零退出时立即停止该批次提交和推送，明确列出
超限路径与字节数并提醒用户。等待 5 分钟后仍无回复时，只继续推进不依赖超限文件的工作；
静默不构成提交超限文件的授权，覆盖阈值必须由用户明确要求。
3. 每个独立整改批次生成详实提交消息，结构见
   `references/git-artifacts-and-workflow.md`；参考子库批次在消息中写明新增/迁移/重建
   submodule 及 README/docs 变化。提交后推送当前分支，禁止 force push。
4. 调用 `~init` 同步 AGENTS.md 和 agent 配置归档；随后调用 `~tag(dev)` 保存开发快照。
5. 在 `docs/` 写入该技术任务的 Markdown 文档，记录目标、冲突表摘要、改动、验证证据、
   未决项和恢复方法；参考子库的分析文档写入 `refer/git-rep/docs/`，不要混入顶层
   `docs/`。文档纳入最终提交与推送。
6. 最终确认本地分支、远程分支和 `dev` 标签指向同一验收提交，并确认标签已推送；
   有漂移时停止并报告，不猜测远程状态。

## 验收矩阵

| 维度 | 证据 | 通过条件 |
|---|---|---|
| 规则来源 | 快照 metadata、commit、manifest、SHA-256 | 使用的四条示例规则均来自固定提交，校验通过 |
| 目录布局 | `form-audit.sh` TSV 输出、根 AGENTS 白名单 | 计划内冲突清零，例外逐条登记 |
| 文件命名 | 自动 TSV、文件路径、重命名后旧引用搜索 | 代码文件名符合规则，兼容例外有理由 |
| 符号命名 | 审计表 `文件:行号`、公开接口清单 | 函数/变量/对象逐项判定，例外可追溯 |
| 名称质量与标签边界 | 路径审计、`git grep`、冲突表、旧引用搜索 | 名称简短且语义完整；标签名只作版本引用，不进入路径或标识符 |
| Agent 规则文件名 | `form-audit.sh` 的 `AGENT_FILE_SINGULAR`、双文件 diff、合并后旧文件检查 | 全库无 `AGENT.md`；双文件内容已合并去重，现行引用全部指向 `AGENTS.md` |
| 交付目录 | docs/logs/data/testing 清单、`AGENTS.md` 索引、`v*` 日志命名审计 | 内容类型、日志命名、索引位置和职责符合边界 |
| 参考子库 | `git ls-files -s`、`.gitmodules`、`git submodule status`、README、`refer/git-rep/docs` | 每个参考目录为 `160000` gitlink；README 有来源/致谢；本库分析文档只在 `refer/git-rep/docs/`；无普通拷贝残留 |
| 根规则同步 | `form-agents-sync.sh --check`、根规则文件 diff | 标记块存在且为当前版本；块外本地约定逐字保留；冲突项以本地原约定为准 |
| 功能复现 | 构建、测试、主入口冒烟命令与退出码 | 整改前后同一验证集通过；缺口明确写出 |
| 大文件闸门 | `form-large-files-check.sh` 输出与退出码 | 暂存新增、修改、复制或重命名文件均不超过 `10,000,000` 字节；命中时本批次未提交 |
| Git 收尾 | diff、init、dev tag、远程对象 | 提交消息有意义，分支与标签指向验收提交 |

## 错误处理

| 场景 | 处理 |
|---|---|
| 库名大小写无法判定类型 | 以大小写规则给默认值，并把“可能误分类”列为待确认项；用户指定优先 |
| 工作区已有改动 | 先区分本任务与用户改动，只记录不覆盖；无法安全分离时停止写操作 |
| 文件重命名破坏引用 | 用 `~debug` 定位全部引用点，将移动和引用更新合并为同一批次后重试 |
| `AGENT.md` 与 `AGENTS.md` 并存 | 以 `AGENTS.md` 为主文件合并双方有效内容，确认无规则丢失后删除 `AGENT.md` 并更新现行引用 |
| 标签名进入路径或标识符 | 按业务目的重命名，并同步导入、配置、文档、测试和旧引用；历史日志中的版本引用可保留 |
| 规则与功能约束冲突 | 保留功能正确性，建立具名例外并写入根 AGENTS；不能 silent 跳过 |
| 通用规则与根文件原约定冲突 | 保留原约定，不复制冲突的通用规则；把冲突和本地例外写入审计表 |
| 根规则标记缺失、重复或未闭合 | 停止同步并修复标记；不得覆盖整份根规则文件或绕过检查 |
| 暂存文件超过大小闸门 | 立即停止该批次提交与推送，报告路径和字节数；5 分钟无回复只继续无依赖工作，静默不授权覆盖 |
| 参考库是普通拷贝而非 submodule | 先迁移本库 docs 并确认归属，再移除旧拷贝，使用 `git submodule add <url> <path>` 重建；不直接暂存整树 |
| 本库分析文档写在子库 `docs/` 内 | 迁移到 `refer/git-rep/docs/`，更新 README 和引用；子库工作树保持上游状态 |
| `refer/git-rep/README.md` 缺来源/致谢 | 补齐每个子库的 path、URL、用途和致谢；与 `.gitmodules`、gitlink 同批提交 |
| `git submodule add` 失败 | 检查 URL、网络/凭据和目录残留；保留已迁移文档，不静默删除或伪装成功；重试仍失败则报告阻塞 |
| 子库工作树有本地修改 | 先取证并区分本库与上游内容；不覆盖、不提交子库内容；计划外停止 |
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
- 标签名可作为更新说明、注释和日志中的版本引用，但不能替代名称本身应表达的业务语义。
- 目录白名单之外的名称只有用户明确批准或目标库特化规则明确登记后才能保留。
- 清理不等于删除历史；需要回顾旧文件时使用 `git show <revision>:<path>`。
- `data/` 中的历史数据默认不作为提交对象，文档和日志不得混入数据目录。
- 根规则同步只更新标记块；本库特有规则和例外写在块外或纳入下一次待同步内容，不能依赖
  人工覆盖整份 `AGENTS.md`。
- 大文件闸门只报告并阻止提交，不自动删除、移动或取消暂存用户文件；处理方式由用户决定。
- `refer/git-rep/` 下的子库是外部内容，只读使用；本库分析文档写入 `refer/git-rep/docs/`，
  不写进子库的 `docs/`。
- 参考库来源以 `.gitmodules` 的 URL 和 `refer/git-rep/README.md` 双重记录；README 至少要有
  可定位的来源 URL 和致谢。
- `git submodule add` 的 `<name>` 保留上游仓库名大小写，属于 `refer/**` 名称例外，不强制小写。
- 修改任一步脚本后运行 `scripts/form-scripts.test.sh`；修改快照后立即运行
  `scripts/form-snapshot-verify.sh`，以测试和哈希输出作为脚本可用性的证据。
- 本 skill 负责格式治理，不替代 `debug`、`test`、`optim` 或 `tag` 的专业实现。
