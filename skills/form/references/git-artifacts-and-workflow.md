# form 交付目录、Git 流程与本地特化

## 1. 交付目录边界

| 目录 | 允许内容 | 清理规则 |
|---|---|---|
| `docs/` | 本次任务 TeX、PDF、Markdown、图片附件 | 不保留旧任务临时文档；历史需要时用 Git 回溯 |
| `logs/` | `AGENTS.md` 索引、任务需求单、agent 三态时间戳日志、`log/json/tsv/csv/txt` 工具/历史日志 | 检查 `vYYYYMMDD[HH[MM[SS]]].txt` 命名；清理候选先查引用，保留用户历史日志 |
| `data/` | 历史任务 `h5/hdf5/pt/npy/npz/lime` 等数据 | `.gitignore` 排除内容，只跟踪说明和忽略文件 |
| `refer/git-rep/` | Git 参考子库（submodule）、`README.md` 来源/致谢、`docs/` 本库分析文档 | 子库工作树保持上游状态；普通拷贝先迁移 docs 再重建为 submodule |
| `<lowercase-repo>/testing/` | 复杂库测试代码与调用脚本 | 按功能组织；通用测试合并后保留默认可运行入口 |
| 简单库功能目录 | `*.test.sh` 与简单 smoke 测试 | 清理失败实验与重复脚本，保留可复用回归 |

`data/.gitignore` 应至少包含：

```gitignore
*
!.gitignore
!AGENTS.md
!README.md
```

该规则必须同时存在于根 `.gitignore` 和 `data/.gitignore`，形成双层防护。`data/cache/**` 没有
例外：cache 可能保存隔离 agent HOME、会话、SQLite/WAL、shell 快照和凭据；禁止 `git add -f`，
禁止从审计中用 `--exclude '^data/'` 隐藏 `TRACKED_DATA_CONTENT`。发现泄露时先吊销/轮换凭据，
再移除索引并处理远端历史；历史改写不能替代轮换。

### 1.1 参考子库交付

参考 Git 库统一以 submodule 放在 `refer/git-rep/<name>`，来源和致谢写入
`refer/git-rep/README.md`，本库分析文档写入 `refer/git-rep/docs/`。普通拷贝不是最终状态。

迁移顺序：

```bash
# 1) 先迁移本库添加的分析文档；已跟踪文件用 git mv
mkdir -p refer/git-rep/docs
git mv refer/git-rep/<name>/docs/<file> refer/git-rep/docs/
# 2) 移除旧拷贝；先确认 Git 可回溯，残留项逐项确认
git rm -r -- refer/git-rep/<name>
# 3) 以 submodule 重建，保留上游仓库名
git submodule add <url> refer/git-rep/<name>
git submodule update --init --recursive -- refer/git-rep/<name>
```

示例：

```bash
git submodule add https://gitee.com/zhangxin8069/PyQCU.git refer/git-rep/PyQCU
git submodule add https://github.com/IHEP-LQCD/EasyDistillation.git \
  refer/git-rep/EasyDistillation
```

- 文档已跟踪时用 `git mv`；未跟踪时先确认来源，再用普通 `mv`，随后统一暂存。
- `git rm -r` 不删除未跟踪残留或 `.git` 目录；残留项须逐项确认后清理，不能为了
  `git submodule add` 成功而静默 `rm -rf`。
- 已经正确配置的 submodule 只更新 README 或执行 `git submodule update`，不删除重建；
  URL 变更用 `git submodule set-url <path> <url>` 并同步 README。
- 提交时同时暂存 `.gitmodules`、gitlink 和 `refer/git-rep/README.md`；不暂存子库工作树内容，
  不使用 `git add -A` 或 `git add .`。
- 验证：`git ls-files -s -- refer/git-rep/<name>` 为 `160000`；
  `git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url)$'` 有对应项；
  `git submodule status -- refer/git-rep` 正常。

## 2. 大任务开始检查

1. 确认范围和 Git 根目录；仓库外内容不读取、不修改。
2. 检查工作区、远程分支和上一标签：

```bash
git status --short --branch
git log -1 --oneline --decorate
git tag --list --sort=-creatordate | head -n 10
```

3. 将上一任务留下的候选文件分为：必需功能、可恢复文档、日志、测试、数据、临时产物。
4. 使用引用搜索和 `git log --diff-filter=A --` 判断文件来源；不能确认用途时列入计划等待
   默认较高权限覆盖，仍无法判定内容归属的保留。
5. 存在 `refer/git-rep/` 时，检查每个参考目录是 gitlink 而非普通拷贝，README 有来源/致谢，
   本库分析文档在 `refer/git-rep/docs/`；不符合项列入整改计划。
6. 清理清单必须在整改计划中逐项展示。删除前记录：

```bash
git rev-parse HEAD
git show HEAD:<path> >/dev/null
```

需要回顾时使用 `git show <revision>:<path>` 或 `git restore --source=<revision> -- <path>`。

## 3. 提交消息

一次提交只承载一个逻辑批次，消息使用有实际意义的领域词。标签名可作为版本定位引用，
但不能代替对真实目的的说明：

```text
<type>(<scope>): <purpose>

原因:
- <引用必要标签时说明版本背景，并写清为什么需要整改>

改动:
- <目录/文件/符号改动>

验证:
- <命令与结果摘要>
```

