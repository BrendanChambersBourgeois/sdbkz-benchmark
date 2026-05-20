"""Figure 12: 500-tour convergence test (n=90 + n=140 side-by-side).

Two convergence regimes at β=30:
  - n=90  — BKZ flatlines after tour 70, SD-BKZ keeps improving
  - n=140 — Both algorithms slowly improve, BKZ wins at full convergence

Together these pre-empt the "you didn't run BKZ long enough" reviewer
objection at both ends of the dimension range.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._data import _load_convergence_files
from .._style import COLORS


def fig_convergence_500_tours(output_dir="."):
    """Mean d(LN) over 500 tours for BKZ and SD-BKZ at n=90 AND n=140 (β=30).

    Sources the two convergence regimes from the v1.3 seed manifest via
    (campaign="convergence", n, beta=30, max_tours=500) selectors —
    no legacy-dir args anymore, since the v2.0.0 symlink drop removed
    `results/convergence_test/` and `results/convergence/`.
    """
    n90 = _load_convergence_files(n=90, beta=30, max_tours=500)
    n140 = _load_convergence_files(n=140, beta=30, max_tours=500)

    if n90[4] == 0 and n140[4] == 0:
        print("  No convergence test data in either directory")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    def plot_row(row_axes, data, panel_letters, regime_text):
        bkz_arr, sd_arr, n_val, beta_val, n_seeds = data
        if n_seeds == 0:
            for ax in row_axes:
                ax.text(0.5, 0.5, "no data", ha="center", va="center",
                        transform=ax.transAxes, fontsize=14, color="gray")
            return

        bkz_mean = bkz_arr.mean(axis=0)
        sd_mean = sd_arr.mean(axis=0)
        bkz_std = bkz_arr.std(axis=0, ddof=1) if bkz_arr.shape[0] >= 2 else np.zeros_like(bkz_mean)
        sd_std = sd_arr.std(axis=0, ddof=1) if sd_arr.shape[0] >= 2 else np.zeros_like(sd_mean)
        n_tours = bkz_arr.shape[1]
        tours = np.arange(1, n_tours + 1)

        # The "improvement since tour N" panel anchors at tour REF_TOUR.
        # REF_TOUR is the standard tour budget; convergence_500 data is
        # always 500 tours, so REF_TOUR=70 is safe under normal inputs,
        # but we guard against shorter trajectories defensively.
        REF_TOUR = 70
        ref_idx = REF_TOUR - 1  # 0-indexed
        if n_tours <= ref_idx:
            ax_right = row_axes[1]
            ax_right.text(0.5, 0.5,
                          f"input has {n_tours} tours (need ≥{REF_TOUR})",
                          ha="center", va="center", transform=ax_right.transAxes,
                          fontsize=12, color="gray")
            # Fall through to the left panel — the raw trajectory plot
            # is still meaningful even if the post-REF panel cannot render.

        ax_left, ax_right = row_axes

        # Left panel: full trajectory
        ax_left.plot(tours, bkz_mean, color=COLORS["bkz"], linewidth=2,
                     label="BKZ", zorder=3)
        ax_left.fill_between(tours, bkz_mean - bkz_std, bkz_mean + bkz_std,
                             color=COLORS["bkz"], alpha=0.15)
        ax_left.plot(tours, sd_mean, color=COLORS["sdbkz"], linewidth=2,
                     label="SD-BKZ", zorder=4)
        ax_left.fill_between(tours, sd_mean - sd_std, sd_mean + sd_std,
                             color=COLORS["sdbkz"], alpha=0.15)
        ax_left.axvline(x=70, color="gray", linewidth=1, linestyle=":",
                        label="Standard tour limit (70)")
        ax_left.set_xlabel("Tour")
        ax_left.set_ylabel("d(LN) (nats)")
        ax_left.set_title(f"({panel_letters[0]}) {regime_text} — "
                          f"n={n_val}, $\\beta$={beta_val}, {n_seeds} seeds")
        ax_left.legend(fontsize=9, loc="upper right")

        # Right panel: improvement since REF_TOUR
        if n_tours <= ref_idx:
            return  # already rendered the no-data notice above
        bkz_improvement = bkz_mean[ref_idx] - bkz_mean
        sd_improvement = sd_mean[ref_idx] - sd_mean
        bkz_improvement_post = bkz_improvement[ref_idx:]
        sd_improvement_post = sd_improvement[ref_idx:]
        tours_post = np.arange(REF_TOUR, n_tours + 1)

        ax_right.plot(tours_post, bkz_improvement_post, color=COLORS["bkz"],
                      linewidth=2, label="BKZ improvement")
        ax_right.plot(tours_post, sd_improvement_post, color=COLORS["sdbkz"],
                      linewidth=2, label="SD-BKZ improvement")
        ax_right.axhline(y=0, color="red", linewidth=1, linestyle="--",
                         alpha=0.7)

        ax_right.set_xlabel("Tour")
        ax_right.set_ylabel("d(LN) improvement since tour 70 (nats)")
        ax_right.set_title(f"({panel_letters[1]}) Improvement after tour 70")
        ax_right.legend(fontsize=9, loc="upper left")

        # The stats text box (BKZ Δ / SD-BKZ Δ / advantages at tour 70 and
        # 500) was removed 2026-04-09 — whichever corner it landed in, it
        # covered either the SD-BKZ improvement curve or the early-tour
        # data. The numbers live in paper_findings.md and the stats tables.

    plot_row(axes[0], n90, ("a", "b"), "SD-BKZ keeps gaining")
    plot_row(axes[1], n140, ("c", "d"), "BKZ wins at convergence")

    fig.suptitle("Two convergence regimes at $\\beta$=30: SD-BKZ wins at "
                 "n=90, BKZ wins at n=140 — both at full 500-tour budget",
                 fontsize=14, y=1.00)
    fig.tight_layout()
    path = os.path.join(output_dir, "convergence_500_tours.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
