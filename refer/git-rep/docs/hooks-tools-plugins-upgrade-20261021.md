# hooks / tools / plugins 参考升级记录（2026-10-21）

## 目标

参考 `refer/git-rep/**` 中成熟的 hook/plugin manifest、静态校验和安装器实践，升级本库三处能力：

- hooks：有限超时、可枚举事件、plugin/hook 审计入口。
- tools：可复用的 plugin/hook/MCP 静态审计器。
- plugins：同步最新引用提交、增加 OMX 候选、安装前 manifest 审计。

## 参考来源

| 来源 | 固定提交 | 采纳内容 | 未采纳内容 |
|---|---|---|---|
| oh-my-codex | `304fb3b4825c4132c273732b14d2d5e86b54f8e3` | Codex hook event 结构、plugin manifest、MCP 开关、OMX 安装候选 | HUD、runtime state、apps 和复杂 Node bootstrap |
| ECC | `90606c8315ee09cafc303515c5f33024db6b9882` | hook schema、manifest 校验、命令/路径风险分类、插件安装候选更新 | 大规模 Node hooks、Chrome DevTools MCP、完整 workspace 运行时 |
| NVIDIA skills | `c31020eec34541c0f08d3e4a84eedefe1c002872` | 原生 Codex plugin manifest 与无 hooks 的安全基线 | 420 个 CUDA/Jetson/TAO 领域技能均保持 reference-only |

ECC 固定提交必须以 `.gitmodules` 当前值
`90606c8315ee09cafc303515c5f33024db6b9882` 为准；其 `.codex-plugin/plugin.json` SHA256 为
`09d1f838f55e4463aa9da6673f812edc33952572e3425eb77dee9ec31280d424`。

## 改动

### hooks

- `agent-hook.sh` 为每个事件设置覆盖目标执行和 JSON 事件写入的有限总超时；`--timeout` 与
  `AGENT_HOOK_TIMEOUT` 可覆盖。超时后终止受控进程组并返回 124。
- 普通事件成功返回时清理遗留后台子进程；`agent-resume` 保持唯一 detached 例外。清理阶段忽略重复
  `TERM`/`INT`，确保先 TERM 后 KILL 的升级不会被第二次信号打断。
- 新增 `plugin-audit` 事件，转发 `tools/plugin-audit.py`。
- 新增 `--list`，输出事件、默认超时和阻塞语义。

### tools

- 新增 `agent-resources.py` 的后续配套 `plugin-audit.py`：只读解析 plugin/hook/MCP manifest。
- 检查必需字段、相对路径逃逸、符号链接逃逸、hook event/schema、重复 id、命令路径穿越、命令风险、
  timeout、远程 hook、硬编码凭据与 MCP runtime。
- 严格拒绝重复 JSON 键、`NaN`/`Infinity` 和无效 UTF-8；发现目录/manifest 超限时 fail-closed，不再
  静默截断。终端与 JSON 输出均对已识别的凭据赋值脱敏，并转义控制字符。
- 默认 high/critical 失败，`--strict` 将 medium 也提升为失败；不执行插件代码。

### plugins

- ECC 内建参考从旧版 `76aaa77` 更新为 `90606c8315ee09cafc303515c5f33024db6b9882`。
- 新增 `omx` 社区候选，固定到 `304fb3b4825c4132c273732b14d2d5e86b54f8e3`，marketplace 为
  `oh-my-codex-local`。
- `orchestration` profile 升级为 `babysitter + omx`；`all` 同步包含 OMX。
- 新增 `--audit-manifest PATH`，委托 `tools/plugin-audit.py --strict`，审计失败时在任何 marketplace
  写入前停止。

## 安全边界

- 不复制 ECC/OMX 的 Node hook 实现，不自动信任任何外部 hook、MCP、apps 或插件二进制。
- plugin-audit 只做静态分析，不执行 manifest 中的 command、HTTP、prompt 或 MCP server。
- OMX/ECC 仍只作为显式安装候选，不进入默认 `recommended` profile。

## 验证

- `python3 -B tools/plugin-audit.test.py`（15 项）
- `bash hooks/hooks.test.sh`
- `bash plugins/install-recommended.test.sh`
- `bash -n hooks/*.sh hooks/pre-commit hooks/pre-push`
- `bash -n plugins/*.sh`
- `tools/configure-check.sh`
- `git diff --check`
