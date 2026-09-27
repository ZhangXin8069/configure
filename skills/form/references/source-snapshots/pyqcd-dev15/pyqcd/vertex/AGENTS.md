# AGENTS.md — pyqcd/vertex

VdV/VVV 顶点构造与相位因子（动量涂抹蒸馏用）；本征模压缩
（`_eigcompress.py`，整合 refer/sush lqcddb vector_creator：内积/正交检查/
归一化/Gram–Schmidt/create_noise + compress_matrix_V1 求和压缩（reshape 快速
路径）/V2 随机抽取/V3 正交投影/V4 Z_N 噪声，seed 可复现跨后端一致；
特征向量布局 (Nev,Nz,Ny,Nx,Nc)；`create_omega_accelerate` Ω 加速权重张量
（exact/块/noise 分区，dim=2/3，conserved/normal——对照 lqcddb 原版实跑
真值逐位一致；契约要求 N_eigen/N_sum/N_extract 三元组））。
