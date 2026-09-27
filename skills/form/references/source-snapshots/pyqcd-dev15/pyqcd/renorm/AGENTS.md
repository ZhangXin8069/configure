# AGENTS.md — pyqcd/renorm

★ 重整化核心链：自重整化 Z_R（`_zr.py`）、混合方案（`_hybrid.py`）、NLO 匹配（`_matching.py`）、连续极限外推（`_extrapolate.py`）、梯度流（`_gradient_flow.py`）、TMD 提取（`_tmd.py`/`_tmdextract.py`）。refer/zengch 逻辑移植 + 理论文档新写。
第三轮：修复 `_matching.C/C_gluon_ratio` 误植（matching_cc 三分区+5/6·Si 项）；
collinear 准 PDF sin 变换 `_tmdextract.quasi_pdf_gluon`；ZR 逐样本重拟合环
`_zr.fit_ZR_samples/summarize_ZR_samples`；协方差加权外推
`_extrapolate.fit_hR_PDF_extrap_boot`（Cholesky 白化+lstsq+逐样本带）。

dev8 对照轮（2026-08-24，对照 matching_new/fit_zr_new/fit_ratio）：修复耦合归一漏乘
4π 三处——`_matching.hR_PDF:81`、`_zr.Z_MS:31`、`_tmdextract.tmd_matching_hybrid:216`
（约定 `A_s ≡ α_s/(4π)`，用真耦合处须 ×4π，同 zengch 端 `alpha_s=A_s(mu)*4π`）；
`quasi_tmd_pdf` 逐列循环批量化为单次 GEMM（7.8–68x，逐位一致）。
求和规则断言改对称宽域 ±1.9（正半轴截断丢失 ξ<0 支路，+26% 不随 dx 收敛）。
