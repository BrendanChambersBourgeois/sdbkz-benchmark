"""Paper 2, figure: per-key paired exact recovery, BKZ vs SD-BKZ (sec:fatigue).

For each key (seed id) of a beta=20 fplll ladder, the number of q cells in
which each variant recovers the exact key (secret_exact_match, ntru_exact
tree). A key runs both variants on the same cells, so points above the
diagonal are keys SD-BKZ recovers in more cells. Marker area is the number of
keys at that point.
"""
import glob
import json
import os
from collections import Counter, defaultdict

import matplotlib.pyplot as plt

from .._style import COLORS

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NS = [89, 101, 113]
BETA = 20


def per_key(n):
    """{seed: [sd_cells, bkz_cells]} over the n ladder."""
    out = defaultdict(lambda: [0, 0])
    pat = os.path.join(_REPO, "results", "seeds", "ntru_exact", "q*", "p*_mt50",
                       f"n{n:03d}_beta{BETA:02d}", "seed*.json")
    # One cell per (q, seed): a seed rerun at a higher precision replaces the lower one.
    best = {}
    for f in glob.glob(pat):
        q_dir, p_dir = f.split(os.sep)[-4:-2]
        prec = int(p_dir[1:].split("_")[0])
        with open(f) as fh:
            d = json.load(fh)
        key = (q_dir, d["seed"])
        if key not in best or prec > best[key][0]:
            best[key] = (prec, d)
    for (_, seed), (_, d) in best.items():
        out[seed][0] += bool(d["secret_exact_match_sdbkz"])
        out[seed][1] += bool(d["secret_exact_match_bkz"])
    return out


def fig_ntru_paired_keys(output_dir=".", fname="paired_keys.png"):
    fig, axes = plt.subplots(1, len(NS), figsize=(12, 4.3))
    for ax, n in zip(axes, NS, strict=True):
        keys = per_key(n)
        pts = Counter((b, s) for s, b in keys.values())
        hi = max(max(p) for p in pts) + 1
        ax.plot([0, hi], [0, hi], color=COLORS["zero"], lw=1.0, ls="--", alpha=0.7,
                zorder=1)
        ax.scatter([p[0] for p in pts], [p[1] for p in pts],
                   s=[18 * c for c in pts.values()], color=COLORS["sdbkz"],
                   alpha=0.75, edgecolor="black", linewidth=0.4, zorder=3)
        up = sum(s > b for s, b in keys.values())
        dn = sum(s < b for s, b in keys.values())
        ax.set_title(f"$n={n}$: SD-BKZ ahead {up}, BKZ ahead {dn}")
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.set_xlabel("cells recovered by BKZ")
        ax.set_xlim(-0.5, hi)
        ax.set_ylim(-0.5, hi)
        ax.set_aspect("equal")
        ax.grid(alpha=0.15, zorder=0)
    axes[0].set_ylabel("cells recovered by SD-BKZ")

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
