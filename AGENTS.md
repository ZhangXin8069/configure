# AGENTS.md — configure 仓库总览

个人 shell/点文件配置仓库（ZhangXin）。为多台机器（工作站、笔记本、HPC 集群、容器、云端）提供版本化 shell 配置、工具脚本与环境引导。

## 入口与加载链

`env.sh` 被 **source**（不可直接执行），由 `.zshrc`/`.bashrc` 引入，负责：

1. source `tmp/scripts.sh`（自动生成的别名定义）
2. source `lib/_git_aliases.sh`（git 别名）
3. 将 `bin/` 与 `~/.local/bin` 前置到 `PATH`
4. 定义导航/grep 等 shell 别名

**别名生成**：`scripts/script_alias.sh` 扫描 `bin/` 与 `tmp/` 下所有 `.sh` 文件，生成 `alias <文件名>='bash <路径>'` 到 `tmp/scripts.sh`。**新增/删除 bin 或 tmp 下脚本后必须重新运行** `bash scripts/script_alias.sh`。

## 目录结构

| 路径 | 用途 |
|---|---|
| `env.sh` | 环境主入口（shell 启动时被 source） |
| `bin/` | 工具脚本，每个 `.sh` 自动生成别名 |
| `scripts/` | 维护/引导脚本（不自动别名） |
| `lib/` | 版本化环境配置与基础模板 |
| `lib/{name}-v{YYYYMMDD}/` | 带版本日期的环境配置 |
| `skills/` | agent 技能（init、tag、debug、optim、diff），`{~skill-name}` 触发 |
| `docs/` | 参考文档、包清单、图片素材 |
| `tmp/` | 运行时产物（别名脚本、日志），不入库 |

## 版本化配置约定（lib/{name}-v{YYYYMMDD}/）

- 更新配置时**新建**带当天日期的目录，不改旧目录（旧版保留作历史参考）
- `env.sh` 用 `@SECTION@`（单@，激活块）/ `@@SECTION@@`（双@，注释块）标记分节
- 安装命令首次运行后保留为注释，只留生效的 export，保证可复现

## 命令

- 无构建/lint/测试框架（纯 shell 脚本），校验脚本语法用 `bash -n <script>`
- 提交前无强制检查；仓库内 `.agent.*.log` 为 opencode 运行日志，不入库
