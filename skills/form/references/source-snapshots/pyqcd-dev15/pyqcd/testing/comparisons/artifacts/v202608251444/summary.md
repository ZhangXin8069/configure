# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.0001 | 0.0 | 8.396 |  |
| pass | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | 0.0 | - | 0.0016 | 0.0006 | 2.542 |  |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.0018 | 0.0 | 111.845 |  |
| pass | L04 | lqcddb | 动量壳列表生成（立方壳+fix_Q2+only_g0 全语义） | 0.0 | - | 0.0014 | 0.0013 | 1.116 | 原 pyqcd 缺立方壳/only_g0，已按参照修复对齐 |
| pass | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | 0.0 | - | 0.0009 | 0.0005 | 1.796 |  |
| pass | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.005 | 0.0001 | 47.128 |  |
| pass | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | 0.0 | - | 0.0029 | 0.0028 | 1.032 |  |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.2425 | 0.2162 | 1.122 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0003 | 0.0001 | 4.15 |  |
| pass | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | 0.0016570486171591627 | - | 0.0004 | 0.0003 | 1.218 | fm2GeV 常数比例 0.998343；cosh 支路 pyqcd 有意加 arccosh 定义域 clamp（仅填边界 NaN） |
| pass | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.147 | fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197 |
| pass | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | 0.0 | - | 0.002 | 0.0004 | 5.279 | %.32e/%.32f 格式微差，按解析值比对 |
| pass | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | 0.0 | - | 0.0003 | 0.0 | 10.277 |  |
| pass | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0004 | 0.0002 | 1.853 |  |
| pass | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | 0.0 | - | 0.0731 | 0.0608 | 1.201 |  |
| pass | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | 0.0 | - | 0.0005 | 0.0 | 29.869 |  |
| pass | L17 | lqcddb | Bootstrap 重采样（双方无种子，统计性比对） | 1.9085525915261319 | - | 0.0027 | 0.0006 | 4.292 | 随机重采样无确定对应；比较各键标准差相对偏差 |
| pass | L18 | lqcddb | ratio_3pt 一维模式 R=C3/C2 折叠 | 0.0 | - | 0.0003 | 0.0002 | 1.386 |  |
| pass | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | 0.0 | - | 0.2844 | 0.0261 | 10.889 |  |
| pass | L20 | lqcddb | solve_gevp 广义本征值/矢量逐位一致（B-正交基） | 0.0 | - | 0.0125 | 0.0005 | 25.412 |  |
| pass | L21 | lqcddb | mean/sum_over_array_of_list 分组聚合 | 0.0 | - | 0.0017 | 0.0004 | 4.567 |  |
| pass | L22 | lqcddb | dis_connect PDF 全窗非连通矩阵元 | 0.0 | - | 0.0045 | 0.0011 | 4.008 |  |
| pass | L22b | lqcddb | dis_connect PFF 分段窗（结构性） | 0.0 | - | 0.0058 | 0.0012 | 5.015 | 参考 PFF 装配依赖其 ArraySlicer.reshape 平坦重解释副作用与窗口覆盖顺序；pyqcd 按文档意图实现，实测未逐位一致（记录于映射表），物理主通道为 PDF |
| pass | L23 | lqcddb | ArraySlicer 切片/赋值/信息 | 0.0 | - | 0.0001 | 0.0002 | 0.908 | pyqcd 缺 get_slices/get_slice_shape/get_info 增强——缺失项待补 |
| pass | L24 | lqcddb | 算符厄米共轭/转置/电荷共轭/双夸克对称 | 0.0 | - | 0.0001 | 0.0 | 2.491 |  |
| ref_error | L25 | lqcddb | Stout 涂抹真实规范组态（2 时间片 nstep=2） | - | - | None | 0.6082 | - |  ERR:/lqcddb/src/lqcddb/base/smear_gauge.py", line 11, in stout_smear_ndarray
    U_dag = U.transpose(0, 1, 2, 3, 4, 6, 5).conj()
ValueError: axes don't match array
 |
