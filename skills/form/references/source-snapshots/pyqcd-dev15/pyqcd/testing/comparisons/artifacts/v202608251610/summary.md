# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| ref_error | L25 | lqcddb | Stout 涂抹真实规范组态（幅值一致性；逐位差异见映射表） | - | - | None | 0.5631 | - | 量级/可运行性校验；逐位对照由 S10(traceless=False 复刻参照)覆盖；默认去迹路径的性质由 conftest(test_stout_smear)保证 ERR:/PyQCD/examples/pyqcd/cmp1/cases_lqcddb2.py", line 259, in r_stout
    slab.transpose(3, 0, 1, 2, 4, 5)[:, :, :, :, None, :]
ValueError: axes don't match array
 |

**PASS 0/1**
