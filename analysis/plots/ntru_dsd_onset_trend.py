"""Paper 2, Figure 2: NTRU DSD-onset gap grows with dimension.

SD-BKZ vs BKZ reference-free DSD-onset modulus (smallest q at which the
variant flags dense-sublattice discovery, b1>1.5) as a function of n, with
the SD-vs-BKZ gap% annotated. SD-BKZ reaches DSD at progressively lower q
than BKZ as n grows (gap 0 -> 27%).

DATA PROVENANCE: the per-(n, variant) onset moduli below are the committed
5-point trend (paper2 Table tab:dsdgap; /mnt/hgfs/Research/paper_findings.md
"SD-BKZ DSD-onset GAP GROWS with dimension", reference-free b1>1.5, fplll
beta=20, ~15-20 seeds/cell). The full per-q DSD-fraction extraction that
produced these onsets is not yet codified as a reusable analysis, so the
trend is carried here as constants kept in lock-step with the table rather
than recomputed; recomputation from the ntru q-sweep seeds is future work.
"""
import os

import matplotlib.pyplot as plt

from .._style import COLORS

# (n, SD onset q, BKZ onset q, gap%) -- mirrors paper2 Table tab:dsdgap
# exactly. gap% is carried verbatim from the committed table (its published
# values, not recomputed: the curated table rounded inconsistently at the
# edge, e.g. n=89 -> 18) so figure and table never disagree.
ONSET_TREND = [
    (67, 146, 149, 2),
    (79, 175, 175, 0),
    (89, 237, 281, 18),
    (101, 426, 514, 21),
    (113, 732, 932, 27),
]


def fig_ntru_dsd_onset_trend(output_dir=".", fname="dsd_onset_trend.png"):
    """SD vs BKZ DSD-onset modulus vs n, with gap% annotations."""
    ns = [r[0] for r in ONSET_TREND]
    sd = [r[1] for r in ONSET_TREND]
    bkz = [r[2] for r in ONSET_TREND]
    gap_pct = [r[3] for r in ONSET_TREND]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ns, bkz, color=COLORS["bkz"], marker="s", markersize=6,
            linewidth=1.8, label="BKZ onset $q$", zorder=3)
    ax.plot(ns, sd, color=COLORS["sdbkz"], marker="o", markersize=6,
            linewidth=1.8, label="SD-BKZ onset $q$", zorder=3)
    ax.fill_between(ns, sd, bkz, color=COLORS["sdbkz"], alpha=0.10, zorder=1)

    for n, s, b, g in zip(ns, sd, bkz, gap_pct, strict=True):
        ax.annotate(f"{g}%", xy=(n, (s + b) / 2),
                    xytext=(n + 1.2, (s + b) / 2), fontsize=9,
                    color="#334155", va="center")

    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel(r"DSD-onset modulus $q$ (reference-free, $b_1>1.5$)")
    ax.set_title(r"SD-BKZ reaches DSD at lower $q$ than BKZ; gap grows with $n$"
                 "\n" r"($\beta=20$, gap% labelled)")
    ax.legend(loc="upper left", framealpha=0.9)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
