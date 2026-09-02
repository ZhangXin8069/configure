---
name: fast
description: |
  Use when the user prefixes a task with `~fast` or explicitly requests fast,
  token-efficient, resource-conscious execution with fewer iterations or higher throughput.
metadata:
  openclaw:
    emoji: ⚡
---

# fast — 多快好省修饰技能

## 执行前置

遵循当前目录 `AGENTS.md`「技能执行公共契约」；fast 是修饰层，不替代被修饰技能的领域规则。
先把 fast 上下文附着到整条技能链，再按下列预算和质量闸门执行。它不新增权限，也不改变
提交、推送、删除或系统配置的授权边界。

## 核心原则

1. **修饰而非执行**：fast 只改变任务编排、输出轻量化和迭代预算；具体领域判断仍由目标技能负责，避免用通用提速规则替代物理、代码或验证知识。
2. **全链路继承**：fast 是当前任务的上下文属性；auto、all 及其后续子技能都携带它，且同一条链只添加一次，避免外层提速、内层恢复原流程的失配。
3. **优化关键路径**：优先合并重复读取/分析/复查、并行无共享状态的工作、减少低信息量产物；不以删掉关键证据换取表面速度。
4. **共享全局预算**：整条任务默认最多 3 轮，轮数由外层统一计数；用户明确指定全局轮数时，该值是 fast 的可见例外，子技能不能再各自叠加轮数，防止嵌套预算相乘。
5. **明确收益阈值**：fast 激活时，auto 的默认边际收益停止条件由 `<5%` 调整为 `<25%`；实际循环由 all 承担时也采用同一有效阈值，用户明确指定的收益阈值优先。
6. **质量先过硬闸门**：正确性、安全性、关键证据、用户明确要求和失败修复不可压缩；质量下限不满足时，不得用“更快”宣称收敛。
7. **轻量输出可逆**：analy、pure、report 的默认 effective_format 是 Markdown；这只替换默认载体，不删除公式、证据链、来源行号和结论边界。
8. **收益以证据为准**：3 倍效率是验收目标而非自动事实；没有同输入、同环境的无 fast 对照时，只能报告估计或未验证。

## 触发时机

- 用户使用 `~fast` 前缀，或明确提出“快一点”“少用 Token”“降低资源”“多快好省”“减少重复迭代”等要求。
- 用户输入 `~fast <任务>` 且未指定执行技能：逻辑展开为 `~fast+auto+all <任务>`。
- 用户输入 `~fast~<技能> <任务>`：保留显式目标，例如 `~fast~report`；不因 fast 而再次插入 `auto/all`。
- fast 已激活后，任何后续子技能调用都继承 fast，例如 `~report` 规范化为 `~fast~report`；已经带 fast 的调用不重复添加。
- 与其他技能配合：auto 负责一次性授权和无人值守，all 负责收敛编排，dispatch 负责独立子任务并行，test/debug/review 负责质量验证，diff 负责最终改动复查。
- 约束优先场景：用户明确要求完整原流程、固定测试/复查数量或指定输出格式时，仍可使用 fast，但这些要求成为 fast 的保留约束。

## 工作流程

### Step 1. 规范化技能链与例外

把本次任务抽象为 `fast_context + base_chain`，其中 `base_chain` 是用户显式指定的技能链，缺省才使用
`auto+all`。逻辑示例如下：

```text
~fast 任务              => ~fast+auto+all 任务
~fast~report 任务       => ~fast~report 任务
fast 上下文 + ~report   => ~fast~report
fast 上下文 + ~auto     => ~fast~auto
```

把用户明确写出的格式、数量、精度、覆盖范围、验证要求和全局轮数登记为保留约束。采用以下固定优先级：

1. 安全性、正确性和硬性验证闸门；
2. 用户明确要求或明确声明的 fast 例外；
3. fast 的默认修饰（本节列出的预算、阈值和默认载体）；
4. 被修饰技能的普通默认值。

因此，用户写出“fast 下保留 5 轮”时使用 5 轮；用户只写“保留 5 次复查”时保留 5 次复查，但不自动把全局轮数改为 5。

### Step 2. 建立一次性 fast 预算

