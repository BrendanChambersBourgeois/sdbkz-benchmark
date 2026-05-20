"""Figure: Per-position SD-BKZ improvement across all (n, beta) groups.

Three vertically stacked panels (one per beta) showing per-position
|BKZ-R*| - |SDBKZ-R*| as line plots, one curve per dimension n colored
by viridis.  The x-axis is fractional position in the active block
(0 = head, 1 = tail) so curves at different n align visually.

This is the granular companion to fig_spatial_decomposition, which bins
the same quantity into three segments.  The per-position view reveals
the negative overshoot dip near the tail that the 3-bin average masks.
"""
import os

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np

from .._data import _per_position_group_stats
from .._style import BETA_LABELS

BETAS = [20, 30, 40]


def fig_per_position_landscape(groups, output_dir=".", min_seeds=10):
    """Per-position improvement overlay, one panel per beta.

    Args:
        groups: Output of load_all_seeds(), dict keyed by (n, beta).
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to include a group.
    """
    by_beta = {b: [] for b in BETAS}
    for (n, beta), seeds in sorted(groups.items()):
        if beta not in BETAS or len(seeds) < min_seeds:
            continue
        means, stds, n_used = _per_position_group_stats(seeds)
        if means is None:
            continue
        by_beta[beta].append({"n": n, "means": means, "seeds": n_used})

    if not any(by_beta.values()):
        print("  No groups with Rankin profile data for per-position landscape")
        return

    all_ns = sorted({d["n"] for rows in by_beta.values() for d in rows})
    cmap = cm.viridis
    n_to_color = {n: cmap(i / max(len(all_ns) - 1, 1))
                  for i, n in enumerate(all_ns)}

    fig, axes = plt.subplots(3, 1, figsize=(9, 10.5))
    for ax, beta in zip(axes, BETAS, strict=False):
        ax.set_title(BETA_LABELS[beta], loc="left", fontsize=12)
        ax.axhline(0, color="#475569", lw=0.8, ls="-", alpha=0.7)
        ax.axvline(1 / 3, color="#94a3b8", lw=0.5, alpha=0.4)
        ax.axvline(2 / 3, color="#94a3b8", lw=0.5, alpha=0.4)

        for d in by_beta[beta]:
            n = d["n"]
            x = np.linspace(0, 1, len(d["means"]))
            ax.plot(x, d["means"], color=n_to_color[n], lw=1.4,
                    label=f"n={n}", alpha=0.85)

        ax.legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.9)
        ax.set_ylabel("|BKZ\u2212R*| \u2212 |SDBKZ\u2212R*|  (nats)")

    axes[-1].set_xlabel("Fractional position in active block (0 = head, 1 = tail)")
    fig.suptitle("Per-position SD-BKZ improvement landscape", fontsize=13, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    path = os.path.join(output_dir, "per_position_landscape.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
