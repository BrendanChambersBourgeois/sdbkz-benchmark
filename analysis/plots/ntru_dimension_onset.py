"""Paper 2, Figure 1: NTRU SD-BKZ dimension-onset.

Mean d(LN) advantage (BKZ - SD-BKZ) vs lattice parameter n on circulant
NTRU at q=97, beta=20, 50 tours. Three regimes (Section 4): tied (n<=67) ->
sharp onset spike at n~71-73 -> tight +1.5-1.7 plateau (n>=79). Fully
recomputed from the per-seed `advantage` field of the ntru campaign seeds
(results/seeds/ntru/q97/...); no curated constants.

HONESTY: the onset zone n=71-73 is a two-outcome split (at n=71, 27/40 win /
13 lose), not Gaussian noise. There the raw per-seed advantages are scattered
(sign-coloured) so both modes are visible; elsewhere only the mean line is
drawn. Scatter x-spread is deterministic (no RNG -- determinism gate).
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

# Dimensions where the per-seed advantage is bimodal (win/lose); we scatter the
# seeds there to show both modes instead of collapsing them to a mean marker.
BIMODAL = {71, 73}


def fig_ntru_dimension_onset(groups, output_dir=".", beta=20, min_seeds=10,
                             fname="dimension_onset.png"):
    """Mean NTRU SD-BKZ advantage vs n, with per-seed scatter in the two-mode
    onset zone (n=71-73)."""
    rows = []  # (n, mean, advs)
    for (n, b), seeds in sorted(groups.items()):
        if b != beta or len(seeds) < min_seeds:
            continue
        advs = np.array([s["advantage"] for s in seeds], dtype=float)
        rows.append((n, float(advs.mean()), advs))

    if not rows:
        raise ValueError(f"no NTRU beta={beta} groups with >= {min_seeds} seeds")

    dims = np.array([r[0] for r in rows])
    means = np.array([r[1] for r in rows])
    sd_c, zero_c = COLORS["sdbkz"], COLORS["zero"]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axhline(0.0, color=zero_c, linewidth=1.0, linestyle="--", alpha=0.7, zorder=2)

    # Per-seed scatter in the two-mode zone, coloured by sign (win/lose).
    scat_done = False
    scatter_max = 0.0
    for n, m, advs in rows:
        if n not in BIMODAL:
            continue
        order = np.argsort(advs)
        xs = n + np.linspace(-0.45, 0.45, len(advs))  # deterministic spread
        a = advs[order]
        win = a > 0
        ax.scatter(xs[win], a[win], s=14, color=sd_c, alpha=0.7,
                   edgecolors="none", zorder=4,
                   label=("per-seed: SD wins" if not scat_done else None))
        ax.scatter(xs[~win], a[~win], s=14, color=zero_c, alpha=0.7,
                   edgecolors="none", zorder=4,
                   label=("per-seed: SD loses" if not scat_done else None))
        nwin = int(win.sum())
        # leader line from label down to the top of this n's column so the
        # win-count is unambiguously tied to its scatter cluster.
        ax.annotate(f"{nwin}/{len(advs)} win", xy=(n, a.max() + 0.15),
                    xytext=(n, a.max() + 1.4), fontsize=8.5, ha="center",
                    color="#1e293b",
                    arrowprops=dict(arrowstyle="-", color="#475569", lw=1.1))
        scatter_max = max(scatter_max, float(a.max()))
        scat_done = True

    # Mean line across all n (below scatter labels).
    ax.plot(dims, means, color=sd_c, marker="o", markersize=5, linewidth=1.8,
            zorder=3, label="mean advantage")

    peak_i = int(np.argmax(means))
    ax.annotate(
        f"onset spike\nn={dims[peak_i]}, mean {means[peak_i]:+.1f}",
        xy=(dims[peak_i], means[peak_i]),
        xytext=(dims[peak_i] + 4, means[peak_i] - 2.0),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="#334155", lw=1.0),
    )

    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel(r"$d(\mathrm{LN})$ advantage (BKZ $-$ SD-BKZ), nats"
                  "\n(positive $\\Rightarrow$ SD-BKZ wins)")
    ax.set_title(r"NTRU SD-BKZ dimension-onset ($q=97$, $\beta=20$, 50 tours)")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
    if scatter_max > 0:
        ax.set_ylim(top=scatter_max + 2.5)  # headroom for the centred win-labels

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
