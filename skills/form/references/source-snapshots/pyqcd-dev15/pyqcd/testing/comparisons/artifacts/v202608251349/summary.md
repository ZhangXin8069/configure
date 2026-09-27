# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | 0.0 | - | 0.0004 | 0.0 | 35.429 |  |
| diff | L20 | lqcddb | solve_gevp 广义本征值（PD 矩阵；向量按子空间 SVD 比） | 0.5187006253476079 | - | 0.0103 | 0.0003 | 32.507 |  |
| ref_error | L22 | lqcddb | dis_connect 非连通矩阵元 PDF+PFF | - | - | None | 0.0006 | - |  ERR:", line 194, in assign
    self.array[slices] = values.reshape(self.array[slices].shape)
ValueError: cannot reshape array of size 10368 into shape (6,4,3,1,12)
 |

**PASS 1/3**
