# 4150 effmass 聚合 2pt 检查

聚合脚本的组态序列为 `4050 + 50*k`，故 4150 对应样本索引 `k=2`。
raw 项比较 `(t_sink,t_source)` 矩阵；`twoptall` 项先按
`(t_sink-t_source) mod 72` 汇总，并对 complex64 输入升宽到 complex128。

| 聚合资产 | 形状 | 行数 | 4150 索引（命中/行数） | 状态 |
|---|---|---:|---:|---|
| `raw +2z momentum-smear` | `[5, 879, 72, 72]` | 5 | `2`（5/5） | **pass** |
| `raw -2z momentum-smear` | `[5, 879, 72, 72]` | 5 | `2`（5/5） | **pass** |
| `raw momentum-smear0 Cg5g4` | `[4, 878, 72, 72]` | 4 | `2`（4/4） | **pass** |
| `twoptall +2z momentum-smear` | `[5, 879, 72]` | 5 | `2`（5/5） | **pass** |
| `twoptall momentum-smear0 Cg5g4` | `[4, 878, 72]` | 4 | `2`（4/4） | **pass** |
| `twoptall Pz0 Cg5` | `[1, 879, 72]` | 1 | `2`（1/1） | **pass** |
| `twoptall Pz0 Cg5g4` | `[1, 876, 72]` | 1 | `2`（1/1） | **pass** |

汇总：7/7 个资产通过，
25 个动量行；所有通过行的最优匹配索引均为 2。
这证明了可见 4150 单组态文件与聚合 raw/时间汇总的对应关系；
不证明独立 momentum-smeared perambulator 或逐时间 VVV 文件已可见。
