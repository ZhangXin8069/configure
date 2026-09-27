"""GEVP 文档配套实测脚本。

对《格点QCD中的GEVP》文档中的四个论断给出可复现的数值证据：

  E1  解析谱模型下 GEVP 与直接对角化的收敛速度对比（教材 "correction term is
      typically smaller" 的定量化）。
  E2  N 个算符 / M 个态：N >= M 时 GEVP 本征值精确等于 e^{-E_n(t-t0)}。
  E3  PyQCD ``solve_gevp`` 的本征向量归一化是否保持 C(t0)-正交性。
  E4  ``meff(meff_type='GEVP')`` 的真实语义（对 GEVP 输出序列的 log 比）。
  E5  C(t0) 条件数对求解方式（Cholesky 化归 vs 直接求逆）的影响。

运行：python -m pyqcd.testing.regression.gevp.verify
"""
import numpy as np
from scipy.linalg import eigh, cholesky, solve

from pyqcd.analysis import solve_gevp, meff          # noqa: E402
from pyqcd.tools import set_backend                  # noqa: E402

set_backend('numpy')
FM2GEV = 0.1973269804     # ħc [GeV·fm]，与 pyqcd 约定一致
A_FM = 0.1                # 格距 0.1 fm


def model_correlator(E, Z, Nt):
    """由谱表示精确构造关联矩阵 C_ij(t) = sum_k Z_ik Z_jk e^{-E_k t}。"""
    t = np.arange(Nt)
    # (Nop, Nstate, Nt)
    return np.einsum('ik,jk,tk->ijt', Z, Z, np.exp(-np.outer(t, E)))


def eff_mass_from_lambda(lam, a=A_FM):
    """E_eff(t) = ln[lambda(t)/lambda(t+1)] / a（格点单位 -> GeV）。"""
    return np.log(lam[:-1] / lam[1:]) * (FM2GEV / a)


def banner(title):
    print('\n' + '=' * 72)
    print(title)
    print('=' * 72)


# ══════════════════════════════════════════════════════════════════════
# E1 / E2: 收敛速度对比
# ══════════════════════════════════════════════════════════════════════
banner('E1/E2  GEVP vs 直接对角化：解析谱模型的收敛行为')

M = 6                                   # 物理态数目
N = 3                                   # 算符基数目
E_true = np.array([0.30, 0.55, 0.90, 1.35, 1.80, 2.40])   # 格点单位
rng = np.random.default_rng(20260916)
Z = rng.normal(size=(N, M)) * 0.5 + np.array([[1.0, 0.4, 0.2, 0.1, 0.05, 0.02],
                                              [0.3, 1.0, 0.5, 0.2, 0.1, 0.05],
                                              [0.1, 0.3, 1.0, 0.4, 0.2, 0.1]])
Nt = 24
C = model_correlator(E_true, Z, Nt)

t0 = 1
lam_gevp, vecs = solve_gevp(C, t0)      # (N, Nt)，t >= t0 降序
lam_gevp = np.asarray(lam_gevp)

# 直接对角化 C(t)（不做 t0 归一化）
lam_diag = np.array([np.sort(np.linalg.eigvalsh(C[:, :, t]))[::-1]
                     for t in range(Nt)]).T          # (N, Nt)

print(f'模型: M={M} 个态 E={E_true}, N={N} 个算符, Nt={Nt}, t0={t0}')
print()
print('基态有效质量 E_0^eff(t) [GeV]（格距 a=0.1 fm）:')
print(f'{"t":>3} {"GEVP(t0=1)":>14} {"GEVP(t0=4)":>14} {"直接对角化":>14} {"真值":>10}')
lam_g4, _ = solve_gevp(C, 4)
lam_g4 = np.asarray(lam_g4)
E0_gev, E0_g4 = eff_mass_from_lambda(lam_gevp[0]), eff_mass_from_lambda(lam_g4[0])
E0_dir = eff_mass_from_lambda(lam_diag[0])
E0_true = E_true[0] * FM2GEV / A_FM
rows = []
for t in range(1, 12):
    rows.append((t, E0_gev[t], E0_g4[t], E0_dir[t]))
    print(f'{t:>3} {E0_gev[t]:>14.6f} {E0_g4[t]:>14.6f} {E0_dir[t]:>14.6f} {E0_true:>10.4f}')

dev_gev = np.abs(E0_gev[2:11] - E0_true)
dev_g4 = np.abs(E0_g4[2:11] - E0_true)
dev_dir = np.abs(E0_dir[2:11] - E0_true)
print()
print(f'  |E_0^eff - E_0| 平均(2<=t<=10, 9 个时间片):')
print(f'    GEVP(t0=1) = {dev_gev.mean():.4e}   GEVP(t0=4) = {dev_g4.mean():.4e}'
      f'   直接对角化 = {dev_dir.mean():.4e}')
print(f'    改善倍数: 直接/GEVP(t0=1) = {dev_dir.mean()/dev_gev.mean():.2f}x   '
      f'GEVP(t0=1)/GEVP(t0=4) = {dev_gev.mean()/dev_g4.mean():.2f}x')
