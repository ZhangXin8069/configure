# AGENTS.md — monitor 技能

本目录实现 `monitor` 技能：长任务/后台进程/调度器作业/数据进度的只读观测，`SKILL.md` 是流程权威。
`references/scheduler.md`（djob/dsub/dkill、列与截断名、资源限制）、`reading-output.md`（check due、
`wait` 三态、offset 续读、不可信输出）、`patterns.md`（all-jobs 哨兵、single-job 转移、重复监控）、
`troubleshooting.md`（空 active、PENDING 卡住、maxDuration、stderr 污染）按需读取。
`scripts/` 只提供 `poll_jobs.sh`/`wait_all_jobs.sh`/`watch_job.sh` 模板（不代为执行），改后先 `bash -n`。
监控只读：不提交/不取消/不 `dkill`/不写数据树；没有明确授权不动别人的作业与性能基线作业。
有 Git 且本次产生文件改动时执行 `git diff --check` 与定向复查；不自动暂存、提交或推送。
