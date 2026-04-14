"""Figure 3: Per-tour convergence trajectories at representative groups.

2×2 grid showing per-tour d(LN) for BKZ vs SD-BKZ at four (n, β) groups
representing early advantage, peak, decline, and reversal.
"""
import os
import numpy as np
import matplotlib.pyplot as plt

from .._style import COLORS


def fig_convergence_trajectories(groups, output_dir=".",
                                 show_groups=None, n_example_seeds=5):
    """Plot per-tour d(LN) for BKZ vs SD-BKZ at representative groups.

    2x2 grid: early advantage, peak, decline, reversal. Mean trajectory
    with std band, plus faint individual seeds.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        show_groups: List of (n, beta) to plot. None = auto-select 4.
        n_example_seeds: How many individual seed traces to show (faintly).
    """
    if show_groups is None:
        # 4 groups telling the story: early win, peak, decline, reversal
        candidates = [(70, 30), (100, 30), (130, 30), (150, 30)]
        show_groups = [g for g in candidates if g in groups]
        if len(show_groups) < 4:
            fallbacks = [(50, 30), (90, 30), (120, 20), (140, 20)]
            for fb in fallbacks:
                if fb in groups and fb not in show_groups:
                    show_groups.append(fb)
                if len(show_groups) >= 4:
                    break

    show_groups = show_groups[:4]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes = axes.flatten()
    panel_labels = ["(a)", "(b)", "(c)", "(d)"]

    for idx, (n, beta) in enumerate(show_groups):
        ax = axes[idx]
        seeds = groups.get((n, beta), [])
        if not seeds:
            ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} (no data)")
            continue

        bkz_tours_all = []
        sd_tours_all = []
        for s in seeds:
            b = s.get("bkz_dln_per_tour", [])
            sd = s.get("sdbkz_dln_per_tour", [])
            if b and sd:
                bkz_tours_all.append(b)
                sd_tours_all.append(sd)

        if not bkz_tours_all:
            ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} (no per-tour data)")
            continue

        # Plot individual seeds (faint)
        for i, (b, sd) in enumerate(zip(bkz_tours_all[:n_example_seeds],
                                         sd_tours_all[:n_example_seeds])):
            tours_i = np.arange(1, len(b) + 1)
            ax.plot(tours_i, b, color=COLORS["bkz"], alpha=0.12, linewidth=0.5)
            ax.plot(tours_i, sd, color=COLORS["sdbkz"], alpha=0.12, linewidth=0.5)

        # Mean + std band
        min_len = min(len(b) for b in bkz_tours_all)
        bkz_arr = np.array([b[:min_len] for b in bkz_tours_all])
        sd_arr = np.array([sd[:min_len] for sd in sd_tours_all])
        bkz_mean = bkz_arr.mean(axis=0)
        sd_mean = sd_arr.mean(axis=0)
        bkz_std = bkz_arr.std(axis=0, ddof=1)
        sd_std = sd_arr.std(axis=0, ddof=1)
        tours = np.arange(1, min_len + 1)

        ax.plot(tours, bkz_mean, color=COLORS["bkz"], linewidth=2,
                label="BKZ")
        ax.fill_between(tours, bkz_mean - bkz_std, bkz_mean + bkz_std,
                        color=COLORS["bkz"], alpha=0.12)
        ax.plot(tours, sd_mean, color=COLORS["sdbkz"], linewidth=2,
                label="SD-BKZ")
        ax.fill_between(tours, sd_mean - sd_std, sd_mean + sd_std,
                        color=COLORS["sdbkz"], alpha=0.12)

        # Annotate final gap
        gap = bkz_mean[-1] - sd_mean[-1]
        win_pct = np.mean(np.array([s["advantage"] for s in seeds]) > 0) * 100
        ax.text(0.97, 0.95,
                f"$\\Delta$={gap:+.3f}\nwin={win_pct:.0f}%",
                transform=ax.transAxes, fontsize=9, ha="right", va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        ax.set_xlabel("Tour", fontsize=10)
        ax.set_ylabel("d(LN) (nats)", fontsize=10)
        ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} "
                     f"({len(bkz_tours_all)} seeds)", fontsize=11)
        # Legend at upper center — top-middle of trajectory plots is empty
        # space, and the (Δ, win%) annotation lives at upper right.
        ax.legend(fontsize=9, loc="upper center")

    fig.suptitle("Per-tour convergence: BKZ vs SD-BKZ ($\\beta$=30 progression)",
                 fontsize=14, y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "convergence_trajectories.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
