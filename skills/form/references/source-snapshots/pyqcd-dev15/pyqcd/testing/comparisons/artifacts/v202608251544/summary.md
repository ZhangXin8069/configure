# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| diff | S10 | suppl | stout 对照模式 traceless=False 逐位复现参照 | inf | - | 0.3094 | 0.546 | 0.567 | 根因：ref 迹扣除作用于被丢弃临时数组；pyqcd 默认仍去迹 |

**PASS 0/1**
