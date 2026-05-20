"""Figure: Head/mid/tail spatial decomposition of the SD-BKZ improvement.

Three vertically stacked subplots (one per β ∈ {20, 30, 40}) showing the
mean d(LN) improvement in absolute nats for each third of the Rankin profile
(head / middle / tail) as grouped bars across the secret dimension n.

Positive values mean SD-BKZ is closer to the Li-Nguyen fixed point in that
region; negative values mean BKZ is closer. The absolute-nats formulation
(as opposed to the earlier stacked-percentage version) honestly shows
sign-flipped tails dangling below zero.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._data import _decompose_seed
from .._style import COLORS

BETAS = [20, 30, 40]


def fig_spatial_decomposition(groups, output_dir=".", min_seeds=10):
    """Grouped bar chart: head/mid/tail nats improvement vs n, faceted by β.

    Args:
        groups: Output of load_all_seeds(), dict keyed by (n, beta).
        output_dir: Where to save the PNG.
        min_seeds: Minimum seeds to include a group.
    """
    # Collect per-(n, beta) means in absolute nats.
    by_beta = {b: [] for b in BETAS}
    for (n, beta), seeds in sorted(groups.items()):
        if beta not in by_beta:
            continue
        if len(seeds) < min_seeds:
            continue
        heads, mids, tails = [], [], []
        for s in seeds:
            decomp = _decompose_seed(s)
            if decomp is None:
                continue
            heads.append(decomp[0])
            mids.append(decomp[1])
            tails.append(decomp[2])
        if not heads:
            continue
        by_beta[beta].append({
            "n": n,
            "head": float(np.mean(heads)),
            "mid":  float(np.mean(mids)),
            "tail": float(np.mean(tails)),
            "seeds": len(heads),
        })

    if not any(by_beta.values()):
        print("  No groups with Rankin profile data for decomposition")
        return

    fig, axes = plt.subplots(
        nrows=3, ncols=1, figsize=(9, 9.5), sharex=False
    )

    bar_width = 0.26

    legend_handles = None
    for ax, beta in zip(axes, BETAS, strict=False):
        rows = by_beta[beta]
        ax.set_title(f"β = {beta}", loc="left", fontsize=12)
        ax.axhline(y=0, color="#475569", linewidth=0.8, linestyle="-", alpha=0.7)
        ax.grid(True, axis="y", alpha=0.3, linewidth=0.5)
        ax.set_axisbelow(True)

        if not rows:
            ax.text(0.5, 0.5, "(no data)", ha="center", va="center",
                    transform=ax.transAxes, color="#94a3b8")
            ax.set_xticks([])
            continue

        ns = [r["n"] for r in rows]
        xs = np.arange(len(ns))
        heads = [r["head"] for r in rows]
        mids  = [r["mid"]  for r in rows]
        tails = [r["tail"] for r in rows]
        seeds = [r["seeds"] for r in rows]

        h_bars = ax.bar(xs - bar_width, heads, bar_width,
                        color=COLORS["head"], alpha=0.85,
                        label="Head (first third)")
        m_bars = ax.bar(xs, mids, bar_width,
                        color=COLORS["mid"], alpha=0.85,
                        label="Middle (second third)")
        t_bars = ax.bar(xs + bar_width, tails, bar_width,
                        color=COLORS["tail"], alpha=0.85,
                        label="Tail (last third)")

        if legend_handles is None:
            legend_handles = [h_bars, m_bars, t_bars]

        ax.set_xticks(xs)
        ax.set_xticklabels([str(n) for n in ns])

        # Pad the y-limits a bit above/below the data so annotations and
        # the zero line stay readable.
        all_vals = heads + mids + tails
        vmin = min(all_vals + [0.0])
        vmax = max(all_vals + [0.0])
        span = max(vmax - vmin, 1e-9)
        pad = 0.18 * span
        ax.set_ylim(vmin - pad, vmax + pad)

        # Seed-count annotation for under-filled groups, matching the
        # {c}s convention used in dimension_scaling.py. Place above the
        # tallest of the three bars at each n (or above 0 if all negative).
        for i, (n, c) in enumerate(zip(ns, seeds, strict=False)):
            if c >= 100:
                continue
            top = max(heads[i], mids[i], tails[i], 0.0)
            ax.annotate(f"{c}s", (xs[i], top), fontsize=7,
                        color="#334155", ha="center",
                        textcoords="offset points", xytext=(0, 4))

    axes[-1].set_xlabel("Secret dimension n")

    # Shared y-label across all three subplots — avoids per-axis labels
    # colliding with adjacent subplot titles on the left edge.
    fig.supylabel("Mean d(LN) improvement (nats)", fontsize=11)

    if legend_handles is not None:
        fig.legend(handles=legend_handles,
                   loc="upper center", ncol=3,
                   bbox_to_anchor=(0.5, 0.965),
                   frameon=False, fontsize=10)

    fig.suptitle("Where in the Rankin profile does SD-BKZ improve?",
                 fontsize=13, y=0.995)

    fig.tight_layout(rect=[0.03, 0, 1, 0.93])
    path = os.path.join(output_dir, "spatial_decomposition.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
