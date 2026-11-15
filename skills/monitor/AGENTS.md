# AGENTS.md — monitor 技能

本目录实现 `monitor` 技能：任意外部目标（本地进程、后台命令、调度器作业、服务/HTTP、CI、数据产出、
远端命令）的只读观测；`SKILL.md` 是通用观测模型权威，不绑定某个调度器。
`references/adapters.md`（适配器契约与进程/调度器/服务/数据/CI 探针）、`djob.md`（djob 调度器适配器示例）、
`reading-output.md`（check due、`wait` 三态、offset 续读、不可信输出）、`patterns.md`（通用哨兵/单目标/
数据进度/换班）、`troubleshooting.md`（空结果、挂起、maxDuration、stderr、注入）按需读取。
`scripts/` 只提供 djob 适配器模板 `poll_jobs.sh`/`wait_all_jobs.sh`/`watch_job.sh`（不代为执行），
改后先 `bash -n`，再运行 `bash skills/monitor/scripts/monitor-scripts.test.sh` 做离线回归。
监控只读：不提交/不取消/不 `dkill`/不写数据树；没有明确授权不动别人的作业与性能基线作业。
有 Git 且本次产生文件改动时执行 `git diff --check` 与定向复查；不自动暂存、提交或推送。
