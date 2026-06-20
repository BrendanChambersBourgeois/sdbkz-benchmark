"""Paper 2, figure: DSD-onset sigmoids — DSD rate vs q, faceted by n.

The measurement BEHIND the scalar onset points of the fatigue / cross-engine
figures. For each lattice parameter n, the two-part reference-free DSD criterion
is evaluated per seed across the whole q-ladder, giving a success-RATE curve
rate(q) for BKZ and for SD-BKZ. The onset modulus reported elsewhere is just the
q at which a curve crosses 50%; here the full S-curve is shown, so the
SD-before-BKZ gap is the visible horizontal left-shift of the green curve rather
than an asserted scalar.

This is a RATE figure (fraction of seeds meeting the DSD criterion) -- not the
signed d(LN) advantage -- so it is reported freely (the §7 signed-d(LN) scope
restriction does not apply to DSD rates).

Criterion is imported from the canonical extractor (scripts/extract_dsd_onset.py
`_cell_rate` / `_q_grid`) so the sigmoids and the onset tables can never disagree.
β=20, fplll (the Table tab:dsdgap trend family). No curated constants, no RNG.
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(_REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "scripts"))
from extract_dsd_onset import _cell_rate, _q_grid  # noqa: E402

NS = [67, 79, 89, 101, 113]   # the committed β=20 onset trend (tab:dsdgap)
BETA = 20
TREE = "ntru"                 # fplll enumeration oracle
ONSET_RATE = 0.5


def _curve(n, variant):
    """[(q, rate)] over the n-cell's q-ladder for one variant."""
    out = []
    for q in _q_grid(TREE, n, BETA):
        r = _cell_rate(TREE, n, BETA, q, variant)
        if r and r[1] > 0:
            out.append((q, r[0] / r[1]))
    return out


def fig_ntru_onset_sigmoids(output_dir=".", fname="onset_sigmoids.png"):
    """DSD-rate sigmoids vs q, BKZ vs SD-BKZ, faceted by n (β=20, fplll)."""
    sd_c, bkz_c, zero_c = COLORS["sdbkz"], COLORS["bkz"], COLORS["zero"]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    axes = axes.ravel()

    for ax, n in zip(axes, NS, strict=False):
        for variant, c, mk, lbl in [("bkz", bkz_c, "s", "BKZ"),
                                     ("sdbkz", sd_c, "o", "SD-BKZ")]:
            cur = _curve(n, variant)
            if not cur:
                continue
            qs = [q for q, _ in cur]
            rs = [r for _, r in cur]
            ax.plot(qs, rs, color=c, marker=mk, markersize=4, linewidth=1.6,
                    label=lbl, zorder=3)
        ax.axhline(ONSET_RATE, color=zero_c, lw=1.0, ls="--", alpha=0.7,
                   zorder=1)
        ax.set_title(f"$n={n}$")
        ax.set_ylim(-0.04, 1.04)
        ax.set_xlabel("modulus $q$")
        ax.grid(alpha=0.15, zorder=0)

    for ax in axes[len(NS):]:           # blank the unused 6th panel
        ax.axis("off")
    axes[0].legend(loc="center right", framealpha=0.9, fontsize=9)
    for i in (0, 3):
        axes[i].set_ylabel("DSD rate (two-part criterion)")
    fig.suptitle("NTRU DSD-onset sigmoids ($\\beta=20$, fplll): the SD-BKZ rate "
                 "crosses 50% at lower $q$ than BKZ", y=0.99)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
