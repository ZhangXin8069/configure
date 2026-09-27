# configure form 合规整改记录

## 目标

处理 `form-audit.sh` 报告的 10 个大小写混排脚本名和 3 个不合规 `docs/*.txt`，
保持命令语义、依赖清单内容和 Git 可追溯性。

## 整改映射

| 原路径 | 新路径 | 原因 |
|---|---|---|
| `bin/gzALLpush.sh` | `bin/gz-all-push.sh` | 代码文件名全小写，多词用 `-` |
| `bin/gzCONFIGUREpush.sh` | `bin/gz-configure-push.sh` | 仓库名小写并分段 |
| `bin/gzMyQCDpush.sh` | `bin/gz-myqcd-push.sh` | 仓库名小写并分段 |
| `bin/gzPYQCUpush.sh` | `bin/gz-pyqcu-push.sh` | 仓库名小写并分段 |
| `bin/gzPyQCDpush.sh` | `bin/gz-pyqcd-push.sh` | 仓库名小写并分段 |
| `bin/zgALLpull.sh` | `bin/zg-all-pull.sh` | 代码文件名全小写，多词用 `-` |
| `bin/zgCONFIGUREpull.sh` | `bin/zg-configure-pull.sh` | 仓库名小写并分段 |
| `bin/zgMyQCDpull.sh` | `bin/zg-myqcd-pull.sh` | 仓库名小写并分段 |
| `bin/zgPYQCUpull.sh` | `bin/zg-pyqcu-pull.sh` | 仓库名小写并分段 |
| `bin/zgPyQCDpull.sh` | `bin/zg-pyqcd-pull.sh` | 仓库名小写并分段 |
| `docs/apt_requirement.txt` | `lib/requirements/apt.txt` | 功能输入不属于 docs |
| `docs/pip_requirement.txt` | `lib/requirements/pip.txt` | 功能输入不属于 docs |
| `docs/hello.txt` | 删除，内联到 `bin/zhello.sh` | 单行输出不需要独立文档 |

## 同步改动

- `bin/gz-all-push.sh`、`bin/zg-all-pull.sh` 改用新的分段脚本名。
- `bin/apt_install.sh`、`bin/pip_install.sh` 改读 `lib/requirements/`。
- `bin/AGENTS.md`、`docs/AGENTS.md`、`lib/AGENTS.md` 和根 `AGENTS.md` 同步职责与命名。
- 新增 `lib/requirements/README.md`，说明清单格式和消费者。
- 旧文档内容均保留在 Git 历史中，可用 `git show HEAD:<path>` 查看。

## 验证

| 检查 | 命令或证据 | 结果 |
|---|---|---|
| shell 语法 | `bash -n bin/*.sh` | 通过 |
| 原名引用 | 排除固定快照后的仓库级 `rg` | 无旧引用 |
| 结构审计 | `form-audit.sh --strict --quiet` | 13 项候选中计划内项清零 |
| Git 差异 | `git diff --check` | 通过 |
| 目标存在性 | 10 个新脚本及 2 个 requirements 文件存在 | 通过 |

## 恢复

本次全部使用 Git rename；旧路径内容可由整改前提交中的原始路径恢复。提交后使用
`git show <commit>^:<path>` 查看，或用 `git restore --source=<commit>^ -- <path>` 恢复。
