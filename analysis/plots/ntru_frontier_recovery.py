"""Paper 2, figure: frontier exact-key-recovery curves and cost (sec:frontier).

Recovery rate (secret_exact_match) against q / q_fat(n) for BKZ and SD-BKZ on
the 50-tour ladders of tab:frontier, plus recoveries per 100 core-hours on the
fplll beta=40 ladders. Ladders and cost come from the claims-ledger loaders
(scripts/_paper2_claims), so figure, table and ledger read the same seeds.
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(_REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "scripts"))
from _paper2_claims.derived_numeric import _cost_ratio  # noqa: E402
from _paper2_claims.frontier import _ladder, q_fat  # noqa: E402

# (engine, n, beta, panel title)
LADDERS = [
    ("fplll", 157, 40, r"$n=157$, $\beta=40$, fplll"),
    ("fplll", 163, 40, r"$n=163$, $\beta=40$, fplll"),
    ("fplll", 167, 40, r"$n=167$, $\beta=40$, fplll"),
    ("fplll", 173, 40, r"$n=173$, $\beta=40$, fplll"),
    ("g6k", 181, 50, r"$n=181$, $\beta=50$, G6K"),
]
# (n, seed_max) as in the ledger's cost records
COST = [(157, None), (163, 20), (167, None)]
TOURS = 50


def fig_ntru_frontier_recovery(output_dir=".", fname="frontier_recovery.png"):
    sd_c, bkz_c, zero_c = COLORS["sdbkz"], COLORS["bkz"], COLORS["zero"]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    axes = axes.ravel()

    for ax, (eng, n, beta, title) in zip(axes, LADDERS, strict=False):
        lad = _ladder(eng, n, beta, TOURS)
        x = [q / q_fat(n) for q, _ in lad]
        for i, c, mk, lbl in [(1, bkz_c, "s", "BKZ"), (0, sd_c, "o", "SD-BKZ")]:
            ax.plot(x, [np.mean([s[i] for s in v]) for _, v in lad], color=c,
                    marker=mk, markersize=4, linewidth=1.6, label=lbl, zorder=3)
        ax.axhline(0.5, color=zero_c, lw=1.0, ls="--", alpha=0.7, zorder=1)
        ax.set_title(title)
        ax.set_ylim(-0.04, 1.04)
        ax.set_xlabel(r"$q/q_\mathrm{fat}(n)$")
        ax.grid(alpha=0.15, zorder=0)
    axes[0].legend(loc="upper left", framealpha=0.9, fontsize=9)
    for i in (0, 3):
        axes[i].set_ylabel("exact key recovery rate")

    ax = axes[5]
    w = 0.38
    for k, (n, smax) in enumerate(COST):
        sd, bkz, ratio, lo, hi, _ = _cost_ratio(n, smax)
        ax.bar(k - w / 2, bkz, w, color=bkz_c, label="BKZ" if k == 0 else None)
        ax.bar(k + w / 2, sd, w, color=sd_c, label="SD-BKZ" if k == 0 else None)
        ax.text(k, max(sd, bkz) + 0.3, f"SD/BKZ {ratio:.2f}\n[{lo:.2f}, {hi:.2f}]",
                ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(len(COST)))
    ax.set_xticklabels([f"$n={n}$" for n, _ in COST])
    ax.set_ylabel("recoveries per 100 core-hours")
    ax.set_title(r"cost-normalised, $\beta=40$, fplll")
    ax.set_ylim(0, 14.5)
    ax.grid(alpha=0.15, axis="y", zorder=0)
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
