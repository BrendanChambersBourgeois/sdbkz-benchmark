"""Figure 10: GSO log-norm staircase with GSA and Li-Nguyen predictions.

The classic lattice paper figure: log||b*_i|| vs basis position i,
overlaid with theoretical GSA and LN reference lines computed from
formulas (not fitted).
"""
import math
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS


def fig_gso_profiles(groups, output_dir=".", show_groups=None):
    """Plot the classic lattice paper GSO log-norm staircase.

    log||b*_i|| vs basis index i, showing the geometric decrease.
    BKZ vs SD-BKZ vs Geometric Series Assumption (GSA) reference line.

    The Kannan embedding has a flat 'q-vectors' region at the start
    (log q) followed by the reduced region. Only the reduced region
    is interesting — we plot positions m onward.

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
            gs_bkz = s.get("gs_lognorms_bkz")
            gs_sd = s.get("gs_lognorms_sdbkz")
            if gs_bkz is None or gs_sd is None:
                continue
            bkz_profiles.append(gs_bkz)
            sd_profiles.append(gs_sd)

        if not bkz_profiles:
            ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} (no GSO data)")
            continue

        bkz_arr = np.array(bkz_profiles)
        sd_arr = np.array(sd_profiles)
        bkz_mean = bkz_arr.mean(axis=0)
        sd_mean = sd_arr.mean(axis=0)

        # Slice to the reduced region (positions m onward — skip flat q-block).
        # m is constant within a (n, β) group by construction, but assert
        # to surface any future data-loading bug that mixes heterogeneous m.
        m_values = {s["m"] for s in seeds if "m" in s}
        assert len(m_values) == 1, (
            f"gso_profiles: group (n={n}, β={beta}) has mixed m values "
            f"{m_values} — seed loading contract broken")
        m = m_values.pop()
        bkz_active = bkz_mean[m:]
        sd_active = sd_mean[m:]
        active_size = len(bkz_active)
        positions = np.arange(1, active_size + 1)

        # Theoretical predictions for the active block log-norms.
        # GSA: log||b*_i|| = (active_size + 1 - 2i) * log_delta + log_vol/active_size
        # The actual lattice has a non-trivial log_vol; use the mean BKZ
        # profile's log_vol so the theoretical lines have the same area.
        log_vol = float(np.sum(bkz_active))
        log_factor = math.log(beta / (2 * math.pi * math.e))
        log_delta_gsa = log_factor / (2 * beta)
        log_delta_ln = log_factor / (2 * (beta - 1))

        gsa_line = np.array([
            (active_size + 1 - 2 * i) * log_delta_gsa + log_vol / active_size
            for i in range(1, active_size + 1)
        ])
        ln_line = np.array([
            (active_size + 1 - 2 * i) * log_delta_ln + log_vol / active_size
            for i in range(1, active_size + 1)
        ])

        ax.plot(positions, gsa_line, color="#f85149", linewidth=1.4, linestyle=":",
                label="GSA prediction", zorder=2, alpha=0.85)
        ax.plot(positions, ln_line, color="#e3b341", linewidth=1.6, linestyle="--",
                label="LN prediction", zorder=3, alpha=0.9)
        ax.plot(positions, bkz_active, color=COLORS["bkz"], linewidth=1.6,
                label="BKZ", zorder=4)
        ax.plot(positions, sd_active, color=COLORS["sdbkz"], linewidth=1.6,
                label="SD-BKZ", zorder=5)

        ax.set_xlabel("Basis position $i$ (reduced region)", fontsize=10)
        ax.set_ylabel(r"$\log \, \|b^*_i\|$", fontsize=10)
        ax.set_title(f"{panel_labels[idx]} n={n}, $\\beta$={beta} "
                     f"({len(bkz_profiles)} seeds)", fontsize=11)
        ax.legend(fontsize=9, loc="upper right")

    fig.suptitle("Mean GSO log-norm profile vs theoretical predictions",
                 fontsize=14, y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "gso_profiles.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
