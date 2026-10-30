# Slurm 作业配置操作

## 适用范围

本仓库提供多种 Slurm 辅助入口：

| 来源 | 用途 |
|---|---|
| `bin/ddub.sh` | 生成 DSUB `.ddub.sh` 并立即 `dsub -s` |
| `bin/ssub.sh` | 生成 `.ssub.sh` 并立即 `sbatch` |
| `bin/ssrun.sh` | 用固定参数执行交互式 `srun` |
| `bin/ssqueue.sh`、`bin/zsqueue.sh` | 持续查看队列 |
| `bin/sstop.sh` | 取消指定用户全部作业 |
| `lib/dcu-v20260227/` 等版本目录 | 集群特定 `salloc`、`sbatch`、NUMA/网卡绑定模板 |

## 通用前置检查

```bash
command -v sinfo sbatch squeue scancel srun
sinfo -s
squeue -u "$USER"
```

不同集群的分区名、GPU/DCU 资源名、账号和 module 名称不同。不要直接复用其他集群的模板。

## `ddub.sh`

```bash
cd /path/to/workdir
ddub.sh python solve.py --input data.txt
```

脚本会在当前目录覆盖写入 `.ddub.sh`，默认使用 `q_hpcapp` 分区，并声明
`-rpn 16`、`-N 16`、`-R "cpu=37;mem=8G"` 和 600 分钟时限。命令参数按原始文本拼接，
需要保留 `$VAR` 或空格的参数应由调用方提供相应引号文本。生成后的命令追加
`>log.txt 2>&1` 并交给 `dsub -s`。

## `ssub.sh`

```bash
cd /path/to/workdir
ssub.sh bash my_job.sh --input data.txt
```

脚本会在当前目录覆盖写入 `.ssub.sh`，默认包含：

```text
job-name=ssub
partition=gpu-debug
nodes=1
ntasks=1
time=00-00:30:00
output=ssub.out
error=ssub.err
mail-user=zhangxin8069@qq.com
gres=gpu:1
source "$HOME/env.sh"
```

四个注意点：

1. `.ssub.sh` 每次覆盖，不复用上一次的自定义修改。
2. 参数通过 `printf %s` 按原始文本写入，适合简单命令和参数，不替代完整作业脚本；
   当前实现还会向 `.ddub.sh` 追加 `>log.txt 2>&1`，提交前应确认该文件是否属于预期工作流。
3. 默认 GPU、分区、邮箱和 `$HOME/env.sh` 都是个人环境假设。
4. 脚本没有预览模式；执行命令本身就意味着提交作业。需要预览时，先根据模板手工创建等效脚本并检查，再决定是否提交。

## `ssrun.sh`

```bash
ssrun.sh
ssrun.sh bash my_command.sh
```

固定参数包括：

```text
job-name=ssrun
partition=gpu-debug
ntasks=2
gpus=2
time=00-00:30:00
output=ssrun.out
error=ssrun.err
mail-user=zhangxin8069@qq.com
mail-type=ALL
```

脚本先 source `$HOME/env.sh`。在不同集群使用前应复制为作业专用脚本并逐项修改，不建议直接覆盖原脚本。

## 队列查看

```bash
ssqueue.sh
zsqueue.sh
```

两者都启动 `watch`。非交互终端或自动化环境中改用单次命令：

```bash
squeue -u "$USER"
squeue -p gpu-debug
```

## 取消作业

```bash
sstop.sh
```

`sstop.sh` 实际执行 `scancel --user zhangxin`，会取消该用户的所有 Slurm 作业，不只当前目录或当前项目。自动化环境优先使用精确作业号：

```bash
scancel <job-id>
scancel --user "$USER" <job-id>
```

## DCU 模板

版本化示例：

```text
lib/dcu-v20260205/_salloc.newlarge.sh
lib/dcu-v20260205/_sbatch.newlarge.sh
lib/dcu-v20260227/salloc.sh
lib/dcu-v20260227/openmpi_bind_mlnx.sh
```

`dcu-v20260227/salloc.sh` 申请 `hpctest` 分区的 1 节点、128 核、8 张 DCU。`stop.sh` 取消硬编码用户全部作业。使用前应检查：

```bash
grep -nE 'partition|time|gres|ntasks|user|account|source' lib/dcu-v20260227/*.sh
```

`openmpi_bind_mlnx.sh` 根据 `OMPI_COMM_WORLD_LOCAL_RANK` 绑定 NUMA 节点和 `UCX_NET_DEVICES`。它依赖该机器的 8 卡拓扑和 Mellanox 设备命名，不能假定适用于其他节点。

## 安全使用流程

```bash
cp lib/dcu-v20260227/salloc.sh ./salloc.local.sh
${EDITOR:-vim} ./salloc.local.sh
bash -n ./salloc.local.sh
./salloc.local.sh
```

本仓库不自动提交、执行或取消任何 Slurm 作业。每次提交前确认目标用户、分区、时限、GPU/DCU 数量和输出文件路径。
