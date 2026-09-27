# AGENTS.md — pyqcd/smear

HYP 涂抹（Hasenbusch 2001）+ Stout 涂抹（Morningstar–Peardon 2004，
`_stout.py::stout_smear`，整合自 refer/sush lqcddb smear_gauge；空间三方向、
默认 nstep=20/ρ=0.12 对齐真实系综 stout_smear_20_0.12；无显式重投影——
约定输入为 SU(3) 组态）。与梯度流一致性有测试（test_hyp_vs_flow_consistent、
test_stout_smear：SU(3) 保持/平滑场作用量下降/平场不动/时间链不变）。
