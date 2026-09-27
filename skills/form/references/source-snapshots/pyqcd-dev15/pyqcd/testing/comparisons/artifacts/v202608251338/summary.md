# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| diff | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | inf | - | 0.0004 | 0.0 | 36.385 |  |
| diff | L17 | lqcddb | Bootstrap 重采样（双方无种子，统计性比对） | 1.1678588131960814 | - | 0.0015 | 0.0002 | 6.895 | 随机重采样无确定对应；比较各键标准差相对偏差 |
| pq_error | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | - | - | - | - | - |  ERR:/tools/_base.py", line 259, in assign
    self.arr[tuple(idx)] = values
ValueError: could not broadcast input array from shape (6,4,1,1,8) into shape (6,4,1,8)
 |
| diff | L20 | lqcddb | solve_gevp 广义本征值（PD 矩阵；向量按 Gram 相位不变比） | 0.2864055233914784 | - | 0.0093 | 0.0003 | 30.425 |  |
| pass | L21 | lqcddb | mean/sum_over_array_of_list 分组聚合 | 0.0 | - | 0.0014 | 0.0001 | 9.248 |  |
| both_error | L22 | lqcddb | dis_connect 非连通矩阵元 PDF+PFF | - | - | - | - | - |  ERR:n
    self.arr[tuple(idx)] = values
ValueError: shape mismatch: value array of shape (6,4,1,12) could not be broadcast to indexing result of shape (6,4,3,1,12)
 |

**PASS 1/6**
