# 对抗式动态 QA

仅在可运行行为确实需要端到端质量验证时启用；这是 `test` 的增强分支，不替代单元测试和正常回归。

## 1. 场景矩阵

执行前记录：

`scenario_id | intent | user/attacker model | setup | command/harness | expected signal | actual | cleanup`

至少覆盖适用的失败类别：

- malformed input：坏 JSON、缺字段、非法 flag、超长字符串、异常 Unicode、路径穿越形态；
- repeated interruption：重复 continue、stop/cancel、部分输出和重试；
- prompt injection：试图绕过指令、读取秘密、跳过验证或伪造成功；
- cancel/resume 与 stale state：旧 session、错误 run、矛盾状态、缺失时间戳；
- dirty worktree：已有改动和未跟踪文件保持不变；
- hung command：硬超时、终止子进程、恢复说明；
- flaky test：有上限复跑、失败聚类、不把偶然单次绿灯当通过；
- misleading success：成功文本但非零退出、隐藏失败、跳过项或截断日志。

## 2. 有界循环

最多 5 轮：

1. 写目标、安全边界、停止条件和场景矩阵；
2. 跑项目基线验证；
3. 跑可安全执行的对抗式场景，保存退出码、输出和清理结果；
4. 失败先定位根因并最小修复，再重跑基线、原场景和回归；
5. 清理临时 harness、fixture、日志、进程和失败产物。

同一失败重复 3 次即停止并报告根因证据；不通过无限重试换取偶然通过。场景无法安全执行时标记 `blocked`，
使用安全替代或报告边界，不执行破坏性命令、凭据读取或生产写入。

## 3. 完成判据

只有以下全部成立才声明对抗式 QA 完成：

- 正常基线通过；
- 适用场景矩阵全部有结果；
- 每个修复有回归证据；
- 无残留进程、临时文件或状态污染；
- 工作树中与本任务无关的改动仍保持不变。

报告至少包含目标、矩阵、命令、失败、修复、清理、残余风险和证据路径。

## 来源

适配自 `oh-my-codex` 的 `ultraqa`，固定提交
`304fb3b4825c4132c273732b14d2d5e86b54f8e3`，MIT License。本文件删除了 OMX 专有状态命令，
仅保留可移植 QA 原则。
