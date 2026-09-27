# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pq_error | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | - | - | - | - | - |  ERR:alysis/_analyse.py", line 583, in loop_tsrc
    values=slicer_in.slice(
ValueError: operands could not be broadcast together with shapes (6,4,1,1,8) (6,4,1,8) 
 |

**PASS 0/1**
