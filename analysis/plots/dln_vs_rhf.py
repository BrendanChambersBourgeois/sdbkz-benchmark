"""Figure 8: d(LN) reveals what RHF cannot see.

Two panels: z-score histograms of d(LN) vs RHF advantage at the n=100
β=30 peak (left), and per-group win rate comparison across β=30 (right).
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS


def fig_dln_vs_rhf(groups, output_dir=".", min_seeds=10):
    """Scatter plot proving d(LN) sees what RHF misses.

    For each seed, plot RHF advantage on x-axis and d(LN) advantage on y-axis.
    If RHF captured the same information, points would lie on a line. Instead,
    points form a vertical band — d(LN) shows clear separation while RHF stays
    near zero.

    Args:
        groups: Output of load_all_seeds().
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds per group to include.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Left panel: same 100 seeds, normalized z-scores so both metrics
    # share one x-axis. Same dataset, two metrics, very different stories.
    peak_seeds = groups.get((100, 30), [])
    peak_rhfs = [s.get("rhf_advantage") for s in peak_seeds
                 if s.get("rhf_advantage") is not None]
    peak_dlns = [s["advantage"] for s in peak_seeds
                 if s.get("rhf_advantage") is not None]

    if not peak_rhfs:
        print("  No RHF data at peak group (n=100, β=30)")
        plt.close(fig)
        return

    peak_rhfs = np.array(peak_rhfs)
    peak_dlns = np.array(peak_dlns)

    # Z-score: (value - 0) / std. "How many standard deviations from zero?"
    # This puts both metrics on a directly comparable scale.
    # Zero-std guard mirrors the pattern in analysis/tables.py:64 —
    # a constant-value sample (std == 0) would silently divide-by-zero.
    rhf_std = np.std(peak_rhfs, ddof=1)
    dln_std = np.std(peak_dlns, ddof=1)
    if rhf_std == 0 or dln_std == 0:
        print("  dln_vs_rhf: zero std in peak group — skipping z-score panel")
        plt.close(fig)
        return
    rhf_z = peak_rhfs / rhf_std
    dln_z = peak_dlns / dln_std

    bins = np.linspace(-3, 12, 60)
    ax1.hist(rhf_z, bins=bins, color=COLORS["bkz"], alpha=0.7,
             edgecolor="white", linewidth=0.5,
             label=f"RHF advantage (mean = {np.mean(rhf_z):+.2f}σ)")
    ax1.hist(dln_z, bins=bins, color=COLORS["sdbkz"], alpha=0.7,
             edgecolor="white", linewidth=0.5,
             label=f"d(LN) advantage (mean = {np.mean(dln_z):+.2f}σ)")
    ax1.axvline(x=0, color="red", linewidth=1.5, linestyle="--",
                label="Zero (no advantage)")

    ax1.set_xlabel(r"Advantage in standard deviations from zero ($\sigma$ units)")
    ax1.set_ylabel("Number of seeds")
    ax1.set_title(r"Same 100 seeds (n=100, $\beta$=30): two metrics, two stories")
    ax1.legend(loc="upper right", fontsize=9)

    rhf_win = np.mean(peak_rhfs > 0) * 100
    dln_win = np.mean(peak_dlns > 0) * 100
    ax1.text(0.97, 0.65,
             f"RHF win rate:   {rhf_win:.0f}%\n"
             f"d(LN) win rate: {dln_win:.0f}%",
             transform=ax1.transAxes, fontsize=9, ha="right", va="top",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85))

    # Right panel: per-group win rate comparison (RHF vs d(LN))
    group_data = []
    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds or beta != 30:
            continue
        rhfs = [s.get("rhf_advantage") for s in seeds if s.get("rhf_advantage") is not None]
        dlns = [s["advantage"] for s in seeds]
        if not rhfs:
            continue
        rhf_win = np.mean(np.array(rhfs) > 0) * 100
        dln_win = np.mean(np.array(dlns) > 0) * 100
        group_data.append((n, rhf_win, dln_win))

    if group_data:
        ns = np.array([g[0] for g in group_data])
        rhf_wins = np.array([g[1] for g in group_data])
        dln_wins = np.array([g[2] for g in group_data])

        ax2.plot(ns, dln_wins, marker="o", linewidth=2, markersize=7,
                 color=COLORS["sdbkz"], label="d(LN) win rate")
        ax2.plot(ns, rhf_wins, marker="s", linewidth=2, markersize=7,
                 color=COLORS["bkz"], label="RHF win rate")
        ax2.axhline(y=50, color="gray", linewidth=0.8, linestyle=":",
                    label="Coin flip (50%)")
        ax2.set_xlabel("Secret dimension n")
        ax2.set_ylabel("SD-BKZ win rate (%)")
        ax2.set_title(r"$\beta$=30: RHF blind to SD-BKZ advantage")
        ax2.set_ylim(-5, 105)
        ax2.legend(loc="lower left", fontsize=9, framealpha=0.9)

    fig.suptitle("d(LN) reveals what RHF cannot see", fontsize=14, y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "dln_vs_rhf.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")
