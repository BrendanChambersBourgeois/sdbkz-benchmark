"""Paper 2, figure: per-seed advantage distributions vs n (violins).

The dimension-onset figure shows the MEAN advantage; this shows the full per-seed
DISTRIBUTION at each n, making the two-mode onset zone (n=71--73: a win cluster +
a loss cluster, not Gaussian scatter) explicit and showing the tight plateau for
n>=79. Same data and scope as Figure fig:dimonset (q=97, β=20 dimension sweep,
the reference-robust spike region), so the signed advantage is shown here on the
same footing the dimension transition already uses.

Reads the per-seed `advantage` field of the ntru campaign (q=97). No RNG.
"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

BETA = 20
MIN_SEEDS = 10
BIMODAL = {71, 73}


def fig_ntru_advantage_violins(groups, output_dir=".", fname="advantage_violins.png"):
    """Per-seed advantage violins vs n (q=97, β=20)."""
    rows = []
    for (n, b), seeds in sorted(groups.items()):
        if b != BETA or len(seeds) < MIN_SEEDS:
            continue
        advs = np.array([s["advantage"] for s in seeds], dtype=float)
        rows.append((n, advs))
    if not rows:
        raise ValueError(f"no ntru β={BETA} groups with >= {MIN_SEEDS} seeds")

    ns = [r[0] for r in rows]
    data = [r[1] for r in rows]
    sd_c, zero_c = COLORS["sdbkz"], COLORS["zero"]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.axhline(0.0, color=zero_c, lw=1.0, ls="--", alpha=0.7, zorder=1)
    parts = ax.violinplot(data, positions=ns, widths=3.0, showmeans=True,
                          showextrema=False)
    for i, body in enumerate(parts["bodies"]):
        body.set_facecolor(sd_c if ns[i] not in BIMODAL else "#b45309")
        body.set_alpha(0.55)
        body.set_edgecolor("#334155")
    parts["cmeans"].set_color("#334155")
    parts["cmeans"].set_linewidth(1.3)

    # per-seed jitter for the small/bimodal cells so the two modes are visible
    for n, advs in rows:
        if n in BIMODAL:
            xs = n + np.linspace(-1.0, 1.0, len(advs))
            ax.scatter(xs, np.sort(advs), s=10, color="#7c2d12", alpha=0.6,
                       edgecolors="none", zorder=4)
            nwin = int((advs > 0).sum())
            ax.annotate(f"{nwin}/{len(advs)} win", xy=(n, advs.max() + 0.6),
                        ha="center", fontsize=8, color="#7c2d12")

    ax.set_xlabel("NTRU parameter $n$")
    ax.set_ylabel(r"per-seed $d(\mathrm{LN})$ advantage (BKZ $-$ SD-BKZ), nats")
    ax.set_title(r"NTRU per-seed advantage distribution vs $n$ ($q=97$, "
                 r"$\beta=20$): two-mode onset at $n=71$--$73$, tight plateau after")
    ax.set_xticks(ns)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
