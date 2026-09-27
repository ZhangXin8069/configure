# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L26 | lqcddb | 本征模基元 check/normal/orthnormal（check 按布尔） | 0.0 | - | 0.002 | 0.0003 | 5.905 | inner_product 语义分歧：ref 逐点 (Nc,Nc) 外积阵 vs pyqcd Nc 维内积，登记映射表 |
| pass | L27 | lqcddb | compress V1 求和压缩 I/B（参数映射后逐位） | 0.0 | - | 0.0 | 0.0 | 2.834 |  |
| pass | L28 | lqcddb | noise/V2/V3/V4 结构性（形状+可运行） | 0.0 | - | 0.0096 | 0.0022 | 4.296 | 参考侧随机无种子，仅形状契约 |
| diff | S10 | suppl | stout 对照模式 traceless=False（生产等价 7D 喂入，逐位一致） | inf | - | 0.3255 | 0.5297 | 0.614 | 根因链闭合：参照需 (dir,z,y,x,t,c,c) 生产形状喂入；单例 t 假轴会使 nu=0 staple 滚动失效 |

**PASS 3/4**
