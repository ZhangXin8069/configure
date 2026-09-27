# 4150 费米子 2pt 对照

输出目录: `examples/pyqcd/cmp1/v202608291625_fermion_pz2`

配置: `{"nx": 24, "nt": 72, "nev": 100, "momentum_pzyx": [2, 0, 0], "momentum_smear": 0, "variant": "Cg5g4", "t_sources": [0], "delta_t": [2, 2], "selected_pair_count": 1}`

| 对象 | 状态 | 指标 | 值 | 最大绝对差 | 参考文件 |
|---|---|---|---:|---:|---|
| contract | pass | selected_rel_l2 | 2.3147240545678726e-15 | 1.3010433128432032e-17 | /public/group/lqcd/donghx/2pt_Result/beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear0_Cg5g4/4150/twopt_slice_pp_Px0Py0Pz2_eginphase0_Cg5g4_contract_conf4150.npy |
| nopol_pp | pass | selected_rel_l2 | 8.258034704872868e-16 | 6.940799466385295e-18 | /public/group/lqcd/donghx/2pt_Result/beta6.20_mu-0.2770_ms-0.2400_L24x72/momsmear0_Cg5g4/4150/twopt_slice_pp_Px0Py0Pz2_eginphase0_Cg5g4_nopol_ss_conf4150.npy |
| vvv | unverified | - | - | - | - |

状态计数: `{"pass": 2, "unverified": 1}`
