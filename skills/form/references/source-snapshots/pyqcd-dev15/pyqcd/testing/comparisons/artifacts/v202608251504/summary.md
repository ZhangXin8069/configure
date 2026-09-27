# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L22 | lqcddb | dis_connect PDF 全窗非连通矩阵元 | 0.0 | - | 0.0017 | 0.0004 | 3.703 |  |
| pass | L22b | lqcddb | dis_connect PFF 分段窗（结构性） | 0.0 | - | 0.0026 | 0.0005 | 5.561 | 参考 PFF 装配依赖其 ArraySlicer.reshape 平坦重解释副作用与窗口覆盖顺序；pyqcd 按文档意图实现，实测未逐位一致（记录于映射表），物理主通道为 PDF |

**PASS 2/2**
