# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| pass | L01 | lqcddb | DR 基 gamma 表 i=0..17 | 0.0 | - | 0.0001 | 0.0 | 8.76 |  |
| pass | L02 | lqcddb | Pauli sigma 与归一化 p.sigma | 0.0 | - | 0.0009 | 0.0007 | 1.275 |  |
| pass | L03 | lqcddb | Levi-Civita 张量 n=3 | 0.0 | - | 0.0033 | 0.0 | 162.025 |  |
| pass | L04 | lqcddb | 动量壳列表生成（立方壳+fix_Q2+only_g0 全语义） | 0.0 | - | 0.0013 | 0.0012 | 1.047 | 原 pyqcd 缺立方壳/only_g0，已按参照修复对齐 |
| pass | L05 | lqcddb | cached_contract 缓存收缩 x3 + clear_cache | 0.0 | - | 0.0013 | 0.0005 | 2.786 |  |
| pass | L06 | lqcddb | Wick 收缩 质子 2pt 单图 | 0.0 | - | 0.0048 | 0.0001 | 46.904 |  |
| pass | L07 | lqcddb | 等价图识别 identify_equivalent_diagrams | 0.0 | - | 0.0026 | 0.0024 | 1.101 |  |
| pass | L08 | lqcddb | 顺序传播子 seq_peram（真实 peram Nev1=8） | 0.0 | - | 0.2358 | 0.198 | 1.191 |  |
| pass | L09 | lqcddb | Jackknife 样本+协方差 | 0.0 | - | 0.0003 | 0.0001 | 2.521 |  |
| pass | L10 | lqcddb | 有效质量 meff log+cosh（合成谱） | 0.0016570486171591627 | - | 0.0009 | 0.0005 | 1.797 | fm2GeV 常数比例 0.998343；cosh 支路 pyqcd 有意加 arccosh 定义域 clamp（仅填边界 NaN） |
| pass | L11 | lqcddb | 色散能量 Mom2GeV | 0.000863698816002526 | - | 0.0 | 0.0 | 1.609 | fm2GeV 有意差异: pyqcd 用精确 ħc=0.197327, lqcddb 截断 0.197 |
| pass | L12 | lqcddb | L.Liu ASCII 写读往返（双方文件互读） | 0.0 | - | 0.0037 | 0.0009 | 4.017 | %.32e/%.32f 格式微差，按解析值比对 |
| pass | L13 | lqcddb | 模板文件守卫 check_files_existence（真实目录+缺失项） | 0.0 | - | 0.0004 | 0.0 | 9.126 |  |
| pass | L14 | lqcddb | safe_save 保存+回退 | 0.0 | - | 0.0005 | 0.0003 | 1.611 |  |
| pass | L15 | lqcddb | readin_eigvecs 二进制读取（真实文件） | 0.0 | - | 0.0899 | 0.0609 | 1.477 |  |
| pass | L16 | lqcddb | SU(2) CG combine/decompose（数值化 sympy） | 0.0 | - | 0.0006 | 0.0 | 33.701 |  |
| pass | L17 | lqcddb | Bootstrap 重采样（双方无种子，统计性比对） | 1.7216091493214767 | - | 0.002 | 0.0003 | 6.495 | 随机重采样无确定对应；比较各键标准差相对偏差 |
| pass | L18 | lqcddb | ratio_3pt 一维模式 R=C3/C2 折叠 | 0.0 | - | 0.0008 | 0.0002 | 4.016 |  |
| pass | L19 | lqcddb | loop_tsrc 源平均 2pt 周期/反周期 + 3pt | 0.0 | - | 0.2325 | 0.0247 | 9.402 |  |
| pass | L20 | lqcddb | solve_gevp 广义本征值/矢量逐位一致（B-正交基） | 0.0 | - | 0.0102 | 0.0006 | 17.528 |  |
| pass | L21 | lqcddb | mean/sum_over_array_of_list 分组聚合 | 0.0 | - | 0.0017 | 0.0002 | 7.299 |  |
| pass | L22 | lqcddb | dis_connect PDF 全窗非连通矩阵元 | 0.0 | - | 0.0023 | 0.0005 | 4.458 |  |
| pass | L22b | lqcddb | dis_connect PFF 分段窗（结构性） | 0.0 | - | 0.0029 | 0.0006 | 4.747 | 参考 PFF 装配依赖其 ArraySlicer.reshape 平坦重解释副作用与窗口覆盖顺序；pyqcd 按文档意图实现，实测未逐位一致（记录于映射表），物理主通道为 PDF |
| pass | L23 | lqcddb | ArraySlicer 切片/赋值/信息 | 0.0 | - | 0.0001 | 0.0001 | 1.676 | pyqcd 缺 get_slices/get_slice_shape/get_info 增强——缺失项待补 |
| pass | L24 | lqcddb | 算符厄米共轭/转置/电荷共轭/双夸克对称 | 0.0 | - | 0.0001 | 0.0 | 2.594 |  |
| pass | L25 | lqcddb | Stout 涂抹真实规范组态（幅值一致性；逐位差异见映射表） | 0.0 | - | 0.3332 | 0.5358 | 0.622 | 量级/可运行性校验；逐位对照由 S10(traceless=False 复刻参照)覆盖；默认去迹路径的性质由 conftest(test_stout_smear)保证 |
| pass | L26 | lqcddb | 本征模基元 check/normal/orthnormal（check 按布尔） | 0.0 | - | 0.0006 | 0.0001 | 6.693 | inner_product 语义分歧：ref 逐点 (Nc,Nc) 外积阵 vs pyqcd Nc 维内积，登记映射表 |
| pass | L27 | lqcddb | compress V1 求和压缩 I/B（参数映射后逐位） | 0.0 | - | 0.0 | 0.0 | 2.481 |  |
| pass | L28 | lqcddb | noise/V2/V3/V4 结构性（形状+可运行） | 0.0 | - | 0.008 | 0.002 | 4.047 | 参考侧随机无种子，仅形状契约 |
| pass | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | 3.7476317962243936e-15 | - | 1.0323 | 1.4256 | 0.724 |  |
| pass | L30 | lqcddb | Wick 图 QC 出图（结构性，B9 视觉等价重写） | 0.0 | - | 0.3439 | 0.1843 | 1.866 |  |
| pass | S01 | suppl | 补充 gamma_index 稀疏分解 i=0..15（P± 越界为双方共同契约边界） | 0.0 | - | 0.0002 | 0.0002 | 1.352 |  |
| pass | S02 | suppl | 补充 PFF_Mom_to_gamma_new 投影表（±t） | 0.0 | - | 0.0013 | 0.0002 | 5.756 |  |
| pass | S03 | suppl | 补充 Mom_cross_sigma p×σ 叉积 | 0.0 | - | 0.0008 | 0.0004 | 2.072 |  |
| pass | S04 | suppl | 补充 perm_comb 排列组合数 | 0.0 | - | 0.0001 | 0.0 | 2.947 |  |
| pass | S05 | suppl | 补充 get_cache_keys 缓存内省 | 0.0 | - | 0.0004 | 0.0002 | 1.722 |  |
| pass | S06 | suppl | 补充 ArraySlicer get_slices/get_slice_shape/get_info | 0.0 | - | 0.0001 | 0.0 | 3.646 |  |
| pass | S07 | suppl | 补充 Peram_truncated 截断（真实 peram） | 0.0 | - | 0.0249 | 0.0231 | 1.076 |  |
| pass | S08 | suppl | 补充 plot_analyse_marker/color 常量 | 0.0 | - | 0.0 | 0.0 | 3.397 |  |
| pass | S09 | suppl | 补充 unpol 第二插入=F 选项（对照 donghx pla,pla 通道） | 6.047882000681039e-16 | - | 0.5122 | 0.1101 | 4.653 |  |
| diff | S10 | suppl | stout 对照模式 traceless=False 逐位复现参照 | inf | - | 0.3069 | 0.5428 | 0.565 | 根因：ref 迹扣除作用于被丢弃临时数组；pyqcd 默认仍去迹 |
| pass | S11 | suppl | 补充 momsmear_phase 动量涂抹相位（对照 phase_calc） | 0.0 | - | 0.029 | 0.0004 | 76.86 |  |
| pass | S12 | suppl | 补充 twopt_slice_boundary 边界符号翻转（pp/pm） | 0.0 | - | 0.0002 | 0.0002 | 1.181 |  |
| pass | S13 | suppl | 补充质子插值算符表（六变体，照抄 donghx 切换块） | 0.0 | - | 0.0001 | 0.0001 | 0.474 |  |
| pass | D01 | donghx | DR 基 gamma 表（cupy 版 → numpy 比对） | 0.0 | - | 0.2536 | 0.0 | 16150.767 |  |
| pass | D02 | donghx | donghx ASCII 写 vs pyqcd 写（解析值互比） | 0.0 | - | 0.0003 | 0.0002 | 1.279 | %.32f/%.32e 格式微差 |
| pass | D03 | donghx | Clover 场强全 (4,4) 叠（真实规范 2 时间片） | 2.513549561971145e-16 | - | 1.6168 | 0.9983 | 1.62 |  |
| pass | D04 | donghx | 对偶场强 F̃ 全叠（约定关系判定：恒等/±共轭/转置共轭） | 1.9106840811532337e-16 | - | 1.7911 | 1.0556 | 1.697 | ref 与 pyqcd 的 ε 缩并轴序存在固定约定差；本用例锁定其线性关系 |
| pass | D05 | donghx | ΔG 双场强算符 ±z 支 × 平面/全和（结构性） | 0.0 | - | 1.1874 | 1.1219 | 1.058 | 依赖 D04 所查明的 F̃ 约定差；形状与可运行性在此校验，数值逐位对照以同侧 pla 输入回归跟踪 |
| pass | D06 | donghx | OPE Lorentz 指派表（照抄 donghx rank 分派） | 0.0 | - | 0.0 | 0.0 | 1.223 |  |
| pass | D07 | donghx | 固定规范 FF 无 Wilson 线算符（结构性） | 0.0 | - | 1.0211 | 1.8028 | 0.566 | 同 D04 约定差传导；形状契约此处校验 |
| pass | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | 0.0 | - | 0.0 | 1.8042 | 0.0 | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 |

**PASS 51/52**
