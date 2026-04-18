"""Figure 13: q=3329 fplll Gram-Schmidt cancellation.

Three panels: q=97 reference distribution at the n=100 β=30 peak, the
q=3329 distribution showing the bimodal clean/degenerate failure mode
(100 seeds: 10 cloud + 45 primary + 45 secondary machine), and an
example per-tour trajectory of one degenerate seed.
"""
import os

import numpy as np
import matplotlib.pyplot as plt

from .._data import load_all_seeds
from .._style import COLORS


def fig_q3329_degeneracy(groups, output_dir="."):
    """Three-panel figure showing the q=3329 fplll cancellation.

    (a) q=97 distribution at n=100 β=30: 100 seeds, tight cluster
    (b) q=3329 distribution at n=100 β=30: 100 seeds, bimodal failure
    (c) Per-tour d(LN) trajectory for one degenerate seed showing the spike

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

    # q=3329: v1.3 manifest query for the n=100 β=30 p=1000 mt=70
    # campaign (paper §8 headline 100-seed dataset, 10 AWS-Batch +
    # 45 Intel 13900K + 45 AMD 9950X3D). Dedup by (n, β, seed) with
    # non-cloud preference mirrors the legacy raw/cloud-first globber
    # behaviour; fat companions skipped by default.
    q3329_groups = load_all_seeds(
        campaign="q3329", n=100, beta=30, q=3329,
        precision=1000, max_tours=70,
    )
    q3329_seeds = q3329_groups.get((100, 30), [])
    if not q3329_seeds:
        print("  No q=3329 n=100 β=30 data available")
        return

    # Degeneracy detection threshold. A clamp from get_r returning ≤ 0
    # substitutes 1e-300, giving log(1e-300) ≈ −690 nats. Clean seeds
    # stay within a few nats of zero across all positions. −100 nats is
    # well below any legitimate value and well above any clamped one, so
    # the threshold is not sensitive to the exact magnitude.
    # A more robust alternative is to read results/clamp_events.jsonl,
    # the side log emitted by scripts/sweep_parallel.py's _log_clamp
    # helper whenever get_r returns a non-positive value.
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
              "win rate: 100%\n0% degenerate",
              transform=ax_a.transAxes, fontsize=9, ha="right", va="top",
              family="monospace",
              bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))

    # Panel (b) — q=3329 distribution showing bimodal failure
    clean = [d["advantage"] for d in q3329_data if not d["is_degen"]]
    degen = [d["advantage"] for d in q3329_data if d["is_degen"]]
    n_total = len(q3329_data)
    n_degen = len(degen)

    if degen:
        bins = np.linspace(min(min(degen), -10) - 5, max(max(degen), 10) + 5, 25)
    else:
        bins = np.linspace(-2, 2, 20)

    ax_b.hist(clean, bins=bins, color=COLORS["sdbkz"], alpha=0.75,
              edgecolor="white", linewidth=0.5,
              label=f"recovered ({len(clean)})")
    ax_b.hist(degen, bins=bins, color="#dc2626", alpha=0.75,
              edgecolor="white", linewidth=0.5,
              label=f"degenerate ({len(degen)})")
    ax_b.axvline(0, color="red", linewidth=1.2, linestyle="--", alpha=0.8)
    ax_b.set_xlabel("SD-BKZ advantage (nats)")
    ax_b.set_ylabel("Count")
    ax_b.set_title(f"(b) q=3329, n=100, $\\beta$=30 ({n_total} seeds, "
                   f"1000-bit MPFR)")
    ax_b.legend(fontsize=9, loc="upper left")

    if clean:
        clean_mean = np.mean(clean)
        clean_win = sum(1 for a in clean if a > 0)
        ax_b.text(0.97, 0.95,
                  f"recovered mean: {clean_mean:+.3f}\n"
                  f"recovered win:  {clean_win}/{len(clean)}\n"
                  f"degenerate:     {n_degen}/{n_total} ({n_degen/n_total*100:.0f}%)",
                  transform=ax_b.transAxes, fontsize=9, ha="right", va="top",
                  family="monospace",
                  bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))

    # Panel (c) — per-tour trajectory of one degenerate seed
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
            ax_c.set_title(f"(c) Per-tour trajectory of a degenerate seed "
                           f"(seed {best['seed']}): "
                           f"d(LN) spikes when one Gram-Schmidt vector "
                           f"collapses to numerical zero")
            ax_c.legend(fontsize=9, loc="upper left")

    fig.suptitle("fplll Gram-Schmidt cancellation at q=3329: a numerical "
                 "instability absent from q=97",
                 fontsize=14, y=0.995)
    path = os.path.join(output_dir, "q3329_degeneracy.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
