"""Figure 5: Absolute d(LN) for both algorithms across dimensions.

Three panels (one per beta) showing absolute d(LN) for BKZ and SD-BKZ,
contextualizing the advantage relative to total distance from the LN
fixed point.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS


def fig_absolute_dln(groups, output_dir=".", min_seeds=10):
    """Plot absolute d(LN) for both algorithms across dimensions.

    Contextualizes the advantage: shows whether the gap is proportional
    to absolute distance from the fixed point.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to include.
    """
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)

    for ax, beta in zip(axes, [20, 30, 40], strict=False):
        dims, bkz_means, sd_means, bkz_stds, sd_stds = [], [], [], [], []
        for (n, b), seeds in sorted(groups.items()):
            if b != beta or len(seeds) < min_seeds:
                continue
            bkz_dlns = [s["bkz_final_dln"] for s in seeds if "bkz_final_dln" in s]
            sd_dlns = [s["sdbkz_final_dln"] for s in seeds if "sdbkz_final_dln" in s]
            if not bkz_dlns or not sd_dlns:
                continue
            dims.append(n)
            bkz_means.append(np.mean(bkz_dlns))
            sd_means.append(np.mean(sd_dlns))
            bkz_stds.append(np.std(bkz_dlns, ddof=1))
            sd_stds.append(np.std(sd_dlns, ddof=1))

        if not dims:
            ax.set_title(f"β = {beta}\n(no data)")
            continue

        dims = np.array(dims)
        ax.plot(dims, bkz_means, color=COLORS["bkz"], marker="o",
                markersize=4, linewidth=1.5, label="BKZ")
        ax.fill_between(dims,
                         np.array(bkz_means) - np.array(bkz_stds),
                         np.array(bkz_means) + np.array(bkz_stds),
                         color=COLORS["bkz"], alpha=0.1)
        ax.plot(dims, sd_means, color=COLORS["sdbkz"], marker="s",
                markersize=4, linewidth=1.5, label="SD-BKZ")
        ax.fill_between(dims,
                         np.array(sd_means) - np.array(sd_stds),
                         np.array(sd_means) + np.array(sd_stds),
                         color=COLORS["sdbkz"], alpha=0.1)

        ax.set_xlabel("Secret dimension n")
        ax.set_title(f"β = {beta}")
        ax.legend(fontsize=9)

    axes[0].set_ylabel("Absolute d(LN) (nats)")
    fig.suptitle("Distance to Li-Nguyen fixed point", fontsize=14, y=1.02)
    fig.tight_layout()
    path = os.path.join(output_dir, "absolute_dln.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