print(f'  表格行 (t=2,3,4,5,8,10):')
for t in (2, 3, 4, 5, 8, 10):
    print(f'    t={t:>2}: GEVP1={E0_gev[t]:.6f}  GEVP4={E0_g4[t]:.6f}  '
          f'diag={E0_dir[t]:.6f}  true={E0_true:.6f}')

print()
print('激发态 E_1^eff(t) [GeV]:')
E1_gev = eff_mass_from_lambda(lam_gevp[1])
E1_dir = eff_mass_from_lambda(lam_diag[1])
E1_true = E_true[1] * FM2GEV / A_FM
print(f'{"t":>3} {"GEVP(t0=1)":>14} {"直接对角化":>14} {"真值":>10}')
for t in range(1, 10):
    print(f'{t:>3} {E1_gev[t]:>14.6f} {E1_dir[t]:>14.6f} {E1_true:>10.4f}')
print(f'  E_1 真值(精确) = {E1_true:.6f} GeV')
print('  相对误差 |E1_eff - E1_true|/E1_true [%]:')
print(f'  {"t":>3} {"GEVP":>10} {"直接对角化":>12}')
for t in (2, 3, 5, 9):
    print(f'{t:>3} {100*abs(E1_gev[t]-E1_true)/E1_true:>10.3f} '
          f'{100*abs(E1_dir[t]-E1_true)/E1_true:>12.3f}')

print()
print('--- E2: 截断态空间（M=N=3）时 GEVP 本征值的精确性 ---')
E3 = E_true[:3]
Z3 = Z[:, :3]
C3 = model_correlator(E3, Z3, Nt)
lam3, _ = solve_gevp(C3, t0)
lam3 = np.asarray(lam3)
for n in range(3):
    exact = np.exp(-E3[n] * (np.arange(Nt) - t0))
    with np.errstate(divide='ignore', invalid='ignore'):
        rel = np.abs(lam3[n] / exact - 1)
    print(f'  n={n}: max|lambda_n/e^(-E_n(t-t0)) - 1| = {np.nanmax(rel[1:]):.3e}  '
          f'(E_{n}={E3[n]})')

# ══════════════════════════════════════════════════════════════════════
# E3: C(t0)-正交性（B-正交）
# ══════════════════════════════════════════════════════════════════════
banner('E3  PyQCD solve_gevp 本征向量的 C(t0)-正交性检验')
V = np.asarray(vecs)                     # (N, N, Nt)
for t in (2, 5, 10):
    Vt = V[:, :, t]
    G = Vt.conj().T @ C[:, :, t0] @ Vt
    off = np.abs(G - np.diag(np.diag(G))).max()
    print(f'  t={t:>2}: max|V^dag C(t0) V - diag| = {off:.3e}   '
          f'diag = {np.round(np.diag(G).real, 6)}')
print('  参考: scipy.linalg.eigh(A,B) 原始返回应满足 V^dag B V = I')

# 对照：不额外做欧氏归一化时的 B-正交偏差
from scipy.linalg import eigh as _eigh
_, Vraw = _eigh(C[:, :, 5], C[:, :, t0])
Graw = Vraw.conj().T @ C[:, :, t0] @ Vraw
print(f'  对照(未做欧氏归一化): max|V^dag C(t0) V - I| = '
      f'{np.abs(Graw - np.eye(N)).max():.3e}')

# ══════════════════════════════════════════════════════════════════════
# E4: meff(meff_type='GEVP') 语义
# ══════════════════════════════════════════════════════════════════════
banner("E4  meff(meff_type='GEVP') 的真实语义")
samples = lam_gevp[None, :, :]           # (Nconf=1, N, Nt) —— 把本征值序列当"关联函数"
out = meff(samples, A_FM, Nconf_axes=0, Nt_axes=2, meff_type='GEVP')
out_log = meff(samples, A_FM, Nconf_axes=0, Nt_axes=2, meff_type='log')
manual = np.log(lam_gevp[:, :-1] / lam_gevp[:, 1:]) * (FM2GEV / A_FM)
print(f'  meff_type="GEVP" 与 "log" 输出是否逐位一致: '
      f'{np.allclose(out["data_mean"], out_log["data_mean"], rtol=0, atol=0)}')
print(f'  与手工 ln[lambda(t)/lambda(t+1)]/a 的最大偏差: '
      f'{np.abs(out["data_mean"][:, :-1] - manual).max():.3e}')
print(f'  末列（无 t+1 可比）填充值: {out["data_mean"][:, -1]}')
print('  结论: GEVP 分支 = 对 solve_gevp 输出的本征值序列做 log 型有效质量，'
      '不执行任何矩阵运算。')

# ══════════════════════════════════════════════════════════════════════
# E5: 条件数敏感性
# ══════════════════════════════════════════════════════════════════════
banner('E5  求解路径对比：Cholesky 化归 vs 直接求逆（对称性保持与精度）')
from scipy.linalg import solve_triangular as _stri      # noqa: E402

