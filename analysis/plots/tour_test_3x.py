"""Figure 7: 3x tour count capability test.

Two panels: per-group remaining gap after running BKZ for 3× the normal
tour budget (left), and an example mean trajectory comparing BKZ@3x to
SD-BKZ@1x (right).
"""
import os
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt

from .._style import COLORS


def fig_3x_tour_test(tour_seeds, output_dir="."):
    """Visualize the 3x tour count capability test.

    Uses the extended 500-seed dataset across multiple groups.
    Left panel: gap remaining after 3x tours per group (box plot).
    Right panel: mean d(LN) trajectory for a representative group showing
    BKZ stagnation vs SD-BKZ descent.

    Args:
        tour_seeds: Output of load_3x_tour_data() — supports both old and
            extended format.
        output_dir: Where to save the PNG.
    """
    if not tour_seeds:
        print("  No 3x tour data available")
        return

    # Detect format: extended has 'advantage_3x', old has 'bkz_70_final'
    is_extended = "advantage_3x" in tour_seeds[0]

    if not is_extended:
        # Fall back to old single-group format
        seeds_with_data = [s for s in tour_seeds
                           if s.get("bkz_70_final") and s.get("sdbkz_70_final")]
        if not seeds_with_data:
            print("  No complete 3x tour seeds")
            return
        fig, ax = plt.subplots(1, 1, figsize=(8, 5))
        bkz70 = [s["bkz_70_final"] for s in seeds_with_data]
        bkz210 = [s["bkz_210_final"] for s in seeds_with_data]
        sd70 = [s["sdbkz_70_final"] for s in seeds_with_data]
        x = np.arange(len(seeds_with_data))
        width = 0.25
        ax.bar(x - width, bkz70, width, label="BKZ @ 70", color=COLORS["bkz"], alpha=0.6)
        ax.bar(x, bkz210, width, label="BKZ @ 210 (3x)", color=COLORS["bkz"], alpha=0.9)
        ax.bar(x + width, sd70, width, label="SD-BKZ @ 70", color=COLORS["sdbkz"], alpha=0.8)
        ax.set_ylabel("Final d(LN) (nats)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = os.path.join(output_dir, "tour_test_3x.png")
        fig.savefig(path)
        plt.close(fig)
        print(f"  Saved: {path}")
        return

    # Extended format: group by (n, beta)
    groups = defaultdict(list)
    for s in tour_seeds:
        groups[(s["n"], s["beta"])].append(s)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Left panel: box plot of remaining gap (advantage_3x) per group.
    # The closed/total count is baked into the x-axis tick label so it
    # sits below the plot — no chance of colliding with whiskers, the
    # subplot title above, or the right subplot.
    sorted_keys = sorted(groups.keys())
    box_data = []
    labels = []
    colors_list = []
    for (n, beta) in sorted_keys:
        seeds = groups[(n, beta)]
        advs = [s["advantage_3x"] for s in seeds]
        box_data.append(advs)
        closed = sum(1 for a in advs if a <= 0)
        labels.append(f"n={n}, $\\beta$={beta}\n"
                      f"{len(seeds)} seeds\n"
                      f"{closed}/{len(seeds)} closed")
        colors_list.append(COLORS["sdbkz"] if beta == 30 else COLORS["bkz"])

    bp = ax1.boxplot(box_data, labels=labels, patch_artist=True, widths=0.6,
                     medianprops=dict(color="black", linewidth=1.5))
    for patch, color in zip(bp["boxes"], colors_list):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax1.axhline(y=0, color="red", linewidth=1, linestyle="--", alpha=0.7,
                label="Gap closed (BKZ matches SD-BKZ)")
    ax1.set_ylabel("Remaining gap: BKZ@3x $-$ SD-BKZ@1x (nats)")
    ax1.set_title("3x tours: remaining gap per group")
    ax1.legend(fontsize=8, loc="lower right")

    # Right panel: mean d(LN) trajectory for largest beta=30 group
    beta30_groups = [(n, b) for (n, b) in sorted_keys if b == 30]
    if beta30_groups:
        rep_key = max(beta30_groups, key=lambda k: len(groups[k]))
        rep_seeds = groups[rep_key]
        n_rep, beta_rep = rep_key
        normal_tours = rep_seeds[0]["normal_tours"]
        triple_tours = rep_seeds[0]["triple_tours"]

        bkz_trajs = np.array([s["bkz_dln_per_tour"] for s in rep_seeds])
        sd_trajs = np.array([s["sdbkz_dln_per_tour"] for s in rep_seeds])
        mean_bkz = bkz_trajs.mean(axis=0)
        mean_sd = sd_trajs.mean(axis=0)
        std_bkz = bkz_trajs.std(axis=0, ddof=1)
        std_sd = sd_trajs.std(axis=0, ddof=1)

        tours_bkz = np.arange(1, len(mean_bkz) + 1)
        tours_sd = np.arange(1, len(mean_sd) + 1)

        ax2.plot(tours_bkz, mean_bkz, color=COLORS["bkz"], linewidth=1.5,
                 label=f"BKZ ({triple_tours} tours)")
        ax2.fill_between(tours_bkz, mean_bkz - std_bkz, mean_bkz + std_bkz,
                         color=COLORS["bkz"], alpha=0.15)
        ax2.plot(tours_sd, mean_sd, color=COLORS["sdbkz"], linewidth=1.5,
                 label=f"SD-BKZ ({normal_tours} tours)")
        ax2.fill_between(tours_sd, mean_sd - std_sd, mean_sd + std_sd,
                         color=COLORS["sdbkz"], alpha=0.15)
        ax2.axvline(x=normal_tours, color="gray", linewidth=0.8, linestyle=":",
                    label=f"Normal limit ({normal_tours} tours)")

        ax2.set_xlabel("Tour")
        ax2.set_ylabel("d(LN) (nats)")
        ax2.set_title(f"Mean trajectory (n={n_rep}, $\\beta$={beta_rep}, "
                      f"{len(rep_seeds)} seeds)")
        ax2.legend(fontsize=8)

    fig.suptitle("Capability test: BKZ @ 3x tours vs SD-BKZ @ 1x",
                 fontsize=13, y=1.02)
    fig.tight_layout()
    path = os.path.join(output_dir, "tour_test_3x.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
