"""Figure 6: β/n ratio vs mean advantage scatter.

Visualizes the empirical β/n ≈ 0.20 threshold below which the SD-BKZ
backward pass becomes ineffective.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import BETA_COLORS, BETA_LABELS, BETA_MARKERS, COLORS


def fig_beta_n_scatter(groups, output_dir=".", min_seeds=10):
    """Scatter plot of β/n ratio vs mean advantage, colored by beta.

    Visualizes the threshold below which the backward pass is ineffective.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to include.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds:
            continue
        advs = np.array([s["advantage"] for s in seeds])
        ratio = beta / n
        color = BETA_COLORS[beta]
        marker = BETA_MARKERS[beta]
        size = min(120, max(30, len(seeds)))

        ax.scatter(ratio, np.mean(advs), color=color, marker=marker,
                   s=size, zorder=3, edgecolors="white", linewidth=0.5)
        # Only label β=30 points to avoid label-soup. The other betas are
        # distinguished by marker color/shape via the legend.
        if beta == 30:
            ax.annotate(f"n={n}", (ratio, np.mean(advs)),
                        fontsize=7, textcoords="offset points", xytext=(6, 3),
                        color=color)

    ax.axhline(y=0, color=COLORS["zero"], linewidth=1, linestyle="--",
               alpha=0.7)
    ax.axvspan(0, 0.20, color=COLORS["zero"], alpha=0.05,
               label="β/n < 0.20 (collapse zone)")

    ax.set_xlabel("β/n ratio")
    ax.set_ylabel("Mean d(LN) advantage (nats)")
    ax.set_title("Backward pass effectiveness vs β/n ratio")

    # Manual legend for betas
    for beta in [20, 30, 40]:
        ax.scatter([], [], color=BETA_COLORS[beta],
                   marker=BETA_MARKERS[beta], s=60, label=BETA_LABELS[beta])
    ax.legend(loc="upper left", fontsize=9)

    fig.tight_layout()
    path = os.path.join(output_dir, "beta_n_scatter.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
