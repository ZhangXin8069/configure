# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.002 | 0.0 | 112.052 |  |
| pass | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | 0.0 | - | 0.0049 | 0.0008 | 6.357 |  |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.0034 | 0.0 | 230.185 |  |
| pass | L04 | lqcddb | 动量壳列表生成（立方壳+fix_Q2+only_g0 全语义） | 0.0 | - | 0.0013 | 0.0012 | 1.12 | 原 pyqcd 缺立方壳/only_g0，已按参照修复对齐 |
| pass | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | 0.0 | - | 0.001 | 0.0004 | 2.373 |  |
| pass | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.0071 | 0.0001 | 60.611 |  |
| pass | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | 0.0 | - | 0.0094 | 0.0051 | 1.818 |  |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.1871 | 0.1771 | 1.057 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0002 | 0.0001 | 3.574 |  |
| diff | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | inf | - | 0.0004 | 0.0003 | 1.363 |  |
| pass | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.814 | fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197 |
| both_error | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | - | - | - | - | - | %.32e/%.32f 格式微差，按解析值比对 ERR:_impl.py", line 1609, in savetxt
    raise AttributeError('fmt has wrong shape.  %s' % str(fmt))
AttributeError: fmt has wrong shape.  ['%i', '%.32e', '%.32e']
 |
| pass | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | 0.0 | - | 0.0004 | 0.0 | 9.573 |  |
| pass | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0004 | 0.0003 | 1.432 |  |
| pass | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | 0.0 | - | 0.0858 | 0.0467 | 1.838 |  |
| pass | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | 0.0 | - | 0.1574 | 0.0 | 9542.066 |  |
| both_error | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | - | - | - | - | - | %.32f/%.32e 格式微差 ERR:_impl.py", line 1609, in savetxt
    raise AttributeError('fmt has wrong shape.  %s' % str(fmt))
AttributeError: fmt has wrong shape.  ['%i', '%.32e', '%.32e']
 |

**PASS 14/17**
