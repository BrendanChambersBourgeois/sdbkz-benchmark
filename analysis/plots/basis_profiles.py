"""Figure 9: Mean Rankin profile vs basis position, BKZ vs SD-BKZ.

2×2 grid (one panel per representative (n, β) group) showing the
averaged Rankin profile shapes across all seeds in each group.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS


def fig_basis_profiles(groups, output_dir=".", show_groups=None):
    """Plot the actual Rankin profile of the reduced basis vs the Li-Nguyen
    theoretical fixed point.

    This is the canonical lattice paper figure: shows the GSO log-norm
    profile shape directly. Each panel = one (n, β) group, with three
    curves: BKZ result, SD-BKZ result, and the theoretical fixed point.
    Profiles are averaged across all seeds in the group.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        show_groups: List of (n, beta) to plot. None = auto-select 4.
    """
    if show_groups is None:
        candidates = [(70, 30), (100, 30), (130, 30), (150, 30)]
        show_groups = [g for g in candidates if g in groups]
        if len(show_groups) < 4:
            for fb in [(50, 30), (90, 30), (120, 30), (140, 30)]:
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

        bkz_profiles = []
        sd_profiles = []
        for s in seeds:
            rp_bkz = s.get("rankin_profile_bkz")
            rp_sd = s.get("rankin_profile_sdbkz")
            if rp_bkz is None or rp_sd is None:
                continue
            bkz_profiles.append(rp_bkz)
            sd_profiles.append(rp_sd)

        if not bkz_profiles:
            ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} (no profile data)")
            continue

        bkz_arr = np.array(bkz_profiles)
        sd_arr = np.array(sd_profiles)
        bkz_mean = bkz_arr.mean(axis=0)
        sd_mean = sd_arr.mean(axis=0)

        size = bkz_arr.shape[1]
        positions = np.arange(1, size + 1)

        ax.plot(positions, bkz_mean, color=COLORS["bkz"], linewidth=1.8,
                label="BKZ", zorder=3)
        ax.plot(positions, sd_mean, color=COLORS["sdbkz"], linewidth=1.8,
                label="SD-BKZ", zorder=4)

        ax.set_xlabel("Basis position $i$", fontsize=10)
        ax.set_ylabel(r"Rankin log-norm $r_i$", fontsize=10)
        ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} "
                     f"({len(bkz_profiles)} seeds)", fontsize=11)
        ax.legend(fontsize=9, loc="best")

    fig.suptitle(r"Mean Rankin profile: BKZ vs SD-BKZ ($\beta$=30 progression)",
                 fontsize=14, y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "basis_profiles.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