在首轮摘要中固定以下上下文，并传给每个子技能：

```text
mode=fast
global_rounds_max=3
optimization_gain_stop=<25%>
quality_ratio_min=0.60
format_default=Markdown for analy/pure/report
format_override=<explicit user format or none>
effective_format=<format_override or Markdown>
```

`optimization_gain_stop` 只表示边际优化收益低于 25% 时停止继续优化，不表示允许接受测试失败、无证据
结论或安全违规。用户明确设置全局轮数或收益阈值时，替换对应默认字段；auto 的原有授权仍有效，L2 仍跳过破坏性操作。
格式字段按 `effective_format = format_override（有值时）否则 Markdown` 计算；下游技能只读取
`effective_format` 选择 Markdown 或普通 LaTeX/PDF 分支，不能从自己的普通默认值重新推断格式。

每次调用子技能时都传递同一份 `fast_context`，并要求子技能在阶段摘要中回显有效值：

```text
fast.active=true
fast.global_rounds_max=<3 or explicit exception>
fast.optimization_gain_stop=<25% or explicit exception>
fast.quality_ratio_min=0.60
fast.format_override=<explicit user format or none>
fast.effective_format=<Markdown or explicit user format>
fast.format_default=Markdown for analy/pure/report
fast.explicit_overrides=<user-stated constraints>
```

子技能对 fast 标记字段采用上述有效值，不再回退到自己的普通默认值；auto/all 必须在每个轮数守卫和
收益收敛判断前读取 `global_rounds_max`/`optimization_gain_stop`，并在阶段摘要回显最终有效值；
analy/pure/report 必须在生成产物前读取 `effective_format`。未列入 fast 标记字段的领域规则仍由子技能负责。

### Step 3. 压缩工作分解

按“保留约束 → 信息增益 → 关键路径”排序处理：

| 原工作 | fast 默认处理 | 保留条件 |
|---|---|---|
| analy 与 pure 重复建立底稿 | 合并为一份整体结构/核心细节证据图 | 公式、符号、代码映射、来源行号仍齐全 |
| 无共享状态的多个子任务 | 通过 dispatch 并行 | 写集、设备和外部资源互不冲突 |
| 5 组高度重复参数 | 可压缩为名义、边界、退化/错误 3 类 | 用户未指定数量，且覆盖矩阵仍闭合 |
| 5 次重复复查 | 可合并为需求/正确性/最终产物 3 个检查面 | 每个关键断言至少有一次实际证据 |
| analy/pure/report 的默认重型输出 | 改用 Markdown | 用户未明确要求 PDF、LaTeX、幻灯片或版式验收 |
| 多次搭建同一测试/报告辅助流程 | 共享一次脚本、证据清单和断言 | 不隐藏中间结果，不改变测试含义 |

不得把“可压缩”理解成自动删除：先检查用户约束和覆盖矩阵，再执行合并或抽样。共享写入或有顺序
依赖的工作保持串行；压缩失败时恢复该部分完整流程，不继续削减。
测试用例数和复查次数是下游验收计数，不等于全局轮数；用户明确指定的数量必须保留，且不因 fast 默认三轮而被误删。

### Step 4. 执行全局预算

默认三轮是全局的“评估 → 一个主导动作 → 回归验证”，而不是每个子技能的一轮。用户明确指定更大的全局轮数时，
按该例外执行，但仍共享一个外层计数器：

1. **首轮**：完成最小可交付结果，合并分析与重复准备工作，启动可并行支线。
2. **第二轮**：只修复阻断性错误、关键证据缺口和高风险回归。
3. **最后一轮**：只做高收益优化和最终验收；收益低于 25% 或硬闸门已全部通过时提前结束。

有失败时先 debug；有性能问题且硬闸门通过时再 optim。fast 预算耗尽仍未满足质量下限时停止并报告，不能
为了达到“3 倍”继续追加隐性轮次。

### Step 5. 应用 Markdown 默认与下游传播

当 `fast_context.effective_format=Markdown` 到达 analy、pure 或 report：

