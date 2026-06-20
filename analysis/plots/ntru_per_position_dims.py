"""Paper 2, figure: per-position SD-BKZ redistribution across dimensions.

Generalises the n=89 per-position figure (fig:perpos) to n=89/101/113: the
head-down / tail-up redistribution of the GS profile that SD-BKZ induces is not
specific to one dimension. Each panel is one n at a representative pre-onset
modulus; both engines (fplll enumeration solid, G6K sieve dashed) overlaid, mean
over seeds of log||b*_i||_SD - log||b*_i||_BKZ per position. The i=n block split
(q-vector / dual block boundary) is marked.

Reads gs_lognorms_{bkz,sdbkz} from the per-seed JSONs directly. No RNG.
"""
import glob
import json
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

# n -> representative q (in each n's redistribution band) with both-engine β=40
# coverage. The band shifts up with n, so q rises with n; below it the profile
# is flat (pre-onset), so a fixed q would wrongly show "no effect" at large n.
CELLS = {89: 137, 101: 241, 113: 439}
BETA = 40
ENGINES = [("fplll", "ntru", "-"), ("G6K", "ntru_g6k", "--")]
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mean_diff(tree, n, q):
    pat = os.path.join(_REPO, "results", "seeds", tree, f"q{q}", "p*_mt*",
                       f"n{n:03d}_beta{BETA:02d}", "seed*.json")
    diffs = []
    for p in glob.glob(pat):
        if "_fat" in p:
            continue
        d = json.load(open(p))
        b, s = d.get("gs_lognorms_bkz"), d.get("gs_lognorms_sdbkz")
        if b and s and len(b) == len(s):
            diffs.append(np.asarray(s, float) - np.asarray(b, float))
    if not diffs:
        return None, 0
    return np.mean(np.vstack(diffs), axis=0), len(diffs)


def fig_ntru_per_position_dims(output_dir=".", fname="per_position_dims.png"):
    """Per-position SD-BKZ redistribution at n=89/101/113, both engines."""
    sd_c = COLORS["sdbkz"]
    ns = sorted(CELLS)
    fig, axes = plt.subplots(1, len(ns), figsize=(12, 4.4), sharey=True)

    for ax, n in zip(axes, ns, strict=True):
        q = CELLS[n]
        for label, tree, ls in ENGINES:
            md, nseed = _mean_diff(tree, n, q)
            if md is None:
                continue
            ax.plot(np.arange(len(md)), md, color=sd_c, ls=ls, lw=1.6,
                    label=f"{label} ($N={nseed}$)", zorder=3)
        ax.axhline(0.0, color="#dc2626", lw=0.9, ls="--", alpha=0.6)
        ax.axvline(n, color="#334155", lw=1.0, ls=":", alpha=0.7)
        ax.annotate(f"$i={n}$", xy=(n, 0), xytext=(n + 2, ax.get_ylim()[0]),
                    fontsize=8, color="#334155", va="bottom")
        ax.set_title(f"$n={n}$, $q={q}$")
        ax.set_xlabel("GS position $i$")
        ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    axes[0].set_ylabel(
        r"$\log\|\mathbf{b}_i^\ast\|_{\mathrm{SD}}-\log\|\mathbf{b}_i^\ast\|_{\mathrm{BKZ}}$"
        "\n(negative $\\Rightarrow$ SD-BKZ shorter)")
    fig.suptitle(r"Per-position SD-BKZ redistribution across $n$ ($\beta=40$): "
                 r"head-down / tail-up scales with dimension, both engines", y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
