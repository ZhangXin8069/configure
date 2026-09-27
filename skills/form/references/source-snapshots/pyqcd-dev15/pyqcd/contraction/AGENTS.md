# AGENTS.md — pyqcd/contraction

自动 Wick 收缩、重子算符、seqperam、动态收缩（蒸馏 2pt/3pt 核心）。批量 einsum，禁止逐点循环。
双宇称投影+反周期边界符号翻转 `_baroperator.parity_and_boundary`；Wick 缩并图
QC 可视化 `_wickplot.plot_figure_wick`（2pt/3pt/4pt+，复杂度自适应）；收缩路径
FLOPs 诊断 `_dynamic._analyze_contraction_path/_format_cost`
（run_wick_analysis 增 optimize/peram_registry/v_registry/gamma_registry 可选参，
传入 registry 时逐图输出朴素/优化 FLOPs+加速比+最大中间张量）。
