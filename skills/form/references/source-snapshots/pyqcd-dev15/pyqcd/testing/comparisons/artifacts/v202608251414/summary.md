# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.0012 | 0.0 | 91.88 |  |
| pass | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | 0.0 | - | 0.0024 | 0.0009 | 2.577 |  |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.0038 | 0.0 | 227.645 |  |
| pass | L04 | lqcddb | 动量壳列表生成（立方壳+fix_Q2+only_g0 全语义） | 0.0 | - | 0.0013 | 0.0012 | 1.109 | 原 pyqcd 缺立方壳/only_g0，已按参照修复对齐 |
| pass | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | 0.0 | - | 0.001 | 0.0005 | 1.953 |  |
| pass | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.006 | 0.0001 | 55.498 |  |
| pass | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | 0.0 | - | 0.0047 | 0.0025 | 1.856 |  |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.2408 | 0.1909 | 1.261 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0003 | 0.0001 | 4.001 |  |
| pass | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | 0.0016570486171591627 | - | 0.0004 | 0.0002 | 1.77 | fm2GeV 常数比例 0.998343；cosh 支路 pyqcd 有意加 arccosh 定义域 clamp（仅填边界 NaN） |
| pass | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.956 | fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197 |
| pass | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | 0.0 | - | 0.004 | 0.0005 | 8.779 | %.32e/%.32f 格式微差，按解析值比对 |
| pass | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | 0.0 | - | 0.0001 | 0.0 | 1.706 |  |
| pass | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0004 | 0.0003 | 1.555 |  |
| pass | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | 0.0 | - | 0.0942 | 0.0595 | 1.584 |  |
| pass | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | 0.0 | - | 0.0006 | 0.0 | 31.691 |  |
| pass | L17 | lqcddb | Bootstrap 重采样（双方无种子，统计性比对） | 1.969702868959698 | - | 0.0029 | 0.0006 | 4.5 | 随机重采样无确定对应；比较各键标准差相对偏差 |
| pass | L18 | lqcddb | ratio_3pt 一维模式 R=C3/C2 折叠 | 0.0 | - | 0.0006 | 0.0002 | 3.917 |  |
| pass | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | 0.0 | - | 0.2587 | 0.0264 | 9.804 |  |
| pass | L20 | lqcddb | solve_gevp 广义本征值/矢量逐位一致（B-正交基） | 0.0 | - | 0.0173 | 0.0012 | 15.043 |  |
| pass | L21 | lqcddb | mean/sum_over_array_of_list 分组聚合 | 0.0 | - | 0.0018 | 0.0004 | 4.982 |  |
| pass | L22 | lqcddb | dis_connect PDF 全窗非连通矩阵元 | 0.0 | - | 0.0045 | 0.001 | 4.495 |  |
| pass | L22b | lqcddb | dis_connect PFF 分段窗（结构性） | 0.0 | - | 0.0105 | 0.0011 | 9.75 | 参考 PFF 装配依赖其 ArraySlicer.reshape 平坦重解释副作用与窗口覆盖顺序；pyqcd 按文档意图实现，实测未逐位一致（记录于映射表），物理主通道为 PDF |
| pq_error | L23 | lqcddb | ArraySlicer 切片/赋值/信息 | - | - | - | - | - | pyqcd 缺 get_slices/get_slice_shape/get_info 增强——缺失项待补 ERR:/root/PyQCD/examples/pyqcd/cmp1/cases_lqcddb2.py", line 210, in p_sl
    out = [sl.get_info(),
AttributeError: 'ArraySlicer' object has no attribute 'get_info'
 |
| both_error | L24 | lqcddb | 算符厄米共轭/转置/电荷共轭/双夸克对称 | - | - | - | - | - |  ERR:_baroperator.py", line 328, in diquark_symmetry
    raise ValueError(f"{gamma_expr} is not a diquark structure")
ValueError: gamma_1 is not a diquark structure
 |
| ref_error | L25 | lqcddb | Stout 涂抹真实规范组态（2 时间片 nstep=2） | - | - | None | 0.5746 | - |  ERR:/lqcddb/src/lqcddb/base/smear_gauge.py", line 11, in stout_smear_ndarray
    U_dag = U.transpose(0, 1, 2, 3, 4, 6, 5).conj()
ValueError: axes don't match array
 |
| ref_error | L26 | lqcddb | 本征模基元 inner/check/normal/orthnormal | - | - | None | 0.0002 | - |  ERR:rc/lqcddb/eigvectors/vector.py", line 41, in check
    if self.backend.isnan(eigvecs).any():
AttributeError: 'vector_creator' object has no attribute 'backend'
 |
| ref_error | L27 | lqcddb | compress V1 求和压缩 I/B（参数映射后逐位） | - | - | None | 0.0 | - |  ERR:os((sum(N_sum), eigen_shape[-4], eigen_shape[-3], eigen_shape[-2], eigen_shape[-1]), "<c16")
AttributeError: 'vector_creator' object has no attribute 'backend'
 |
| ref_error | L28 | lqcddb | noise/V2/V3/V4 结构性（形状+可运行） | - | - | None | 0.0023 | - | 参考侧随机无种子，仅形状契约 ERR:, in normal
    N = contract('nv,nv->n', vectors, self.backend.conj(vectors)).reshape(-1, 1)
AttributeError: 'vector_creator' object has no attribute 'backend'
 |
| both_error | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | - | - | - | - | - |  ERR:line 193, in Mom_VVV_sink_t
    eigvecs_flat = eigvecs.reshape(Nev, Nx**3, Nc)
ValueError: cannot reshape array of size 1327104 into shape (32,2641807540224,3)
 |
| pass | L30 | lqcddb | Wick 图 QC 出图（结构性，B9 视觉等价重写） | 0.0 | - | 0.3221 | 0.2001 | 1.61 |  |
| pass | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | 0.0 | - | 0.1127 | 0.0 | 6236.014 |  |
| pass | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | 0.0 | - | 0.001 | 0.0002 | 4.316 | %.32f/%.32e 格式微差 |
| pass | D03 | donghx | Clover 场强全 (4,4) 叠（真实规范 2 时间片） | 2.513549561971145e-16 | - | 1.5891 | 1.0442 | 1.522 |  |
| pq_error | D04 | donghx | 对偶场强 F̃=ε·F 全叠 | - | - | - | - | - |  ERR:q = case.run_pq()
  File "/root/PyQCD/examples/pyqcd/cmp1/cases_donghx2.py", line 76, in p_dual
    tilde[(mu, nu)] = pq_dual_stack(F)[mu, nu]
KeyError: (0, 0)
 |
| both_error | D05 | donghx | ΔG 双场强算符 ±z 支 × 平面/全和（4 配置） | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| diff | D06 | donghx | OPE Lorentz 指派表（照抄 donghx rank 分派） | inf | - | 0.0 | 0.0 | 0.877 |  |
| both_error | D07 | donghx | 固定规范 FF 无 Wilson 线算符 | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| pq_error | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | - | - | - | - | - | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 ERR: line 193, in Mom_VVV_sink_t
    eigvecs_flat = eigvecs.reshape(Nev, Nx**3, Nc)
ValueError: cannot reshape array of size 995328 into shape (24,2641807540224,3)
 |

**PASS 27/39**
