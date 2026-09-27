# AGENTS.md — pyqcd

**PyQCD 主包**：格点 QCD 蒸馏管线 + 胶子 OPE + 梯度流重整化 TMD-PDF 计算库。
架构参考 /root/PyQCU（子包 + `_` 前缀私有模块 + 显式 re-export），
内容照抄自冻结蒸馏基线与 `refer/`（逻辑参考，不 import）。

## 核心目标

**计算使用梯度流重整化方案的核子中的胶子 TMD-PDF**：
裸矩阵元（蒸馏 2pt + 胶子 OPE staple 算符）→ Wilson flow 梯度流涂抹 →
混合方案/自重整化 Z_R → λ 外推 → 傅里叶 → NLO 匹配 → 连续极限外推。

## 子包

| 子包 | 内容 | 来源 |
|---|---|---|
| `lattice/` | 常数（Nc/fm2GeV）、DR 基 γ/σ 矩阵 | lib/constants,gamma,sigma |
| `tools/` | 后端切换（numpy/cupy）、缓存 einsum、切片、数据读取 | lib/backend,base,io_readers |
| `vertex/` | VdV/VVV 顶点、相位因子 | lib/vertex |
| `contraction/` | 自动 Wick、重子算符、seqperam、动态收缩 | lib/autowick,baroperator,seqperam,dynamic |
| `operator/` | Clover 场强 F、对偶 F̃、胶子 OPE 算符、.lime 读取、TMD staple 扩展 | compute_ope.py + 新写 |
| `analysis/` | Jackknife/Bootstrap/meff/ratio_3pt + disconnected(code_1)/meff/3pt 编排 + 色散拟合 | lib/analyse + analyze.py/zengch 逻辑 |
| `renorm/_tmdextract.py` | ★ 准 TMD-PDF/CS 核/SFTX 1 圈匹配 | 理论文档新写 |
| `smear/` | HYP 涂抹（Hasenbusch 2001，梯度流备选方案） | 理论文档对比项新写 |
| `analysis/_dispersion.py` | 色散关系拟合 E(Pz)=√(m²+k₂Pz²+k₃Pz⁴a²) | zengch fit_E0 逻辑 |
| `analysis/_ratio_fit.py` | c0 裸矩阵元提取（R 模型逐样本拟合） | zengch fit_ratio 逻辑 |
| `renorm/` | ★ 自重整化 Z_R、混合方案、NLO 匹配、外推、梯度流、TMD 提取 | refer/zengch 逻辑移植 + 理论文档新写 |
| `pipeline/` | 集中配置 + 9 步管线调度（+tmd 步） | config.py/run_pipeline.py |
| `testing/` | 原 `examples/` 的契约测试、回归、示例、基线与历史快照 | 迁移整理 |

## 关键约定

- 张量布局：gauge `(Nt,Nz,Ny,Nx,4,3,3)`；链接/场强 `(…,3,3)`；维序 t,z,y,x。
- 后端：`from pyqcd.tools import set_backend/get_backend`；numpy/cupy 通用；
  禁止直接 import cupy 计算（仅 try/except 探测）。
- 梯度流：`wilson_flow(U, tau, eps=0.01)`（RK3，Luescher 2010）；
  流时间物理约定 τ=3a²（NieMiera 2025）。
- 重整化：z 单位 fm（内部转 GeV⁻¹ 用 fm_to_GeV=0.197）；μ=2 GeV 默认。
- 日志：`print` + `verbose` 参数；管线产物写 logs/（gitignore 豁免）。
- 测试：`python -m pyqcd.testing`；一致性验证：
  `python -m pyqcd.testing.regression.consistency`。

## 反模式（勿重复）

- 生产代码不 import `refer/` 或 `pyqcd.testing`。
- 不做逐点 for 循环求逆/矩阵运算（批量 einsum）。
- 不改动 `refer/`；冻结基线位于
  `pyqcd/testing/regression/baselines/legacy_pipeline/`。
