# AGENTS.md — pyqcd/operator

Clover 场强 F、对偶 F̃、胶子 OPE 算符（`_gluon_ope.py`）、.lime 读取、TMD staple 扩展。
第三轮扩展：`gluon_ope_operator_z0` 增 mu2/nu2（F̃ 交叉 Lorentz 对）与
direction=±1（负 z Wilson 线，Operator.py operators_new_z0_mz_mu2）；
固定规范 FF 算符 `gluon_ff_operator_z0`（无 Wilson 线）；Lorentz 指派表
`get_ope_lorentz_pairs(zdir, mode)`（unpol/helicity/gauge_fix_unpol/
gauge_fix_helicity 四模式）。
