# form 交付目录、Git 流程与本地特化

## 1. 交付目录边界

| 目录 | 允许内容 | 清理规则 |
|---|---|---|
| `docs/` | 本次任务 TeX、PDF、Markdown、图片附件 | 不保留旧任务临时文档；历史需要时用 Git 回溯 |
| `logs/` | 本次任务 `log/json/tsv/csv/txt`；用户自定义历史日志 | 清理候选先查引用，保留用户历史日志 |
| `data/` | 历史任务 `h5/hdf5/pt/npy/npz/lime` 等数据 | `.gitignore` 排除内容，只跟踪说明和忽略文件 |
| `<lowercase-repo>/testing/` | 复杂库测试代码与调用脚本 | 按功能组织；通用测试合并后保留默认可运行入口 |
| 简单库功能目录 | `*.test.sh` 与简单 smoke 测试 | 清理失败实验与重复脚本，保留可复用回归 |

`data/.gitignore` 应至少包含：

```gitignore
*
!.gitignore
!AGENTS.md
!README.md
```

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
5. 清理清单必须在整改计划中逐项展示。删除前记录：

```bash
git rev-parse HEAD
git show HEAD:<path> >/dev/null
```

需要回顾时使用 `git show <revision>:<path>` 或 `git restore --source=<revision> -- <path>`。

## 3. 提交消息

一次提交只承载一个逻辑批次，消息使用有实际意义的领域词，禁止引用标签名作为语义：

```text
<type>(<scope>): <purpose>

原因:
- <为什么需要整改>

改动:
- <目录/文件/符号改动>

验证:
- <命令与结果摘要>
```

`type` 可采用 `refactor`、`docs`、`test`、`fix`、`chore`；`scope` 使用真实模块名。

## 4. 分批交付

1. 每批开始前保存功能基线，批次结束后运行最小相关验证。
2. 只暂存本任务文件；禁止 `git add -A` 和 `git add .`。
3. 每个批次保持可构建、可回退；大范围重命名不能拆成“先全部移动、后全部修引用”。
4. 推送前检查远端漂移；普通快进失败先取回并分析，禁止 force push。
5. 最终功能复现通过后才创建或推送最终标签。

## 5. 结束流程

完整交付顺序：

```text
form 审计与整改
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

目标库根 `AGENTS.md` 至少包含以下可执行内容；可按库情况增减字段，但不能只留外部链接：

```markdown
## form 格式约定

- 库类型: <simple|complex>。
- 主导语言: <cpp|python|bash|other；混合库列出各目录>。
- 文件命名: <include/src/main 规则>。
- 函数命名: <公开接口/内部函数规则>。
- 变量命名: <宏/普通变量/内部变量规则>。
- 对象命名: <公开对象/内部对象规则>。
- 顶层目录白名单: <本库允许集合及职责>。
- 测试入口: `<可直接执行的命令>`。
- 功能复现: `<构建、测试、主入口冒烟命令>`。
- 文档/日志/数据: <目录职责和保留规则>。
- Git 交付: <提交、推送、标签流程；禁止强推>。
- 本地例外: <每一项的可观察条件、示例和理由；无则写“无”>。
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
根 AGENTS.md 为准。若两者冲突，根 AGENTS.md 的已批准本地规则优先。
```

特化文件仍须满足本目录的技能公共契约、触发时机、工作流程、错误处理和注意事项结构。
