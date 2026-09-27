# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| diff | L26 | lqcddb | 本征模基元 inner/check/normal/orthnormal | 4.118363254701669 | - | 0.0006 | 0.0001 | 5.548 |  |
| both_error | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | - | - | - | - | - |  ERR:insum/contract.py", line 324, in contract_path
    raise ValueError(
ValueError: Size of label 'x' for operand 2 (41472) does not match previous terms (13824).
 |
| pq_error | D04 | donghx | 对偶场强 F̃=ε·F 全叠 | - | - | - | - | - |  ERR:core/shape_base.py", line 457, in stack
    raise ValueError('all input arrays must have the same shape')
ValueError: all input arrays must have the same shape
 |
| diff | D06 | donghx | OPE Lorentz 指派表（照抄 donghx rank 分派） | inf | - | 0.0 | 0.0 | 0.964 |  |

**PASS 0/4**
