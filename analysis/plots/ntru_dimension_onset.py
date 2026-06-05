"""Paper 2, Figure 1: NTRU SD-BKZ dimension-onset.

Mean d(LN) advantage (BKZ - SD-BKZ) vs lattice parameter n on circulant
NTRU at q=97, beta=20, 50 tours, with a +-1 sigma band. Shows the three
regimes of Section 4 (tied -> sharp onset spike at n~71-73 -> tight +1.5
plateau). Fully recomputed from the per-seed `advantage` field of the
ntru campaign seeds (results/seeds/ntru/q97/...); no curated constants.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS


def fig_ntru_dimension_onset(groups, output_dir=".", beta=20, min_seeds=10,
                             fname="dimension_onset.png"):
    """Mean NTRU SD-BKZ advantage vs n with a +-1 sigma band.

    Args:
        groups: load_all_seeds() output, keyed (n, beta).
        output_dir: directory for the PNG.
        beta: block size to plot (NTRU onset sweep is beta=20).
        min_seeds: minimum seeds to plot a point.
        fname: output filename.
    """
    dims, means, stds, counts = [], [], [], []
    for (n, b), seeds in sorted(groups.items()):
        if b != beta or len(seeds) < min_seeds:
            continue
        advs = np.array([s["advantage"] for s in seeds])
        dims.append(n)
        means.append(float(np.mean(advs)))
        stds.append(float(np.std(advs, ddof=1)))
        counts.append(len(seeds))

    if not dims:
        raise ValueError(f"no NTRU beta={beta} groups with >= {min_seeds} seeds")

    dims = np.array(dims)
    means = np.array(means)
    stds = np.array(stds)

    fig, ax = plt.subplots(figsize=(8, 5))
    color = COLORS["sdbkz"]
    ax.fill_between(dims, means - stds, means + stds,
                    color=color, alpha=0.12, zorder=1,
                    label=r"$\pm 1\sigma$")
    ax.plot(dims, means, color=color, marker="o", markersize=5,
            linewidth=1.8, zorder=3, label="mean advantage")
    ax.axhline(0.0, color=COLORS["zero"], linewidth=1.0, linestyle="--",
               alpha=0.7, zorder=2)

    # Mark the onset zone (where the mean spikes above the plateau).
    peak_i = int(np.argmax(means))
    ax.annotate(
        f"onset spike\nn={dims[peak_i]}, mean {means[peak_i]:+.1f}",
        xy=(dims[peak_i], means[peak_i]),
        xytext=(dims[peak_i] + 4, means[peak_i] - 1.5),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="#334155", lw=1.0),
    )

    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel(r"$d(\mathrm{LN})$ advantage (BKZ $-$ SD-BKZ), nats")
    ax.set_title(r"NTRU SD-BKZ dimension-onset ($q=97$, $\beta=20$, 50 tours)")
    ax.legend(loc="upper left", framealpha=0.9)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
