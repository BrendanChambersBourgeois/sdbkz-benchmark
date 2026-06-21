"""Paper 2, Figure: cross-engine DSD-onset, faceted fplll | G6K.

The whole cross-engine claim in one figure (Section 6, Tables tab:g6konset /
tab:xengdim): reference-free two-part DSD-onset modulus q vs n at beta=40 on
BOTH oracles. n=89 is an honest null (SD ~ BKZ ~ q194, dense window 100
seeds/cell); the gap reopens at n=101 (9% fplll, 7% G6K, N=40/cell) and persists
at n=113 (7% fplll, 6% G6K, N=40/cell) -- where the extended q-grid {487..859}
now LOCATES the onset (fplll SD 464.6 / BKZ 499.0; G6K SD 456.3 / BKZ 482.2),
so n=113 is drawn as a pinned point, not a >grid edge marker. On both oracles
and all three n the SD-BKZ onset q sits at or below the BKZ onset q -- SD-BKZ
finds the dense sublattice at the same or lower overstretch. The n=113 onset
brackets the fatigue estimate q_fat(113) ~= 503. Constants mirror the paper-2
tables (seed-backed via extract_dsd_onset.py --engine {fplll,g6k}); figure and
tables never disagree.
"""
import os

import matplotlib.pyplot as plt

from .._style import COLORS

# engine -> [(n, SD onset q, BKZ onset q, gap label)] -- all seed-backed 50%
# DSD-rate crossings from extract_dsd_onset.py --engine {fplll,g6k}.
PINNED = {
    "fplll (enum)":  [(89, 193.7, 193.8, "null"), (101, 257.3, 280.7, "9%"),
                      (113, 464.6, 499.0, "7%")],
    "G6K (sieve)":   [(89, 193.1, 194.0, "null"), (101, 249.9, 268.3, "7%"),
                      (113, 456.3, 482.2, "6%")],
}


def fig_ntru_xengine_onset(output_dir=".", fname="xengine_onset.png"):
    """Faceted (fplll | G6K) reference-free DSD-onset q vs n at beta=40."""
    sd_c, bkz_c = COLORS["sdbkz"], COLORS["bkz"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)

    for ax, (engine, rows) in zip(axes, PINNED.items(), strict=True):
        ns = [r[0] for r in rows]
        sd = [r[1] for r in rows]
        bkz = [r[2] for r in rows]
        ax.plot(ns, bkz, color=bkz_c, marker="s", markersize=6, linewidth=1.8,
                label="BKZ onset $q$", zorder=3)
        ax.plot(ns, sd, color=sd_c, marker="o", markersize=6, linewidth=1.8,
                label="SD-BKZ onset $q$", zorder=3)
        ax.fill_between(ns, sd, bkz, color=sd_c, alpha=0.12, zorder=1)
        # gap / null labels on each pinned cell
        for n, s, b, lbl in rows:
            ymid = (s + b) / 2
            txt = lbl if lbl == "null" else f"{lbl} gap"
            # n=113 sits high on the axis -- drop its label below the points so
            # it never collides with the top frame; others to the right.
            xytext = (n - 3.0, ymid - 26) if n == 113 else (n + 2.0, ymid)
            ha = "center" if n == 113 else "left"
            ax.annotate(txt, xy=(n, ymid), xytext=xytext,
                        fontsize=9, color="#334155", va="center", ha=ha,
                        arrowprops=dict(arrowstyle="-", color="#94a3b8",
                                        lw=0.8))
        ax.set_title(engine)
        ax.set_xlabel("NTRU parameter $n$")
        ax.set_xticks([89, 101, 113])
        ax.set_xlim(84, 119)
        ax.set_ylim(170, 540)

    axes[0].set_ylabel(r"DSD-onset modulus $q$ ($\beta=40$, two-part criterion)")
    axes[0].legend(loc="upper left", framealpha=0.9, fontsize=9)
    fig.suptitle(r"Cross-engine DSD-onset: null at $n=89$, gap reopens at "
                 r"$n=101$ and persists at $n=113$ (both oracles)", y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
