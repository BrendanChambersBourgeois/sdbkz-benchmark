"""Figure 2: Per-group advantage distribution histograms.

3×4 grid of histograms (one row per beta) showing the progression from
positive advantage (peak) through crossover to negative (BKZ wins).
"""
import os
import numpy as np
import matplotlib.pyplot as plt

from .._style import COLORS, BETA_COLORS


def fig_advantage_histograms(groups, output_dir=".", min_seeds=20):
    """Generate per-group histograms showing advantage asymmetry.

    Shows only representative groups to keep the figure to one page:
    one row per beta, columns showing the progression from positive to
    negative advantage (peak → crossover → negative).

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save PNGs.
        min_seeds: Minimum seeds to plot.
    """
    representative = [
        (50, 20), (90, 20), (120, 20), (150, 20),   # β=20: rise → fall
        (90, 30), (100, 30), (130, 30), (150, 30),   # β=30: rise → peak → fall
        (70, 40), (90, 40), (120, 40), (130, 40),    # β=40: rise → cliff
    ]
    eligible = {k: v for k, v in groups.items()
                if k in representative and len(v) >= min_seeds}
    if not eligible:
        print("  No groups with enough seeds for histograms")
        return

    betas = [20, 30, 40]
    cols = 4
    fig, axes = plt.subplots(3, cols, figsize=(16, 10))

    for row, beta in enumerate(betas):
        beta_groups = [(n, b) for (n, b) in sorted(eligible.keys()) if b == beta]
        for col in range(cols):
            ax = axes[row][col]
            if col < len(beta_groups):
                n, b = beta_groups[col]
                seeds = eligible[(n, b)]
                advs = np.array([s["advantage"] for s in seeds])
                color = BETA_COLORS[beta]

                ax.hist(advs, bins=20, color=color, alpha=0.7, edgecolor="white",
                        linewidth=0.5)
                ax.axvline(x=0, color=COLORS["zero"], linewidth=1, linestyle="--")
                ax.axvline(x=np.mean(advs), color="black", linewidth=1.2,
                           linestyle="-", label=f"mean={np.mean(advs):.3f}")

                win_pct = np.mean(advs > 0) * 100
                ax.set_title(f"n={n}, $\\beta$={beta} ({len(seeds)}s)",
                             fontsize=10)
                ax.text(0.97, 0.95, f"win={win_pct:.0f}%",
                        transform=ax.transAxes, fontsize=9, ha="right", va="top",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                  alpha=0.8))
                ax.legend(fontsize=7, loc="upper left")
                if row == 2:
                    ax.set_xlabel("Advantage (nats)", fontsize=9)
                if col == 0:
                    ax.set_ylabel(f"$\\beta$={beta}\nCount", fontsize=9)
            else:
                ax.set_visible(False)

    fig.suptitle("d(LN) advantage distributions: peak $\\to$ crossover $\\to$ reversal",
                 fontsize=14, y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "advantage_histograms.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
