# refer/git-rep skills 吸收记录（2026-10-21）

## 范围

- 用户指定范围：`refer/git-rep/**/skills`。
- 实际扫描 5 个 skills 根目录，覆盖 4 个固定 submodule。
- 技能文件总数：273；唯一名称：248；同名镜像/版本：25。
- 完整机器清单与逐 candidate 处置保存在本地忽略目录
  `data/runs/absorb/20261021-194557/`：
  `skills-inventory.json`、`skills-inventory.tsv`、`absorption-matrix.tsv`、`absorption-summary.json`。

## 来源与许可

| 来源 | 固定提交 | 许可 | 处置边界 |
|---|---|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills.git) | `5beb35b040e3de97e54fa9e386d7e42d15c295c2` | MIT | 可最小适配 |
| [oh-my-codex](https://github.com/Yeachan-Heo/oh-my-codex.git) | `304fb3b4825c4132c273732b14d2d5e86b54f8e3` | MIT | 仅适配不依赖 OMX 运行时的通用机制 |
| [scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills.git) | `593377bb048752abb0152deab9fbb1083a6087df` | MIT | 领域技能主要通过 `conf-refer-skill` 直调 |
| [academic-research-skills](https://github.com/Imbad0202/academic-research-skills.git) | `cfd081d8f309ec65254d9f9f04c845ee78b1ec1d` | CC BY-NC 4.0 | 仅 reference-only，不复制实现 |

## 处置汇总

- `adapt`: 12 个唯一技能映射到 8 个本地目标。
- `reference-only`: 243 个文件，保留在 submodule 供 `conf-refer-skill` 按需调用。
- `reject`: 18 个文件，主要是插件镜像、sunset stub、OMX 专有状态机或上游 `in-progress`/`deprecated` 内容。
- `keep`: 0；未把外部技能整树复制进本库运行路径。

## 已适配价值

| 外部能力 | 本地目标 | 吸收内容 |
|---|---|---|
| `writing-for-agents` | `skills/skill-creator/references/agent-doc-writing.md` | context pointer、两类负载、信息层级、完成判据、引导词与修剪 |
| `codebase-design` / `domain-modeling` / `to-tickets` | `skills/plan/references/tracer-tickets.md` | 纵向切片、真实阻塞边、expand-contract、领域词汇与深模块 |
| `code-review` / `ai-slop-cleaner` | `skills/review/references/review-matrix.md` | Standards/Spec 双轴、证据等级、fallback 与 AI 残留分类 |
| `deep-interview` | `skills/brainstorm/SKILL.md` | intent、non-goals、decision boundaries 与成功率清晰度门槛 |
| `best-practice-research` | `skills/research-notes/SKILL.md` | 官方/上游/标准优先和版本日期证据 |
| `ultraqa` | `skills/test/references/adversarial-qa.md` | 有界对抗式 E2E、场景矩阵、同失败停止与 cleanup |
| `uncertainty-and-units` / `scientific-critical-thinking` | `skills/phys-model/references/uncertainty-and-evidence.md` | 单位边界、不确定度预算、plausibility 与 claim evidence 三态 |
| `get-available-resources` | `tools/agent-resources.py` | 脱敏只读 host/affinity/cgroup/Slurm/GPU 资源快照 |

## 拒绝与保留理由

- 科学领域库技能（生物信息、药物设计、临床、量子框架、材料/化学工具等）专业性高，但本仓库是 shell/agent 配置库；
  复制会形成失主维护的领域镜像。保留为 reference-only，通过 `conf-refer-skill` 完整读取后原地执行。
- 学术论文流水线为 CC BY-NC 4.0，且本库已有 `get-paper`、`analy`、`pure`、`report`；不做再分发适配。
- OMX 的 goal、team、worker、HUD、notification、setup、cancel 等依赖其运行态和 CLI，不能直接移植到本库通用流程。
- `autoresearch-goal`、`pipeline`、`ralph`、`ultrawork` 是 sunset stub；上游 `in-progress`/`deprecated` 技能不作为稳定依赖。
- 插件目录中的同名技能是主技能镜像，不再重复适配。

## 验证要求

- `python3 tools/agent-resources.test.py`
- `python3 -m py_compile tools/agent-resources.py`
- `tools/configure-check.sh`
- `skills/form/scripts/form-audit.sh --root . --strict --quiet`
- `skills/form/scripts/form-snapshot-verify.sh --quiet`
- `git diff --check`

## 限制

- 本次吸收的是通用机制和边界原则，不保证外部领域技能中的工具、API、数据版本和模型可用。
- 需要领域技能时，仍由 `conf-refer-skill` 选择具体 submodule 路径、读取完整 SKILL.md 并按需读取附属资源。
