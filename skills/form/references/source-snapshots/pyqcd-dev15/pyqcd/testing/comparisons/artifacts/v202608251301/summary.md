# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.0017 | 0.0 | 115.817 |  |
| pass | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | 0.0 | - | 0.004 | 0.0009 | 4.233 |  |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.0039 | 0.0 | 194.934 |  |
| pass | L04 | lqcddb | 动量壳列表生成（立方壳+fix_Q2+only_g0 全语义） | 0.0 | - | 0.0013 | 0.0012 | 1.137 | 原 pyqcd 缺立方壳/only_g0，已按参照修复对齐 |
| pass | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | 0.0 | - | 0.001 | 0.0005 | 2.258 |  |
| pass | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.0067 | 0.0001 | 48.291 |  |
| pass | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | 0.0 | - | 0.0058 | 0.0026 | 2.245 |  |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.2049 | 0.1739 | 1.178 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0002 | 0.0001 | 3.53 |  |
| diff | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | inf | - | 0.0004 | 0.0002 | 1.817 | fm2GeV 常数有意差异所致恒定比例 0.998343 |
| pass | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.72 | fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197 |
| pass | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | 0.0 | - | 0.0023 | 0.0003 | 6.54 | %.32e/%.32f 格式微差，按解析值比对 |
| pass | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | 0.0 | - | 0.0003 | 0.0 | 11.323 |  |
| pass | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0004 | 0.0002 | 1.904 |  |
| pass | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | 0.0 | - | 0.0968 | 0.0499 | 1.938 |  |
| pass | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | 0.0 | - | 0.1421 | 0.0 | 9712.249 |  |
| pass | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | 0.0 | - | 0.0003 | 0.0002 | 1.634 | %.32f/%.32e 格式微差 |

**PASS 16/17**
