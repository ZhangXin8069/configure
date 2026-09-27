# 对照单测结果

| 状态 | id | 组 | 功能 | rel_diff | tol | t_ref(s) | t_pyqcd(s) | 加速比 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| diff | L25 | lqcddb | Stout 涂抹真实规范组态（2 时间片 nstep=2） | inf | - | 0.3187 | 0.5623 | 0.567 |  |
| diff | L26 | lqcddb | 本征模基元 inner/check/normal/orthnormal | inf | - | 0.0007 | 0.0001 | 5.18 |  |
| pass | L29 | lqcddb | 相位因子+Mom_VdV/Mom_VVV/sink2src（Nev=32 全格点） | 1.3560005192265755e-14 | - | 1.1373 | 25.1175 | 0.045 |  |
| pass | S01 | suppl | 补充 gamma_index 稀疏分解 i=0..15（P± 越界为双方共同契约边界） | 0.0 | - | 0.0008 | 0.0006 | 1.38 |  |
| pass | S02 | suppl | 补充 PFF_Mom_to_gamma_new 投影表（±t） | 0.0 | - | 0.0038 | 0.0004 | 10.889 |  |
| pass | S03 | suppl | 补充 Mom_cross_sigma p×σ 叉积 | 0.0 | - | 0.0016 | 0.0007 | 2.366 |  |
| pass | S06 | suppl | 补充 ArraySlicer get_slices/get_slice_shape/get_info | 0.0 | - | 0.0001 | 0.0 | 1.962 |  |
| diff | S09 | suppl | 补充 unpol 第二插入=F 选项（对照 donghx pla,pla 通道） | 2.334743898847668 | - | 0.5088 | 0.2018 | 2.521 |  |
| diff | D04 | donghx | 对偶场强 F̃=ε·F 全叠 | 1.0 | - | 1.6859 | 0.9765 | 1.726 |  |
| diff | D05 | donghx | ΔG 双场强算符 ±z 支 × 平面/全和（4 配置） | inf | - | 1.0945 | 1.0693 | 1.024 |  |
| diff | D07 | donghx | 固定规范 FF 无 Wilson 线算符 | inf | - | 1.1144 | 1.835 | 0.607 |  |
| pq_error | D08 | donghx | Mom_VVV 六置换 LC 收缩（Nev=24，Pz∈{0,1}） | - | - | - | - | - | 参考 VVV_Calc_cupy 为逐 t 驱动（含文件 IO），核心算子与 pyqcd Mom_VVV_sink_t 同式；数值对照由 L29 覆盖 ERR:se.run_pq()
  File "/root/PyQCD/examples/pyqcd/cmp1/cases_donghx2.py", line 165, in p_vvv
    outs.append(mvvv(ph, ev_t))
NameError: name 'ev_t' is not defined
 |

**PASS 5/12**