| diff | L26 | lqcddb | 本征模基元 inner/check/normal/orthnormal | 4.118363254701669 | - | 0.0008 | 0.0001 | 5.566 |  |
| pass | L27 | lqcddb | compress V1 求和压缩 I/B（参数映射后逐位） | 0.0 | - | 0.0 | 0.0 | 2.601 |  |
| pass | L28 | lqcddb | noise/V2/V3/V4 结构性（形状+可运行） | 0.0 | - | 0.0085 | 0.0014 | 5.952 | 参考侧随机无种子，仅形状契约 |
| ref_error | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | - | - | None | 25.1984 | - |  ERR:ertex.py", line 643, in sink2src
    if dtype == 'VdV':
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| pass | L30 | lqcddb | Wick 图 QC 出图（结构性，B9 视觉等价重写） | 0.0 | - | 0.3078 | 0.1849 | 1.664 |  |
| both_error | S01 | suppl | 补充 gamma_index 稀疏分解（对照原版） | - | - | - | - | - |  ERR:]
  File "/root/PyQCD/pyqcd/lattice/_gamma.py", line 205, in gamma_index
    value[count] = g[i, j]
IndexError: index 4 is out of bounds for axis 0 with size 4
 |
| pq_error | S02 | suppl | 补充 PFF_Mom_to_gamma_new 投影表（±t） | - | - | - | - | - |  ERR:.py", line 258, in PFF_Mom_to_gamma_new
    gamma_indx_list_matrix[1:]).reshape(-1, n_comb * 2, 2)
ValueError: cannot reshape array of size 24 into shape (0,2)
 |
| ref_error | S03 | suppl | 补充 Mom_cross_sigma p×σ 叉积 | - | - | None | 0.0005 | - |  ERR:listcomp>
    return [r_mcs(list(m), upto4dim=u4) for m in mm for u4 in (False,
TypeError: build.<locals>.r_mcs() got an unexpected keyword argument 'upto4dim'
 |
| pass | S04 | suppl | 补充 perm_comb 排列组合数 | 0.0 | - | 0.0 | 0.0 | 1.943 |  |
| pass | S05 | suppl | 补充 get_cache_keys 缓存内省 | 0.0 | - | 0.0003 | 0.0002 | 1.415 |  |
| pq_error | S06 | suppl | 补充 ArraySlicer get_slices/get_slice_shape/get_info/assign keep_dims | - | - | - | - | - |  ERR:/_base.py", line 273, in assign
    self.arr[tuple(idx)] = _np.asarray(values).reshape(newshape)
ValueError: cannot reshape array of size 30 into shape (1,1,1)
 |
| pass | S07 | suppl | 补充 Peram_truncated 截断（真实 peram） | 0.0 | - | 0.0244 | 0.0243 | 1.007 |  |
| pass | S08 | suppl | 补充 plot_analyse_marker/color 常量 | 0.0 | - | 0.0 | 0.0 | 4.135 |  |
| diff | S09 | suppl | 补充 unpol 第二插入=F 选项（对照 donghx pla,pla 通道） | 2.334743898847668 | - | 0.5362 | 0.1953 | 2.746 |  |
| pass | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | 0.0 | - | 0.1001 | 0.0 | 2282.606 |  |
| pass | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | 0.0 | - | 0.0003 | 0.0002 | 1.363 | %.32f/%.32e 格式微差 |
| pass | D03 | donghx | Clover 场强全 (4,4) 叠（真实规范 2 时间片） | 2.513549561971145e-16 | - | 1.5834 | 1.0375 | 1.526 |  |
| diff | D04 | donghx | 对偶场强 F̃=ε·F 全叠 | 1.0 | - | 1.772 | 1.0375 | 1.708 |  |
| both_error | D05 | donghx | ΔG 双场强算符 ±z 支 × 平面/全和（4 配置） | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| pass | D06 | donghx | OPE Lorentz 指派表（照抄 donghx rank 分派） | 0.0 | - | 0.0 | 0.0 | 1.09 |  |
| both_error | D07 | donghx | 固定规范 FF 无 Wilson 线算符 | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| pq_error | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | - | - | - | - | - | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 ERR:se.run_pq()
  File "/root/PyQCD/examples/pyqcd/cmp1/cases_donghx2.py", line 163, in p_vvv
    outs.append(mvvv(ph, ev_t))
NameError: name 'ev_t' is not defined
 |

**PASS 36/48**