- 默认交付 Markdown，使用标题、Markdown 表格、代码围栏和 `$...$`/`$$...$$` 数学表达式；
- 保留结论—证据—含义—下一步主线、`文件:行号`、未验证项和关键物理/代码边界；
- Markdown 模式验证结构、链接、代码围栏、公式分隔符和证据可追溯性；不虚报未执行的 PDF 编译或版式验收；
- 用户明确要求 PDF/LaTeX/16:9 幻灯片时，先把该要求写入 `format_override`，使 `effective_format` 进入普通分支；fast 只压缩其分析、准备和复查编排。

### Step 6. 验收效率、质量并汇总

记录同输入、同环境下的可比指标：优先关键路径墙钟时间，辅以总 Token、工具/子代理调用数和人工交互数。
效率目标为：

```text
speedup = no_fast_cost / fast_cost >= 3
quality_ratio = fast_quality / no_fast_quality >= 0.60
```

质量评估先检查硬闸门（正确性、安全性、范围、关键证据、必要测试）是否全部通过，再比较覆盖率、可复现性
和可读性等软指标。`quality_ratio_min=0.60` 是相对无 fast 基线的比例下限，不是允许绝对质量降到 60%；
没有无 fast 对照或客观评分时，在汇总中写“未验证”，不把计划缩短当作实测收益。
质量评估先检查硬闸门（正确性、安全性、范围、关键证据、必要测试）是否全部通过，再用同一评分表比较
事实/正确性、需求覆盖、证据可追溯/可复现、可读性四项 0–100 分软指标的平均值。
`quality_ratio_min=0.60` 是相对无 fast 基线的比例下限，不是允许绝对质量降到 60%；没有同输入同环境基线或
同一评分表的客观评分时，在汇总中写“未验证”，不把计划缩短当作实测收益。

最终摘要至少包含：实际技能链、保留/压缩项、全局轮数、格式、效率指标状态、质量闸门状态、未验证项和遗留风险。

## Git 检查

有 Git 且本次产生文件改动时，执行 `git diff --check`、`git diff --stat` 和逐文件定向复查；不自动暂存、提交或推送。
无 Git 或无本次改动时跳过。

## 错误处理

| 场景 | 处理 |
|---|---|
| 用户明确指定格式、数量、完整流程或全局轮数 | 将格式写入 `format_override`、将数量写入 `explicit_overrides` 并保留；明确的全局轮数是 fast 默认 3 轮的例外，fast 仅优化不与之冲突的编排 |
| auto/all 仍按 `<5%` 优化收益继续 | 重新注入 fast 上下文，将有效停止阈值设为 `<25%`；用户显式阈值除外 |
| 预计或实测效率低于 3 倍 | 先合并重复工作、缩短关键路径并并行独立支线；仍达不到则诚实报告未达标，不删硬闸门 |
| 质量比低于 0.60 或硬闸门失败 | 停止低价值优化，恢复必要验证/完整路径，在有效 fast 轮数预算内修复；无法修复则报告失败 |
| 子技能存在共享写入、顺序依赖或设备冲突 | 不并行该部分，保留串行并压缩重复准备 |
| 子技能不识别 fast 传播 | 传递上述 `fast_context` 一次；仍不兼容时标注该阶段未应用 fast，不伪造结果 |
| fast 轮数预算耗尽仍需继续 | 停止自动迭代并报告剩余风险；只有用户显式开启新一轮任务才继续 |
| 触及删除、force push、系统配置等破坏性操作 | 遵循现有授权流程；fast 不提供额外授权 |

## 注意事项

- `{~fast+auto+all}`、`{~fast~report}` 是技能链的提示协议/规范化记法，不代表本仓库新增了运行时解析器。
- `<25%` 只替换 fast 作用域内 auto/all 的默认边际收益阈值；它不替换测试通过条件、数值容差或安全门槛。
- Markdown 是 analy/pure/report 的默认轻量载体，不是对用户明确要求的 PDF/LaTeX/幻灯片的静默替换。
- “3 倍”和“质量不低于 60%”必须区分实测、估计和未验证；没有对照数据时不得编造收益。
- fast 不自动修改其他技能正文；子技能通过当前任务上下文继承修饰属性，完成后按原技能的领域规则汇总。
