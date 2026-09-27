# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L25 | lqcddb | Stout 涂抹真实规范组态（幅值一致性；逐位差异见映射表） | 0.0 | - | 0.331 | 0.5521 | 0.599 | 量级/可运行性校验；逐位对照由 S10(traceless=False 复刻参照)覆盖；默认去迹路径的性质由 conftest(test_stout_smear)保证 |

**PASS 1/1**