`type` 可采用 `refactor`、`docs`、`test`、`fix`、`chore`；`scope` 使用真实模块名。
例如 `follow dev26, 修复解析器边界条件` 允许使用 `dev26` 作为版本背景，但真正的提交目的
仍必须由“修复解析器边界条件”表达。参考子库批次在 `scope` 中写明 `refer/git-rep`，说明
新增、迁移或重建的 submodule 以及 README/docs 变化。

## 4. 分批交付

1. 每批开始前保存功能基线，批次结束后运行最小相关验证。
2. 只暂存本任务文件；禁止 `git add -A` 和 `git add .`。
3. 每批暂存后运行 `scripts/form-large-files-check.sh --root "$REPO_ROOT"`。默认禁止
   单个索引 blob 超过 `10,000,000` 字节；命中时该批次不得提交或推送。
4. 超限提醒后等待 5 分钟；无回复时继续不依赖该文件的工作，但静默不构成提交授权。
   只有用户明确要求覆盖阈值时，才可使用 `--max-bytes` 或
   `FORM_MAX_COMMIT_FILE_BYTES` 继续该超限批次。
5. 每个批次保持可构建、可回退；大范围重命名不能拆成“先全部移动、后全部修引用”。
6. 推送前检查远端漂移；普通快进失败先取回并分析，禁止 force push。
7. 最终功能复现通过后才创建或推送最终标签。
8. 参考子库批次同时暂存 `.gitmodules`、gitlink 和 `refer/git-rep/README.md`；子库工作树
   内容不进入主库索引。

## 5. 结束流程

完整交付顺序：

```text
form 审计与整改（含 refer/git-rep 参考子库）
→ 功能复现
→ ~diff
→ ~init
→ ~tag(dev)
→ docs 任务文档
→ 最终提交/推送/标签验证
```

每个阶段保留命令、退出码和关键输出作为证据。失败时转入 `debug`，修复后从失败的最早
可验证点重新执行，不跳过失败批次。

`~form` 调用默认提供较高权限，覆盖计划内仓库清理及常规提交、push、标签；force push、
改写已推送标签、系统配置和凭据操作必须单独确认。

## 6. 根 AGENTS.md 本地章节模板

每次在 Git 库运行 `form` 都同步根规则文件 `AGENTS.md`；不存在时创建。同步器只更新
`<!-- form-skill:start -->` 与 `<!-- form-skill:end -->` 之间的区块，块外原有约定保持不变。
根规则文件名和所有目录级 agent 指令文件只能使用 `AGENTS.md`；`AGENT.md` 是历史输入
错误。两者并存时先合并有效内容并去重，再删除单数文件并同步全部现行引用。

目标库根规则文件至少包含以下可执行内容；可按库情况增减字段，但不能只留外部链接：

```markdown
<!-- form-skill:start -->
## form 格式约定

> 目标库原有明确约定与本节通用规则冲突时，以原有约定为准；用户明确指令优先于二者。

- 库类型: <simple|complex>。
- 主导语言: <cpp|python|bash|other；混合库列出各目录>。
- 文件命名: <include/src/main 规则>。
- 函数命名: <公开接口/内部函数规则>。
- 变量命名: <宏/普通变量/内部变量规则>。
- 对象命名: <公开对象/内部对象规则>。
- 名称质量与标签边界: <名称清晰简短且语义完整；标签名只可作版本引用，禁止进入路径或标识符>。
- 顶层目录白名单: <本库允许集合及职责>。
- 测试入口: `<可直接执行的命令>`。
- 功能复现: `<构建、测试、主入口冒烟命令>`。
- 文档/日志/数据: `<docs/>` 职责；`logs/AGENTS.md` 索引与 `vYYYYMMDD[HH[MM[SS]]].txt` 日志命名；`data/` 忽略与保留规则。
- 参考 Git 库: 统一以 submodule 放在 `refer/git-rep/<name>`；`refer/git-rep/README.md` 记录来源与致谢；本库分析文档放 `refer/git-rep/docs/`，子库工作树只读。
- Git 交付: <提交、推送、标签流程；禁止强推>。
- Git 大文件: 除用户明确要求外，禁止提交单个大于 `10,000,000` 字节的文件；每批暂存后运行 `scripts/form-large-files-check.sh`，命中时停止提交并提醒。
- 本地例外: <每一项的可观察条件、示例和理由；无则写“无”>。
<!-- form-skill:end -->
```

## 7. 特化 skill 模板

目标库的 `skills/form/SKILL.md` 保留通用流程，并明确以下覆盖项：

```markdown
---
name: form
description: |
  当用户要求审计或整改本库 <库名> 的命名、目录、框架、文档、日志、数据、
  测试布局、清洁度与 Git 交付格式时使用。
metadata:
  openclaw:
    emoji: 📐
---

# form — <库名> 格式治理

遵循本库根 `AGENTS.md` 的 form 章节；本库为 <simple|complex>，主导语言为 <语言>。
通用决策读取全局 form 的 references，本地框架、例外、验证命令和目录白名单以本库
根 AGENTS.md 为准。参考子库统一放在 `refer/git-rep/<name>`，来源/致谢和分析文档位置
以根 AGENTS.md 为准。若两者冲突，根 AGENTS.md 的已批准本地规则优先。
```

特化文件仍须满足本目录的技能公共契约、触发时机、工作流程、错误处理和注意事项结构。
