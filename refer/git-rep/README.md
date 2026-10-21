# refer/git-rep — 外部参考 Git 库

> These are excellent software toolkits for agents.

本目录以 Git submodule 引入外部参考库，固定到下列提交，仅作只读对照，不属于本仓库维护范围。
升级参考库时显式更新 submodule，并同步本表。

| 路径 | 来源 | 用途 | 固定版本 | 许可与致谢 |
|---|---|---|---|---|
| `academic-research-skills` | https://github.com/Imbad0202/academic-research-skills.git | Claude Code 学术研究技能套件，覆盖从研究到发表的全流程 | `v3.23.1-3-gcfd081d` (`cfd081d8`) | CC BY-NC 4.0；感谢 Imbad0202 / Cheng-I Wu |
| `scientific-agent-skills` | https://github.com/K-Dense-AI/scientific-agent-skills.git | 面向科学计算与科研数据工作的 agent 技能集合 | `v2.72.0-4-g593377bb` (`593377bb`) | MIT；感谢 K-Dense Inc. |
| `mattpocock-skills` | https://github.com/mattpocock/skills.git | 面向真实工程任务的 agent 技能集合 | `v1.3.1-47-g5beb35b` (`5beb35b`) | MIT；感谢 Matt Pocock |
| `oh-my-codex` | https://github.com/Yeachan-Heo/oh-my-codex.git | Codex 的提示词、工作流与运行时增强工具包（OMX） | `v0.21.4` (`304fb3b`) | MIT；感谢 Yeachan-Heo |
| `llm-skills` | https://github.com/Shubhamsaboo/awesome-llm-apps.git | LLM agent、MCP/生成式 UI 与工程辅助技能集合 | `main` (`874bc13a`) | Apache-2.0；感谢 Shubham Saboo |
| `andrej-karpathy-skills` | https://github.com/multica-ai/andrej-karpathy-skills.git | 面向 LLM 编码行为的简洁实现与可验证目标指南 | `main` (`2c606141`) | MIT；致谢相关作者与维护者 |
| `cuda-skills` | https://github.com/NVIDIA/skills.git | NVIDIA CUDA/HPC、NeMo、Jetson、TAO 与物理 AI 领域技能集合 | `main` (`c31020ee`) | Apache-2.0 / CC-BY-4.0；感谢 NVIDIA |
| `ecc-skills` | https://github.com/affaan-m/ECC.git | 跨 agent host、语言、工程与流程技能的聚合集合 | `v2.2.3-915-g90606c83` (`90606c83`) | MIT；感谢 Affaan Mustafa |

## 维护约定

- 初始化/更新：`git submodule update --init --recursive`。
- 本库对这些参考库的分析文档统一放在 `refer/git-rep/docs/`，不要写入子库工作树。
- 技能吸收记录见 `docs/skills-absorption-20261021.md`。
- 子库工作树只读；需要修改上游内容时在上游仓库完成。
- 新增参考库使用 `git submodule add <url> refer/git-rep/<upstream-name>`，并在上表登记
  path、URL、用途、固定提交、许可与致谢。
