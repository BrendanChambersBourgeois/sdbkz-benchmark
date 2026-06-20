"""Paper 2, synthesis figure: NTRU fatigue phase diagram (n, q).

One-picture summary. The DvW21 fatigue curve q_fat(n) = 0.004 * n^2.484 marks
the lower edge of the overstretched regime (shaded). Over it sit the measured
reference-free DSD-onset curves for SD-BKZ and BKZ (beta=20, two-part
criterion, Table tab:dsdgap); the band between them is the SD-before-BKZ gap,
growing from ~0 at n=67 to 28% at n=113.

HONESTY: the measured 50%-DSD-rate onset is a stricter threshold than the
DvW21 asymptotic fatigue fit, so the onset curves sit progressively ABOVE
q_fat as n grows (near it at n=67, well above at n=113). They are plotted
where the data puts them, not forced onto q_fat; the caption says so. Onset
constants mirror ntru_dsd_onset_trend (seed-backed). No RNG.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS
from .ntru_dsd_onset_trend import ONSET_TREND


def q_fat(n):
    """DvW21 fatigue point (empirical fit): q_fat(n) ~ 0.004 * n^2.484."""
    return 0.004 * np.power(n, 2.484)


def fig_ntru_fatigue_phase(output_dir=".", fname="fatigue_phase.png"):
    """Fatigue phase diagram: q_fat curve + SD/BKZ DSD-onset + gap band."""
    ns = np.array([r[0] for r in ONSET_TREND], dtype=float)
    sd = np.array([r[1] for r in ONSET_TREND], dtype=float)
    bkz = np.array([r[2] for r in ONSET_TREND], dtype=float)
    gap = [r[3] for r in ONSET_TREND]
    sd_c, bkz_c = COLORS["sdbkz"], COLORS["bkz"]

    n_lo, n_hi = ns.min() - 4, ns.max() + 4
    n_smooth = np.linspace(n_lo, n_hi, 300)
    qf = q_fat(n_smooth)
    y_top = max(bkz.max(), qf.max()) * 1.08

    fig, ax = plt.subplots(figsize=(8.2, 5.4))

    # Overstretched regime = above the fatigue curve.
    ax.fill_between(n_smooth, qf, y_top, color="#f1f5f9", zorder=0)
    ax.plot(n_smooth, qf, color="#64748b", linestyle="-.", linewidth=1.5,
            zorder=2, label=r"fatigue $q_\mathrm{fat}(n)=0.004\,n^{2.484}$ (DvW21)")
    ax.annotate("overstretched regime", xy=(n_lo + 6, y_top * 0.93),
                fontsize=10, color="#64748b", style="italic")

    # Measured DSD onsets + the SD-before-BKZ gap band.
    ax.fill_between(ns, sd, bkz, color=sd_c, alpha=0.15, zorder=1,
                    label="SD-before-BKZ gap")
    ax.plot(ns, bkz, color=bkz_c, marker="s", markersize=6, linewidth=1.8,
            zorder=3, label="BKZ DSD-onset $q$")
    ax.plot(ns, sd, color=sd_c, marker="o", markersize=6, linewidth=1.8,
            zorder=3, label="SD-BKZ DSD-onset $q$")

    for n, s, b, g in zip(ns, sd, bkz, gap, strict=True):
        if g >= 5:
            # leader line from the % into the gap band it measures, so the
            # label is unambiguously the SD-to-BKZ gap at this n.
            ax.annotate(f"{g}% gap", xy=(n, (s + b) / 2),
                        xytext=(n + 2.5, (s + b) / 2),
                        fontsize=9, color="#334155", va="center",
                        arrowprops=dict(arrowstyle="-", color="#94a3b8", lw=0.8))

    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel("modulus $q$")
    ax.set_xlim(n_lo, n_hi)
    ax.set_ylim(0, y_top)
    ax.set_title(r"NTRU fatigue phase diagram ($\beta=20$): SD-BKZ enters DSD "
                 r"below BKZ, gap grows with $n$")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=9)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
