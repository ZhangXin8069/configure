# refer/git-rep — 外部参考 Git 库

> These are excellent software toolkits for agents.

本目录以 Git submodule 引入外部参考库，固定到下列提交，仅作只读对照，不属于本仓库维护范围。
升级参考库时显式更新 submodule，并同步本表。

| 路径 | 来源 | 用途 | 固定版本 | 许可与致谢 |
|---|---|---|---|---|
| `academic-research-skills` | https://github.com/Imbad0202/academic-research-skills.git | Claude Code 学术研究技能套件，覆盖从研究到发表的全流程 | `v3.23.1-3-gcfd081d` (`cfd081d8`) | CC BY-NC 4.0；感谢 Imbad0202 / Cheng-I Wu |
| `scientific-agent-skills` | https://github.com/K-Dense-AI/scientific-agent-skills.git | 面向科学计算与科研数据工作的 agent 技能集合 | `v2.72.0-4-g593377bb` (`593377bb`) | MIT；感谢 K-Dense Inc. |
| `skills` | https://github.com/mattpocock/skills.git | 面向真实工程任务的 agent 技能集合 | `v1.3.1-47-g5beb35b` (`5beb35b`) | MIT；感谢 Matt Pocock |
| `oh-my-codex` | https://github.com/Yeachan-Heo/oh-my-codex.git | Codex 的提示词、工作流与运行时增强工具包（OMX） | `v0.21.4` (`304fb3b`) | MIT；感谢 Yeachan-Heo |

## 维护约定

- 初始化/更新：`git submodule update --init --recursive`。
- 本库对这些参考库的分析文档统一放在 `refer/git-rep/docs/`，不要写入子库工作树。
- 子库工作树只读；需要修改上游内容时在上游仓库完成。
- 新增参考库使用 `git submodule add <url> refer/git-rep/<upstream-name>`，并在上表登记
  path、URL、用途、固定提交、许可与致谢。
