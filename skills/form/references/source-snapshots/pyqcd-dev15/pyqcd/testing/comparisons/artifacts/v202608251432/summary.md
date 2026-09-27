# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L23 | lqcddb | ArraySlicer 切片/赋值/信息 | 0.0 | - | 0.0002 | 0.0004 | 0.501 | pyqcd 缺 get_slices/get_slice_shape/get_info 增强——缺失项待补 |
| ref_error | L24 | lqcddb | 算符厄米共轭/转置/电荷共轭/双夸克对称 | - | - | None | 0.0 | - |  ERR:efer/sush/lqcddb/src/lqcddb/__init__.py", line 151, in __getattr__
    raise AttributeError(
AttributeError: module 'lqcddb' has no attribute 'transpose_gamma'
 |
| ref_error | L25 | lqcddb | Stout 涂抹真实规范组态（2 时间片 nstep=2） | - | - | None | 0.5318 | - |  ERR:/lqcddb/src/lqcddb/base/smear_gauge.py", line 11, in stout_smear_ndarray
    U_dag = U.transpose(0, 1, 2, 3, 4, 6, 5).conj()
ValueError: axes don't match array
 |
| diff | L26 | lqcddb | 本征模基元 inner/check/normal/orthnormal | 4.118363254701669 | - | 0.0016 | 0.0001 | 14.963 |  |
| pass | L27 | lqcddb | compress V1 求和压缩 I/B（参数映射后逐位） | 0.0 | - | 0.0 | 0.0 | 1.775 |  |
| pass | L28 | lqcddb | noise/V2/V3/V4 结构性（形状+可运行） | 0.0 | - | 0.0077 | 0.0012 | 6.491 | 参考侧随机无种子，仅形状契约 |
| both_error | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | - | - | - | - | - |  ERR:insum/contract.py", line 324, in contract_path
    raise ValueError(
ValueError: Size of label 'x' for operand 2 (41472) does not match previous terms (13824).
 |
| both_error | S01 | suppl | 补充 gamma_index 稀疏分解（对照原版） | - | - | - | - | - |  ERR:]
  File "/root/PyQCD/pyqcd/lattice/_gamma.py", line 205, in gamma_index
    value[count] = g[i, j]
IndexError: index 4 is out of bounds for axis 0 with size 4
 |
| both_error | S02 | suppl | 补充 PFF_Mom_to_gamma_new 投影表（±t） | - | - | - | - | - |  ERR:.py", line 258, in PFF_Mom_to_gamma_new
    gamma_indx_list_matrix[1:]).reshape(-1, n_comb * 2, 2)
ValueError: cannot reshape array of size 24 into shape (0,2)
 |
| both_error | S03 | suppl | 补充 Mom_cross_sigma p×σ 叉积 | - | - | - | - | - |  ERR:listcomp>
    return [p_mcs(list(m), upto4dim=u4) for m in mm for u4 in (False,
TypeError: build.<locals>.p_mcs() got an unexpected keyword argument 'upto4dim'
 |
| pq_error | S04 | suppl | 补充 perm_comb 排列组合数 | - | - | - | - | - |  ERR:d/cmp1/cases_suppl.py", line 90, in p_pc
    return [p_pc(10, 3, 'perm', False),
TypeError: build.<locals>.p_pc() takes 0 positional arguments but 4 were given
 |
| pass | S05 | suppl | 补充 get_cache_keys 缓存内省 | 0.0 | - | 0.0004 | 0.0003 | 1.591 |  |
| both_error | S06 | suppl | 补充 ArraySlicer get_slices/get_slice_shape/get_info/assign keep_dims | - | - | - | - | - |  ERR:/_base.py", line 273, in assign
    self.arr[tuple(idx)] = _np.asarray(values).reshape(newshape)
ValueError: cannot reshape array of size 30 into shape (1,1,1)
 |
| pq_error | S07 | suppl | 补充 Peram_truncated 截断（真实 peram） | - | - | - | - | - |  ERR:ples/pyqcd/cmp1/cases_suppl.py", line 152, in p_pt
    return p_pt(peram8.copy())
TypeError: build.<locals>.p_pt() takes 0 positional arguments but 1 was given
 |
| pass | S08 | suppl | 补充 plot_analyse_marker/color 常量 | 0.0 | - | 0.0 | 0.0 | 3.304 |  |
| diff | S09 | suppl | 补充 unpol 第二插入=F 选项（对照 donghx pla,pla 通道） | 2.334743898847668 | - | 0.5224 | 0.1989 | 2.626 |  |
| pq_error | D04 | donghx | 对偶场强 F̃=ε·F 全叠 | - | - | - | - | - |  ERR:core/shape_base.py", line 457, in stack
    raise ValueError('all input arrays must have the same shape')
ValueError: all input arrays must have the same shape
 |
| both_error | D05 | donghx | ΔG 双场强算符 ±z 支 × 平面/全和（4 配置） | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| diff | D06 | donghx | OPE Lorentz 指派表（照抄 donghx rank 分派） | inf | - | 0.0 | 0.0 | 0.683 |  |
| both_error | D07 | donghx | 固定规范 FF 无 Wilson 线算符 | - | - | - | - | - |  ERR:_dicts
    pr = pla_all_holder.get('ref') or _pla_ref()
ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
 |
| pq_error | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | - | - | - | - | - | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 ERR:se.run_pq()
  File "/root/PyQCD/examples/pyqcd/cmp1/cases_donghx2.py", line 157, in p_vvv
    outs.append(mvvv(ph, ev_t))
NameError: name 'ev_t' is not defined
 |

**PASS 5/21**
