"""生成《格点QCD中的GEVP》文档配图（矢量 PDF）。"""
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from pyqcd.analysis import solve_gevp          # noqa: E402
from pyqcd.tools import set_backend            # noqa: E402

set_backend('numpy')
FM2GEV, A_FM = 0.1973269804, 0.1
ROOT = Path(__file__).resolve().parents[4]
OUT = str(ROOT / 'docs')

plt.rcParams.update({'font.size': 11, 'axes.labelsize': 12,
                     'axes.titlesize': 12, 'legend.fontsize': 9.5,
                     'xtick.labelsize': 10, 'ytick.labelsize': 10,
                     'figure.dpi': 120, 'savefig.bbox': 'tight'})

M, N, Nt = 6, 3, 24
E_true = np.array([0.30, 0.55, 0.90, 1.35, 1.80, 2.40])
rng = np.random.default_rng(20260916)
Z = rng.normal(size=(N, M)) * 0.5 + np.array([[1.0, 0.4, 0.2, 0.1, 0.05, 0.02],
                                              [0.3, 1.0, 0.5, 0.2, 0.1, 0.05],
                                              [0.1, 0.3, 1.0, 0.4, 0.2, 0.1]])


def model_correlator(E, Z, Nt):
    t = np.arange(Nt)
    return np.einsum('ik,jk,tk->ijt', Z, Z, np.exp(-np.outer(t, E)))


def eff(lam):
    return np.log(lam[:-1] / lam[1:]) * (FM2GEV / A_FM)


C = model_correlator(E_true, Z, Nt)
lam1 = np.asarray(solve_gevp(C, 1)[0])
lam4 = np.asarray(solve_gevp(C, 4)[0])
lam_d = np.array([np.sort(np.linalg.eigvalsh(C[:, :, t]))[::-1]
                  for t in range(Nt)]).T
E0_true = E_true[0] * FM2GEV / A_FM

# ── 图 1：收敛对比 ────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6.4, 4.0))
tt = np.arange(1, 14)
ax.plot(tt, eff(lam1[0])[tt], 'o-', ms=4, lw=1.4, label=r'GEVP, $t_0=1$')
ax.plot(tt, eff(lam4[0])[tt], 's-', ms=4, lw=1.4, label=r'GEVP, $t_0=4$')
ax.plot(tt, eff(lam_d[0])[tt], '^-', ms=4, lw=1.4,
        label='plain diagonalization')
ax.axhline(E0_true, color='k', ls='--', lw=1.2, label=r'true $E_0$')
ax.set_xlabel(r'$t$')
ax.set_ylabel(r'$E_0^{\rm eff}(t)$  [GeV]')
ax.set_ylim(0.58, 0.80)
ax.legend(frameon=False)
ax.grid(alpha=0.25)
fig.savefig(f'{OUT}/gevp_convergence.pdf')
plt.close(fig)

# ── 图 2：t0 压低与标度律 ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))

ax = axes[0]
t0s = np.array([1, 2, 3, 4, 6])
deltas = []
for t0_try in t0s:
    lam = np.asarray(solve_gevp(C, t0_try)[0])
    deltas.append(abs(lam[0, t0_try + 5] * np.exp(E_true[0] * 5) - 1.0))
ax.semilogy(t0s, deltas, 'o', ms=5, label=r'$|\delta_0|$ at $t-t_0=5$')
c = -np.polyfit(t0s, np.log(deltas), 1)[0]
ax.semilogy(t0s, np.exp(np.log(deltas[0]) - c * (t0s - t0s[0])), '--', lw=1.2,
            label=rf'fit: $e^{{-{c:.2f}\,t_0}}$')
ax.set_xlabel(r'$t_0$')
ax.set_ylabel(r'$|\lambda_0 e^{E_0(t-t_0)} - 1|$')
ax.legend(frameon=False)
ax.grid(alpha=0.25, which='both')

ax = axes[1]
gaps, rates = [], []
for E3_new in (1.05, 1.35, 1.80, 2.40, 3.00):
    E_mod = np.array([0.30, 0.55, 0.90, E3_new, 4.20, 5.60])
    Cm = model_correlator(E_mod, Z, Nt)
    dl = [abs(np.asarray(solve_gevp(Cm, t0)[0])[0, t0 + 5]
              * np.exp(E_mod[0] * 5) - 1.0) for t0 in t0s]
    rates.append(-np.polyfit(t0s, np.log(dl), 1)[0])
    gaps.append(E3_new - E_mod[0])
ax.plot(gaps, rates, 'o', ms=5, label='measured rate $c$')
xs = np.linspace(0.6, 2.8, 10)
ax.plot(xs, xs, 'k--', lw=1.2, label=r'$c = E_N - E_0$')
ax.set_xlabel(r'$E_N - E_0$  (first truncated state)')
ax.set_ylabel(r'fitted suppression rate $c$')
ax.legend(frameon=False)
ax.grid(alpha=0.25)
fig.savefig(f'{OUT}/gevp_t0_suppression.pdf')
plt.close(fig)

print('figures written to', OUT)
print('c =', round(c, 4), ' gaps/rates =',
      list(zip([round(g, 2) for g in gaps], [round(r, 3) for r in rates])))
