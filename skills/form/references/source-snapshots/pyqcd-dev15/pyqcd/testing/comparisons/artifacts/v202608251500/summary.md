# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | 0.0 | - | 0.0 | 21.0253 | 0.0 | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 |

**PASS 1/1**
