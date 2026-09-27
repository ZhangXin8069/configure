# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| both_error | S10 | suppl | stout 对照模式 traceless=False 逐位复现参照 | - | - | - | - | - | 根因：ref 迹扣除作用于被丢弃临时数组；pyqcd 默认仍去迹 ERR:PyQCD/examples/pyqcd/cmp1/cases_suppl.py", line 213, in p_stout_tl
    v = _pst(slab, nstep=2, rho=0.12, traceless=False)
NameError: name 'slab' is not defined
 |
| pass | S11 | suppl | 补充 momsmear_phase 动量涂抹相位（对照 phase_calc） | 0.0 | - | 0.0318 | 0.0004 | 80.727 |  |
| pass | S12 | suppl | 补充 twopt_slice_boundary 边界符号翻转（pp/pm） | 0.0 | - | 0.0002 | 0.0002 | 1.039 |  |
| pass | S13 | suppl | 补充质子插值算符表（六变体，照抄 donghx 切换块） | 0.0 | - | 0.0001 | 0.0001 | 0.847 |  |

**PASS 3/4**
