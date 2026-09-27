# 4150 2pt 最终输出级检查

本检查只验证参考成品的结构及 `contract → P+ → 反周期边界 → nopol`；
不把普通 light perambulator 当作独立 momentum-smeared perambulator；`momsmear0` 仅表示参考输出配置，不据此推断存在独立涂抹 perambulator。

| 根目录 | 文件数 | 动量组数 | projection pass | diff/unverified | 未解析 `.npy` |
|---|---:|---:|---:|---:|---:|
| momsmear-2x | 25 | 5 | 5 | 0 | 0 |
| momsmear-2y | 25 | 5 | 5 | 0 | 0 |
| momsmear-2z | 25 | 5 | 5 | 0 | 0 |
| momsmear2x | 25 | 5 | 5 | 0 | 0 |
| momsmear2z | 27 | 6 | 6 | 0 | 0 |
| momsmear0_Cg5 | 47 | 16 | 16 | 0 | 0 |
| momsmear0_Cg5g4 | 58 | 16 | 16 | 0 | 0 |

独立 momentum-smeared perambulator：**unverified**。
候选根目录状态：

| 路径 | exists | 类型 |
|---|---:|---|
| `/public/group/lqcd/donghx/Peram_code_2505` | False | - |
| `/public/group/lqcd/donghx/Peram_mpi` | False | - |
| `/public/group/lqcd/donghx/Peram_result` | False | - |
