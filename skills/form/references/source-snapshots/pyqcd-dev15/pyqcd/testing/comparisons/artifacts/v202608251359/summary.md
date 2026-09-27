# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L20 | lqcddb | solve_gevp 广义本征值/矢量逐位一致（B-正交基） | 0.0 | - | 0.0027 | 0.0003 | 8.332 |  |
| ref_error | L22 | lqcddb | dis_connect 非连通矩阵元 PDF+PFF | - | - | None | 0.0006 | - |  ERR:/sush/lqcddb/src/lqcddb/base/base_functions.py", line 174, in slice
    return self.array[slices]
IndexError: index 12 is out of bounds for axis 4 with size 12
 |

**PASS 1/2**
