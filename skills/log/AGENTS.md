# AGENTS.md — log 技能目录

本目录实现 `log` 技能：在主任务阶段成果、一般记录和任务完成三个门控点，将高价值日志、
全文报告及最终用户指令归档到 Git 根目录的 `logs/`，并维护 `logs/AGENT.md` 批次索引。
`SKILL.md` 是流程权威；`scripts/write-log.sh` 负责确定性写入，`scripts/write-log.test.sh` 覆盖
三态、冲突、时间格式、缺字段和 10 MiB 上限。默认使用紧凑时间戳和 KB 级内容。
有 Git 且本次产生文件改动时执行 `git diff --check` 与定向复查，不自动暂存、提交或推送。