print(f'{"kappa(C(t0))":>13} {"路径":>16} {"max|dlam|":>12} {"max|Im lam|":>12}')
for tag, Zs in (('良条件', Z), ('近奇异基', np.vstack([Z[0], Z[0] + 1e-3 * Z[1], Z[2]]))):
    Cs = model_correlator(E_true, Zs, Nt)
    B = Cs[:, :, t0]
    kappa = np.linalg.cond(B)
    lam_ref = np.asarray(solve_gevp(Cs, t0)[0])[:, 8]
    # 路径 A：eigh(A, B)（PyQCD / scipy 广义本征问题）
    lam_ab = np.sort(eigh(Cs[:, :, 8], B)[0])[::-1]
    # 路径 B：Cholesky 化归 A = Q^{-1} C(t) Q^{-dag} -> 标准 Hermitian 问题
    Q = cholesky(B, lower=True)
    A1 = _stri(Q, _stri(Q, Cs[:, :, 8], lower=True).T, lower=True).T
    lam_chol = np.sort(np.linalg.eigvalsh((A1 + A1.T) / 2))[::-1]
    # 路径 C：直接求逆 C(t0)^{-1} C(t) -> 非 Hermitian 一般本征问题
    A2 = np.linalg.solve(B, Cs[:, :, 8])
    ev = np.linalg.eigvals(A2)
    lam_inv = np.sort(ev.real)[::-1]
    for name, lam, imax in (('eigh(A,B)', lam_ab, 0.0),
                            ('Cholesky 化归', lam_chol, 0.0),
                            ('直接求逆', lam_inv, np.abs(ev.imag).max())):
        print(f'{kappa:>13.3e} {name:>16} {np.abs(lam - lam_ref).max():>12.2e} '
              f'{imax:>12.2e}')

banner('E5b 带噪声时的对称性破坏（直接求逆路径的本征值虚部）')
for sigma in (0.0, 1e-5, 1e-3):
    Cn = C.copy()
    if sigma > 0:
        noise = rng.normal(size=C.shape) * sigma
        Cn = Cn + (noise + noise.transpose(1, 0, 2)) / 2
    B = Cn[:, :, t0]
    ev = np.linalg.eigvals(np.linalg.solve(B, Cn[:, :, 8]))
    lam_ab = np.sort(eigh(Cn[:, :, 8], B)[0])[::-1]
    print(f'  sigma={sigma:.0e}  max|Im lambda(直接求逆)| = {np.abs(ev.imag).max():.3e}'
          f'   max|lam_一般本征 - lam_eigh| = '
          f'{np.abs(np.sort(ev.real)[::-1] - lam_ab).max():.3e}')

banner('E6  t0 依赖：修正项振幅随 t0 的压低效应')
print('固定 t-t0 = 5，测量 lambda_0(t,t0)/exp(-E_0(t-t0)) - 1：')
print(f'{"t0":>4} {"lambda_0*exp(+E0 dt)":>22} {"delta":>12} {"delta/delta(t0=1)":>20}')
base = None
for t0_try in (1, 2, 3, 4, 6):
    lam, _ = solve_gevp(C, t0_try)
    lam = np.asarray(lam)
    t = t0_try + 5
    val = lam[0, t] * np.exp(E_true[0] * 5)
    delta = val - 1.0
    if base is None:
        base = delta
    print(f'{t0_try:>4} {val:>22.12f} {delta:>12.3e} {delta/base:>20.4f}')
cf = -np.polyfit(t0s_plot := np.array([1, 2, 3, 4, 6]),
                 np.log([abs(np.asarray(solve_gevp(C, x)[0])[0, x + 5]
                             * np.exp(E_true[0] * 5) - 1.0)
                         for x in (1, 2, 3, 4, 6)]), 1)[0]
print(f'  拟合压低率 c = {cf:.4f}，第一截断态能隙 E_N-E_0 = {E_true[3]-E_true[0]:.2f}')
print(f'  预期列 exp(-c*dt0) 用拟合 c: ' +
      ', '.join(f'{x}:{np.exp(-cf*(x-1)):.4f}' for x in (1, 2, 3, 4, 6)))
banner('E7  标度律检验：压低率是否由第一个被截断的态决定')
print('模型固定 N=3 个算符，改变第一个未表示态 E_3，测 delta(t0) 的指数压低率 c：')
print(f'{"E_3":>6} {"E_3-E_0":>9} {"拟合 c":>10} {"比值 c/(E_3-E_0)":>18}')
tt = np.array([2, 3, 4, 5, 6])
for E3_new in (1.05, 1.35, 1.80, 2.40, 3.00):
    E_mod = np.array([0.30, 0.55, 0.90, E3_new, 4.20, 5.60])
    Cm = model_correlator(E_mod, Z, Nt)
    deltas = []
    for t0_try in tt:
        lam, _ = solve_gevp(Cm, t0_try)
        lam = np.asarray(lam)
        deltas.append(abs(lam[0, t0_try + 5] * np.exp(E_mod[0] * 5) - 1.0))
    c = -np.polyfit(tt, np.log(deltas), 1)[0]
    gap = E3_new - E_mod[0]
    print(f'{E3_new:>6.2f} {gap:>9.2f} {c:>10.4f} {c/gap:>18.4f}')

print('\n完成。')
