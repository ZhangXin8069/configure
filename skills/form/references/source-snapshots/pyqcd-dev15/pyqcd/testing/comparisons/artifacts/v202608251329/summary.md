# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| both_error | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | - | - | - | - | - |  ERR:, line 77, in <dictcomp>
    lambda: [{k: float(complex(v)) for k, v in d.items()}
TypeError: float() argument must be a string or a real number, not 'complex'
 |

**PASS 0/1**
