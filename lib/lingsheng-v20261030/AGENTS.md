# AGENTS.md — lingsheng-v20261030

灵晟 HPC 环境配置 v2026-10-30。目录包含环境入口 `env.sh` 和指向共享
`../../bin/ddub.sh` 的 DSUB 提交包装器。

- `env.sh`：加载 HPCKit 25.2.1、`anaconda3/2023.3`、`cmake/2026.1.RC1`，按需接入
  PyQCU，加载 conda base，并把 Slurm 查询/提交命令映射到 `dinfo`、`dnode`、
  `djob`、`dsub`、`dkill`。
- `ddub.sh`：符号链接到 `../../bin/ddub.sh`，用于生成 `.ddub.sh` 并调用 `dsub -s`。
- 配置包含集群固定路径、账号和队列名；跨集群复用前先逐项核对，不要直接覆盖现有环境。
