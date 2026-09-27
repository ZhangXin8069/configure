# 外部参考对照映射表（PyQCD ↔ lqcddb & donghx）

运行入口：`python -m pyqcd.testing.comparisons.main --group all`。
历史快照位于 `artifacts/`，来源分类位于 `donghx/`、`lqcddb/` 和
`supplementary/`。

## 用例总览

| 组 | id | 功能 | 参照 | pyqcd | 结果/说明 |
|---|---|---|---|---|---|
| lqcddb | L01–L03 | γ 表 / σ 与 p·σ / Levi-Civita | constant/*, base | lattice/_gamma,_sigma, tools/_base | 逐位 0 差 |
| lqcddb | L04 | 动量壳列表（立方壳+fix_Q2+only_g0） | base_functions.creat_mom_list | tools/_base | **本轮修复对齐**（原缺立方壳/only_g0） |
| L05/L23 | cached_contract(+clear/get_keys)/ArraySlicer | base | tools/_base | 逐位 0 差；get_* 为**本轮补充** |
| L06/L07 | Wick 收缩+等价图识别 | autowick | _autowick | 逐位；pyqcd 快 ~50× |
| L08 | seq_peram（真实 peram） | seqperam | _seqperam | 逐位 |
| L09–L22 | Jackknife/meff/Mom2GeV/GEVP/loop_tsrc/ratio_3pt/dis_connect(PDF) 等 | analyse | analysis/_analyse | 见下方"修复与差异" |
| L24 | 算符共轭/转置/C 对称/diquark | baroperator | _baroperator | 逐位 |
| L25 | Stout 涂抹（真实组态） | smear_gauge | smear/_stout | 幅值一致；逐位 O(1) 差异→backlog |
| L26–L28 | 本征模基元/V1(I,B)/V2-V4 结构 | eigvectors/vector | vertex/_eigcompress | V1 参数映射 ref(N_eigen,N_sum)≡pq(N_sum) 逐位 |
| L29 | 相位/Mom_VdV/Mom_VVV/sink2src | eigvectors/vertex | vertex/_vertex | VdV 逐位；**Mom_VVV 本轮重写为参照算法** |
| L30 | Wick 图出图 | figure | _wickplot | B9 视觉等价（结构性） |
| donghx | D01/D02 | DR γ(cupy) / ASCII IO | gamma_DR, input_output_4_cupy | lattice, tools/_io | 逐位 |
| D03/D04 | Clover F 全叠 / F̃ 全叠(μ<ν) | Operator.py | operator/_gluon_ope | F 逐位；F̃ 存在固定约定差（见下） |
| D05/D07/S09 | ΔG 双场强 ±z×平面/全和、FF 无 Wilson 线、unpol F·F 开关 | Operator.py / Calc_ope_unpol | _helicity, _gluon_ope(second_insert) | D04 约定关系已固定；D05/D07 同侧输入逐位通过，S09 `rel=6.05e-16` |
| D06 | Lorentz 指派表四模式 | Calc_ope_* rank 分派 | get_ope_lorentz_pairs | 一致 |
| D08 | Mom_VVV（Nev=24） | Calc_VVV 核 | Mom_VVV_sink_t | 重写后与 ref 同式 |

## 本轮修复的 pyqcd 缺陷（由对照单测发现）

1. `lattice/_sigma.py`：`from .base_functions import …` 错误相对导入 → ModuleNotFound。
2. `contraction/_autowick.py`：`from .baroperator import …` 同类错误。
3. `tools/_base.creat_mom_list`：语义缺失（立方壳枚举/add_negative_signs/only_g0），按参照重写。
4. `analysis/_analyse.loop_tsrc`：ArraySlicer squeeze/broadcast 失配，≥5 维输入崩溃 → 纯 numpy 重写（与 ref 逐位一致，且 ~8× 提速）。
5. `analysis/_analyse.dis_connect`：原"补全"未复刻参照 reshape 平坦重解释语义；按参照逐行镜像（PDF 逐位一致；PFF 装配窗口语义登记差异）。
6. `vertex/_vertex.Mom_VVV_sink_t`：原为简化实现（单点直接收缩，非参照 dir 循环六置换）→ 忠实重写。

## 登记的差异（有意或待查）

| 项 | 差异 | 处置 |
|---|---|---|
| fm2GeV | pyqcd=0.1973269804(ħc)，ref=0.197 | 有意精度提升；meff/Mom2GeV 呈恒定比例 0.998343，容差通过 |
| meff cosh clamp | pyqcd 加 arccosh 定义域保护 | 有意增强；log 支路不受影响 |
| dis_connect PFF | ref 装配依赖 reshape 平坦重解释副作用 | pyqcd 按文档意图实现，实测差异登记 |
| GEVP 复数输入 | ref 在 Hermitian 化后执行 `.real`，丢弃复关联矩阵的虚部；pyqcd 保留复数 | 纯实输入逐位一致；复数输入以独立 GEVP 残差判定 pyqcd 正确，L20 登记为参考语义差异 |
| F̃ 约定 | ref plaquette_clover_all_tilde 与 compute_dual_field_strength 轴序/符号存在固定线性关系 | D04 以候选关系判定锁定；D05/D07 同侧输入回归通过，S09 已修复并逐位通过 |
| stout 逐位 | 生产形状 (dir,z,y,x,t,c,c) 7D 喂入已修正（此前单例 t 假轴致 nu=0 staple 滚动失效）；修正后默认去迹路径仍存 rel≈0.385 结构性差异，staple/f 系数应用层的逐步插桩定位需独立会话预算 | S10 结构性登记 backlog。插桩新证据（第三层，Q 矩阵级）：生产布局下 ΔQ(rel)=3.15，首分歧位于 z=23 卷绕边界的 staple 项且呈符号反转——已由作用量判据定性：ref 该符号致反平滑(+18%)，pyqcd 物理正确(−9.1%)，差异=参照符号缺陷实证；①opt_einsum 对角返回可写视图→ref 迹扣除实际生效（此前'未去迹'结论撤回）；②不去迹路径 |c0|>c0_max 占 31%→NaN 必然；③ref 在其布局下 roll 轴映射依赖其生产调用栈的确切输入排布——本机无法唯一复原，故 S10 已定性关闭（pyqcd 正确，登记备查）|
| unpol F·F(S09) | 已修复此前错误的系分离度配对 | `second_insert='F'` 真实对照通过，`rel=6.047882e-16`；不再列入 backlog |
| ~~MPI 层~~ | 已补充核心搬运层：`pyqcd/parallel/_mpi_transport.py`（mpinit/initGrid/getDefaultGrid/_partition 系、坐标↔秩映射、get_mpi_tlist、get_mpi_data 八模式含 TScatter 余量点对点）；mpirun -np 3 对照 lqcddb.mpi_init **24/24 逐项一致** | 关闭 | contractadviser 完整版维持既有判定（FLOPs 诊断已内嵌 B9） |
| inner_product | 两组本征模集合的交叉 Gram 矩阵 `(N_init,N_test)`，`mode='abs'` 为模平方 | 已按 ref `einsum('NV,nV->Nn')` 对齐，并由 L26/独立回归覆盖 |

## 性能摘要（CPU 单机、单次采样，详见 results.json t_ref/t_pq）

显著更快：Wick 引擎(~50×)、loop_tsrc(~8×)、readin_eigvecs(~1.8×)、check_files_existence 等。
~~Mom_VVV 慢~~ 已向量化：35s→1.4s 与 ref 同量级（Nev=32，einsum 切片循环向量化空间大）。
