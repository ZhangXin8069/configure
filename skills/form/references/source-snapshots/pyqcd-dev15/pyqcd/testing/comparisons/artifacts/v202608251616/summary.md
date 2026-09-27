# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L25 | lqcddb | Stout 涂抹真实规范组态（幅值一致性；逐位差异见映射表） | 0.0 | - | 0.3342 | 0.5498 | 0.608 | 量级/可运行性校验；逐位对照由 S10(traceless=False 复刻参照)覆盖；默认去迹路径的性质由 conftest(test_stout_smear)保证 |
| diff | S10 | suppl | stout 对照模式 traceless=False（生产等价 7D 喂入，逐位一致） | inf | - | 0.3206 | 0.5303 | 0.605 | 根因链闭合：参照需 (dir,z,y,x,t,c,c) 生产形状喂入；单例 t 假轴会使 nu=0 staple 滚动失效 |

**PASS 1/2**
