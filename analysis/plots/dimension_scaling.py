"""Figure 1: Dimension scaling — the hero figure.

Mean d(LN) advantage vs lattice dimension n, one curve per beta. Shows
the rise-peak-decline pattern with shaded ±1σ bands. This is THE figure
that summarizes the campaign.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import BETA_COLORS, BETA_LABELS, BETA_MARKERS, COLORS


def fig_dimension_scaling(groups, output_dir=".", min_seeds=10):
    """Generate the hero figure: mean d(LN) advantage vs dimension, per beta.

    Shows the rise-peak-decline pattern with shaded ±1σ bands.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to plot a point.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    for beta in [20, 30, 40]:
        dims, means, stds, counts = [], [], [], []
        for (n, b), seeds in sorted(groups.items()):
            if b != beta or len(seeds) < min_seeds:
                continue
            advs = np.array([s["advantage"] for s in seeds])
            dims.append(n)
            means.append(np.mean(advs))
            stds.append(np.std(advs, ddof=1))
            counts.append(len(seeds))

        if not dims:
            continue

        dims, means, stds = np.array(dims), np.array(means), np.array(stds)
        color = BETA_COLORS[beta]
        marker = BETA_MARKERS[beta]

        ax.plot(dims, means, color=color, marker=marker, markersize=5,
                linewidth=1.8, label=BETA_LABELS[beta], zorder=3)
        ax.fill_between(dims, means - stds, means + stds,
                         color=color, alpha=0.12, zorder=1)

        # Annotate partial groups
        for d, m, c in zip(dims, means, counts, strict=False):
            if c < 100:
                ax.annotate(f"{c}s", (d, m), fontsize=7, color=color,
                            textcoords="offset points", xytext=(5, 5))

    ax.axhline(y=0, color=COLORS["zero"], linewidth=1, linestyle="--",
               alpha=0.7, label="Zero (BKZ = SD-BKZ)")
    ax.set_xlabel("Secret dimension n")
    ax.set_ylabel("Mean d(LN) advantage (nats)")
    ax.set_title("SD-BKZ advantage: rise, peak, decline")
    ax.legend(loc="upper left", framealpha=0.9)

    path = os.path.join(output_dir, "dimension_scaling.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
