# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.001 | 0.0 | 71.613 |  |
| pq_error | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | - | - | - | - | - |  ERR:ice/_sigma.py", line 77, in Mom_times_sigma
    from .base_functions import cached_contract
ModuleNotFoundError: No module named 'pyqcd.lattice.base_functions'
 |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.002 | 0.0 | 120.144 |  |
| pq_error | L04 | lqcddb | 动量壳列表生成（共同语义） | - | - | - | - | - | pyqcd 缺 only_g0/多动量批量（部分差异） ERR:ot/PyQCD/pyqcd/tools/_base.py", line 332, in <genexpr>
    Q2 = sum(m**2 for m in Mom)
TypeError: unsupported operand type(s) for ** or pow(): 'list' and 'int'
 |
| both_error | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | - | - | - | - | - |  ERR:es/opt_einsum/contract.py", line 324, in contract_path
    raise ValueError(
ValueError: Size of label 'j' for operand 1 (6) does not match previous terms (8).
 |
| diff | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.0053 | 0.0001 | 45.445 |  |
| pq_error | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | - | - | - | - | - |  ERR:", line 532, in identify_equivalent_diagrams
    from .baroperator import GAMMA_PROPERTIES
ModuleNotFoundError: No module named 'pyqcd.contraction.baroperator'
 |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.2137 | 0.2193 | 0.974 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0003 | 0.0001 | 3.875 |  |
| both_error | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | - | - | - | - | - |  ERR:'),
  File "/root/PyQCD/pyqcd/analysis/_analyse.py", line 285, in meff
    data_sample = backend.abs(data_sample)
TypeError: bad operand type for abs(): 'dict'
 |
| diff | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.714 |  |
| both_error | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | - | - | - | - | - | %.32e/%.32f 格式微差，按解析值比对 ERR:_impl.py", line 1609, in savetxt
    raise AttributeError('fmt has wrong shape.  %s' % str(fmt))
AttributeError: fmt has wrong shape.  ['%i', '%.32e', '%.32e']
 |
| ref_error | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | - | - | None | 0.0001 | - |  ERR:ush/lqcddb/src/lqcddb/__init__.py", line 151, in __getattr__
    raise AttributeError(
AttributeError: module 'lqcddb' has no attribute 'check_files_existence'
 |
| diff | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0007 | 0.0003 | 2.184 |  |
| ref_error | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | - | - | None | 0.0998 | - |  ERR:refer/sush/lqcddb/src/lqcddb/__init__.py", line 151, in __getattr__
    raise AttributeError(
AttributeError: module 'lqcddb' has no attribute 'readin_eigvecs'
 |
| ref_error | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | - | - | None | 0.0 | - |  ERR:y._core.core._ndarray_base.__array__
TypeError: Implicit conversion to a NumPy array is not allowed. Please use `.get()` to construct a NumPy array explicitly.
 |
| both_error | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | - | - | - | - | - | %.32f/%.32e 格式微差 ERR:_impl.py", line 1609, in savetxt
    raise AttributeError('fmt has wrong shape.  %s' % str(fmt))
AttributeError: fmt has wrong shape.  ['%i', '%.32e', '%.32e']
 |

**PASS 4/17**
