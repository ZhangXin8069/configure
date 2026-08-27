# AGENTS.md — hooks

Codex agent hook 适配层与独立 Git 质量门禁。`codex-hook.sh` 是统一入口，按事件转发到预检、路径保护、工作树验证或通知脚本；`pre-commit`/`pre-push` 是独立门禁，不依赖自动启用的 `core.hooksPath`。

## 事件与边界

- `session-start`：只读输出仓库根、分支、说明文件和技能目录。
- `before-edit`：只接受仓库内路径，拒绝仓库根、`.git/`、agent 会话日志和仓库外路径。
- `after-edit`/`stop`：检查工作树空白、Shell 语法和会话日志；`--paths` 可收窄验证范围。
- `notify`：优先使用 `notify-send`，不可用时回退到终端，通知失败不阻塞任务。

脚本只把输入当作数据处理，不 `source`、不 `eval`、不执行仓库代码；Shell 文件仅用 `bash -n` 或 `zsh -n` 校验。

## 验证

```bash
bash -n hooks/*.sh hooks/pre-commit hooks/pre-push
hooks/codex-hook.sh session-start
hooks/codex-hook.sh after-edit
```

必需依赖为 `bash`、`git`；路径规范化需要 `realpath`，通知 JSON 解析可选用 `python3`。
