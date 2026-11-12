"""Figure 12: q=3329, n=100, β=30 as first published.

Three panels: the q=97 reference distribution at n=100 β=30, the q=3329
distribution (100 seeds) split by whether the double-precision
measurement GSO hit its floor, and the per-tour trajectory of one
floored seed. The floors are a property of the double measurement, not
of the reduction; measured at 1000 bits all 100 seeds are clean.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._data import load_all_seeds
from .._style import COLORS


def fig_q3329_degeneracy(groups, output_dir="."):
    """Three-panel figure of the q=3329 data as measured in double.

    (a) q=97 distribution at n=100 β=30
    (b) q=3329 distribution at n=100 β=30: 100 seeds, by measurement floor
    (c) Per-tour d(LN) trajectory of one floored seed

    Args:
        groups: Output of load_all_seeds() (used for q=97 group only).
        output_dir: Where to save the PNG.
    """
    # q=97 reference: load from groups
    q97_seeds = groups.get((100, 30), [])
    if not q97_seeds:
        print("  No q=97 n=100 β=30 data available")
        return
    q97_advs = np.array([s["advantage"] for s in q97_seeds])

    # q=3329: manifest query for the n=100 β=30 p=1000 mt=70 cell.
    # Dedup by (n, β, seed) with non-cloud preference; fat companions
    # skipped by default.
    q3329_groups = load_all_seeds(
        campaign="q3329", n=100, beta=30, q=3329,
        precision=1000, max_tours=70,
    )
    # The paper's cell is seeds 1-100. The manifest cell also holds
    # seed 101, a later single-seed probe that is not part of it.
    q3329_seeds = [s for s in q3329_groups.get((100, 30), [])
                   if 1 <= s["seed"] <= 100]
    if not q3329_seeds:
        print("  No q=3329 n=100 β=30 data available")
        return

    # Measurement-floor threshold. When the double-precision measurement
    # GSO returns r_ii ≤ 0 the stored log-norm is the floor −345.388.
    # Unfloored log-norms stay within a few nats of zero, so −100 nats
    # separates the two and is not sensitive to the exact magnitude.
    DEGENERACY_THRESHOLD_LN = -100.0

    q3329_data = []
    for d in q3329_seeds:
        sd_min = min(d["gs_lognorms_sdbkz"])
        bkz_min = min(d["gs_lognorms_bkz"])
        is_degen = (sd_min < DEGENERACY_THRESHOLD_LN
                    or bkz_min < DEGENERACY_THRESHOLD_LN)
        q3329_data.append({
            "seed": d["seed"],
            "advantage": d["advantage"],
            "is_degen": is_degen,
            "bkz_traj": d["bkz_dln_per_tour"],
            "sd_traj": d["sdbkz_dln_per_tour"],
        })

    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], hspace=0.35, wspace=0.25)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, :])

    # Panel (a) — q=97 reference distribution
    ax_a.hist(q97_advs, bins=20, color=COLORS["sdbkz"], alpha=0.75,
              edgecolor="white", linewidth=0.5)
    ax_a.axvline(0, color="red", linewidth=1.2, linestyle="--", alpha=0.8)
    ax_a.axvline(np.mean(q97_advs), color="black", linewidth=1.5,
                 label=f"mean = {np.mean(q97_advs):+.3f}")
    ax_a.set_xlabel("SD-BKZ advantage (nats)")
    ax_a.set_ylabel("Count")
    ax_a.set_title(f"(a) q=97, n=100, $\\beta$=30 ({len(q97_advs)} seeds)")
    ax_a.legend(fontsize=9, loc="upper left")
    ax_a.text(0.97, 0.95,
              "win rate: 100%",
              transform=ax_a.transAxes, fontsize=9, ha="right", va="top",
              family="monospace",
              bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))

    # Panel (b) — q=3329 distribution, split by measurement floor
    clean = [d["advantage"] for d in q3329_data if not d["is_degen"]]
    degen = [d["advantage"] for d in q3329_data if d["is_degen"]]
    n_total = len(q3329_data)

    if degen:
        bins = np.linspace(min(min(degen), -10) - 5, max(max(degen), 10) + 5, 25)
    else:
        bins = np.linspace(-2, 2, 20)

    ax_b.hist(clean, bins=bins, color=COLORS["sdbkz"], alpha=0.75,
              edgecolor="white", linewidth=0.5,
              label=f"no measurement floor ({len(clean)})")
    ax_b.hist(degen, bins=bins, color="#dc2626", alpha=0.75,
              edgecolor="white", linewidth=0.5,
              label=f"measurement floor ({len(degen)})")
    ax_b.axvline(0, color="red", linewidth=1.2, linestyle="--", alpha=0.8)
    ax_b.set_xlabel("SD-BKZ advantage (nats)")
    ax_b.set_ylabel("Count")
    ax_b.set_title(f"(b) q=3329, n=100, $\\beta$=30 ({n_total} seeds, "
                   f"measured in double)")
    ax_b.legend(fontsize=9, loc="upper left")

    # Panel (c) — per-tour trajectory of one floored seed
    if q3329_data:
        degen_seeds = [d for d in q3329_data if d["is_degen"]]
        if degen_seeds:
            best = max(degen_seeds,
                       key=lambda d: max(max(d["bkz_traj"]), max(d["sd_traj"])))
            tours = np.arange(1, len(best["bkz_traj"]) + 1)
            ax_c.plot(tours, best["bkz_traj"], color=COLORS["bkz"],
                      linewidth=1.8, label="BKZ")
            ax_c.plot(tours, best["sd_traj"], color=COLORS["sdbkz"],
                      linewidth=1.8, label="SD-BKZ")
            ax_c.axhline(20, color="gray", linewidth=0.8, linestyle=":",
                         alpha=0.7, label="Spike threshold (20 nats)")
            ax_c.set_xlabel("Tour")
            ax_c.set_ylabel("d(LN) (nats)")
            ax_c.set_title(f"(c) Per-tour d(LN) of a floored seed "
                           f"(seed {best['seed']}), measured in double")
            ax_c.legend(fontsize=9, loc="upper left")

    fig.suptitle("q=3329, n=100, $\\beta$=30 as first published "
                 "(double-precision measurement)",
                 fontsize=14, y=0.995)
    path = os.path.join(output_dir, "q3329_degeneracy.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
