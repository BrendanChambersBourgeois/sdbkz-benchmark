"""Paper 2, synthesis figure: SD-BKZ DSD-rate phase map over the (n, q) plane.

One picture of the whole explored parameter plane: at each measured (n, q) cell
(β=20, fplll), the colour is the SD-BKZ DSD rate (two-part reference-free
criterion). The DvW21 fatigue curve q_fat(n) is overlaid; SD-BKZ cracking
switches on above it and the onset modulus climbs with n. A rate figure (not the
signed d(LN)), using the same criterion as the onset table, so it cannot disagree.

Grid is irregular -- some n carry a full q-ladder, others a single q=97
dimension-sweep point -- so it is drawn as a coloured scatter, not a raster; the
gaps are honest coverage, not interpolation. Reuses extract_dsd_onset's criterion.
No RNG.
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(_REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "scripts"))
from extract_dsd_onset import _cell_rate, _q_grid  # noqa: E402

BETA = 20
TREE = "ntru"
NS = [59, 61, 67, 71, 73, 79, 83, 89, 101, 113, 127]


def _q_fat(n):
    return 0.004 * np.power(n, 2.484)


def fig_ntru_phase_map(output_dir=".", fname="phase_map.png"):
    """SD-BKZ DSD-rate scatter-heat over (n, q) with the q_fat overlay."""
    pts_n, pts_q, pts_r = [], [], []
    for n in NS:
        for q in _q_grid(TREE, n, BETA):
            r = _cell_rate(TREE, n, BETA, q, "sdbkz")
            if r and r[1] > 0:
                pts_n.append(n)
                pts_q.append(q)
                pts_r.append(r[0] / r[1])
    if not pts_n:
        raise ValueError("no β=20 ntru cells found for the phase map")

    fig, ax = plt.subplots(figsize=(9, 5.6))
    sc = ax.scatter(pts_n, pts_q, c=pts_r, cmap="viridis", vmin=0, vmax=1,
                    s=70, edgecolors="#334155", linewidths=0.4, zorder=3)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("SD-BKZ DSD rate (two-part criterion)")

    n_line = np.linspace(min(NS) - 2, max(NS) + 2, 200)
    ax.plot(n_line, _q_fat(n_line), color="#64748b", ls="-.", lw=1.5,
            zorder=2, label=r"fatigue $q_\mathrm{fat}(n)=0.004\,n^{2.484}$ (DvW21)")
    ax.fill_between(n_line, _q_fat(n_line), max(pts_q) * 1.05,
                    color="#f1f5f9", zorder=0)
    ax.annotate("overstretched regime", xy=(min(NS) + 4, max(pts_q) * 0.9),
                fontsize=10, color="#64748b", style="italic")

    ax.set_yscale("log")
    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel("modulus $q$ (log scale)")
    ax.set_title(r"NTRU SD-BKZ DSD-rate phase map ($\beta=20$, fplll): cracking "
                 r"switches on above $q_\mathrm{fat}$, onset climbs with $n$")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=9)
    ax.grid(alpha=0.15, which="both", zorder=0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
