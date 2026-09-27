# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| diff | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | inf | - | 0.0004 | 0.0 | 25.665 |  |
| pass | L17 | lqcddb | Bootstrap 重采样（双方无种子，统计性比对） | 1.1384185333134695 | - | 0.0015 | 0.0002 | 7.141 | 随机重采样无确定对应；比较各键标准差相对偏差 |
| pass | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | 0.0 | - | 0.2171 | 0.0272 | 7.983 |  |
| diff | L20 | lqcddb | solve_gevp 广义本征值（PD 矩阵；向量按子空间 SVD 比） | 0.5187006253476079 | - | 0.0051 | 0.0025 | 2.037 |  |
| both_error | L22 | lqcddb | dis_connect 非连通矩阵元 PDF+PFF | - | - | - | - | - |  ERR:in dis_connect
    outb[tuple(sel)] = np.roll(bub, -t, axis=a_s)[tuple(sel)]
IndexError: too many indices for array: array is 4-dimensional, but 5 were indexed
 |

**PASS 2/5**
