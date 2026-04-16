"""Figure: Peak, dip, and total mean improvement trajectories vs dimension.

Three side-by-side panels (one per beta) showing three curves each:
  - Peak: the best single-position improvement (green)
  - Dip:  the worst single-position improvement (red)
  - Mean: the average across all positions (black)

This plot reveals the mechanism behind the rise-and-fall: at beta=20/30
the peak stays stable while the dip deepens, eventually dominating the
average.  At beta=40 both peak and dip collapse jointly, explaining the
sharpness of the cliff.
"""
import os
import numpy as np
import matplotlib.pyplot as plt

from .._style import BETA_LABELS, COLORS
from .._data import _per_position_group_stats


BETAS = [20, 30, 40]


def fig_peak_dip_trajectory(groups, output_dir=".", min_seeds=10):
    """Peak / dip / total-mean trajectories, one panel per beta.

    Args:
        groups: Output of load_all_seeds(), dict keyed by (n, beta).
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to include a group.
    """
    by_beta = {b: {"ns": [], "peaks": [], "dips": [], "totals": []}
               for b in BETAS}

    for (n, beta), seeds in sorted(groups.items()):
        if beta not in BETAS or len(seeds) < min_seeds:
            continue
        means, _, n_used = _per_position_group_stats(seeds)
        if means is None:
            continue
        d = by_beta[beta]
        d["ns"].append(n)
        d["peaks"].append(float(np.max(means)))
        d["dips"].append(float(np.min(means)))
        d["totals"].append(float(np.mean(means)))

    if not any(d["ns"] for d in by_beta.values()):
        print("  No groups with Rankin profile data for peak/dip trajectory")
        return

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, beta in zip(axes, BETAS):
        d = by_beta[beta]
        if not d["ns"]:
            ax.set_visible(False)
            continue
        ax.plot(d["ns"], d["peaks"], "o-", color=COLORS["sdbkz"],
                lw=2, label="Peak (best position)")
        ax.plot(d["ns"], d["dips"], "o-", color=COLORS["zero"],
                lw=2, label="Dip (worst position)")
        ax.plot(d["ns"], d["totals"], "s-", color=COLORS["bkz"],
                lw=1.5, alpha=0.7, label="Mean across positions")
        ax.axhline(0, color="#475569", lw=0.5, ls="--")
        ax.set_title(BETA_LABELS[beta], fontsize=12)
        ax.set_xlabel("Dimension n")
        ax.legend(loc="lower left", fontsize=9)

    axes[0].set_ylabel("Improvement (nats)")
    fig.suptitle(
        "Peak vs dip vs total mean \u2014 the dip drives the rise-and-fall",
        fontsize=13, y=1.01,
    )
    fig.tight_layout()

    path = os.path.join(output_dir, "peak_dip_trajectory.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
