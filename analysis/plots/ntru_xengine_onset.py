"""Paper 2, Figure: cross-engine DSD-onset, faceted fplll | G6K.

The whole cross-engine claim in one figure (Section 6, Tables tab:g6konset /
tab:xengdim): reference-free two-part DSD-onset modulus q vs n at beta=40 on
BOTH oracles. n=89 is an honest null (SD ~ BKZ ~ q194, dense window 100
seeds/cell); the gap reopens at n=101 (9% fplll, 7% G6K, N=40/cell); n=113 is
edge evidence -- the 50% onset lies above the q<=439 grid, only q=439 fires
(SD 4/40 vs BKZ 1/40 fplll; 11/40 vs 2/40 G6K), so it is drawn as a >439 edge
marker, not a pinned point. Constants mirror the paper-2 tables (seed-backed
via extract_dsd_onset.py --engine {fplll,g6k}); figure and tables never disagree.
"""
import os

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .._style import COLORS

# engine -> [(n, SD onset q, BKZ onset q, label)] for the pinned cells (89,101)
PINNED = {
    "fplll (enum)":  [(89, 193.7, 193.8, "null"), (101, 257.3, 280.7, "9%")],
    "G6K (sieve)":   [(89, 193.1, 194.0, "null"), (101, 249.9, 268.3, "7%")],
}
# engine -> (n=113 edge: SD fire / BKZ fire out of 40 at q=439); onset is >439
EDGE_Q = 439
EDGE = {
    "fplll (enum)": (4, 1),
    "G6K (sieve)":  (11, 2),
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
        # gap / null labels on the pinned cells
        for n, s, b, lbl in rows:
            ymid = (s + b) / 2
            # leader line so "null" / "9%" point at the cell they describe.
            txt = lbl if lbl == "null" else f"{lbl} gap"
            ax.annotate(txt, xy=(n, ymid), xytext=(n + 2.0, ymid),
                        fontsize=9, color="#334155", va="center",
                        arrowprops=dict(arrowstyle="-", color="#94a3b8",
                                        lw=0.8))
        # n=113 edge: the onset lies above the q<=439 grid (unpinned). Continue
        # each line from n=101 as a DASHED up-arrow running off the top axis --
        # "rises beyond the plotted range (>439)" -- rather than as floating
        # disconnected markers. The arrows are kept SEPARATED (SD below BKZ) so
        # the gap persists into the edge, matching the edge data (SD fires more
        # often than BKZ at q=439); converging arrows would imply the gap closes.
        sfire, bfire = EDGE[engine]
        ax.annotate("", xy=(113, 305), xytext=(101, bkz[-1]),
                    arrowprops=dict(arrowstyle="-|>", color=bkz_c, lw=1.4,
                                    ls="--", shrinkA=3, shrinkB=0))
        ax.annotate("", xy=(113, 283), xytext=(101, sd[-1]),
                    arrowprops=dict(arrowstyle="-|>", color=sd_c, lw=1.4,
                                    ls="--", shrinkA=3, shrinkB=0))
        ax.annotate(f"onset $>439$ (edge at $q{{=}}439$:\nSD {sfire}/40 vs "
                    f"BKZ {bfire}/40)", xy=(113, 283), xytext=(106, 232),
                    fontsize=8, ha="center", color="#334155")
        ax.set_title(engine)
        ax.set_xlabel("NTRU parameter $n$")
        ax.set_xticks([89, 101, 113])
        ax.set_xlim(84, 119)
        ax.set_ylim(182, 322)

    axes[0].set_ylabel(r"DSD-onset modulus $q$ ($\beta=40$, two-part criterion)")
    # explain the dashed up-arrows: they are NOT measured points, they mark the
    # onset rising above the q<=439 grid at n=113 (edge evidence only).
    dashed_proxy = Line2D([0], [0], color="#334155", lw=1.4, ls="--",
                          marker=">", markersize=5,
                          label="onset $>$ grid (extrapolated edge)")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend(handles + [dashed_proxy], labels + [dashed_proxy.get_label()],
                   loc="upper left", framealpha=0.9, fontsize=9)
    fig.suptitle(r"Cross-engine DSD-onset: null at $n=89$, gap reopens at "
                 r"$n=101$ on both oracles", y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
