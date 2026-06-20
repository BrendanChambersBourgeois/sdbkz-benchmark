"""Paper 2, figure: SD-BKZ convergence efficiency vs BKZ, faceted by n.

Per-tour mean d(LN) (distance to the Li--Nguyen fixed point) for BKZ and SD-BKZ
on overstretched NTRU, one panel per dimension. The reported observable is the
*crossover tour*: the tour at which SD-BKZ's running d(LN) first drops below
BKZ's CONVERGED (final) d(LN) -- i.e. how many tours SD-BKZ needs to reach the
quality BKZ only reaches at the end of its whole run. SD-BKZ hits BKZ's endpoint
roughly halfway through its own run and then keeps improving, and the
tours-to-match grows with n (≈tour 9 at n=89 → ≈25 at n=113).

This matches the `crossover_tour` field exactly (_bkz_core.py: first tour with
sdbkz_dln < bkz_final_dln); here it is recomputed from the per-cell MEAN curves
so the marker lines up with the plotted trajectories.

§7 note: the per-engine curves are d(LN) DISTANCES (paper 1's convergence
metric) and the reported result is the crossover TOUR measured against BKZ's own
final value -- a timing/efficiency observable, not the signed d(LN) advantage
(whose magnitude is not a reported result outside the n≈71--73 spike). The
quantitative DSD result is the rate-based onset (onset sigmoids / fatigue figs).

β=20, fplll, at a representative overstretched q per n (N=100 seeds/cell). Reads
bkz_dln_per_tour / sdbkz_dln_per_tour from the per-seed JSONs. No RNG.
"""
import glob
import json
import os

import matplotlib.pyplot as plt
import numpy as np

from .._style import COLORS

# n -> representative overstretched q (β=20, fplll, well-populated cell)
CELLS = {89: 307, 101: 409, 113: 719}
BETA = 20
TREE = "ntru"
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cell(n, q):
    """Mean per-tour d(LN) for both variants (truncated to common length)."""
    pat = os.path.join(_REPO, "results", "seeds", TREE, f"q{q}", "p*_mt*",
                       f"n{n:03d}_beta{BETA:02d}", "seed*.json")
    bkz, sd = [], []
    for f in sorted(glob.glob(pat)):
        d = json.load(open(f))
        b, s = d.get("bkz_dln_per_tour"), d.get("sdbkz_dln_per_tour")
        if b and s:
            bkz.append(b)
            sd.append(s)
    if not bkz:
        return None
    length = min(min(len(x) for x in bkz), min(len(x) for x in sd))
    bm = np.mean([x[:length] for x in bkz], axis=0)
    sm = np.mean([x[:length] for x in sd], axis=0)
    return bm, sm, len(bkz)


def fig_ntru_crossover_dynamics(output_dir=".", fname="crossover_dynamics.png"):
    """Per-tour d(LN); SD-BKZ reaching BKZ's converged value marked, faceted n."""
    sd_c, bkz_c = COLORS["sdbkz"], COLORS["bkz"]
    ns = sorted(CELLS)
    fig, axes = plt.subplots(1, len(ns), figsize=(12, 4.4), sharey=False)

    for ax, n in zip(axes, ns, strict=True):
        res = _cell(n, CELLS[n])
        if res is None:
            ax.axis("off")
            continue
        bm, sm, nseed = res
        tours = np.arange(1, len(bm) + 1)
        bkz_final = float(bm[-1])
        # tour where the mean SD curve first reaches BKZ's converged d(LN)
        below = np.where(sm < bkz_final)[0]
        xover = int(below[0] + 1) if below.size else None

        ax.plot(tours, bm, color=bkz_c, lw=1.8, marker="s", markersize=3,
                label="BKZ", zorder=3)
        ax.plot(tours, sm, color=sd_c, lw=1.8, marker="o", markersize=3,
                label="SD-BKZ", zorder=3)
        ax.axhline(bkz_final, color=bkz_c, lw=1.0, ls="--", alpha=0.55, zorder=1)
        ax.annotate("BKZ converged", xy=(tours[-1], bkz_final),
                    xytext=(tours[-1], bkz_final + (bm[0] - bm[-1]) * 0.06),
                    fontsize=7.5, color=bkz_c, ha="right", va="bottom")
        if xover is not None:
            ax.axvline(xover, color="#334155", lw=1.1, ls=":", alpha=0.8,
                       zorder=2)
            ax.plot([xover], [bkz_final], marker="o", color="#334155",
                    markersize=6, zorder=4)
            ax.annotate(f"SD matches BKZ-final\n@ tour {xover} of {len(bm)}",
                        xy=(xover, bkz_final),
                        xytext=(xover + len(bm) * 0.04, bm[0] - (bm[0] - bm[-1]) * 0.18),
                        fontsize=8, color="#334155", va="top")
        ax.set_title(f"$n={n}$, $q={CELLS[n]}$ ($N={nseed}$)")
        ax.set_xlabel("BKZ tour")
        ax.grid(alpha=0.15, zorder=0)

    axes[0].set_ylabel(r"mean $d(\mathrm{LN})$ (distance to fixed point), nats")
    axes[0].legend(loc="upper right", framealpha=0.9, fontsize=9)
    fig.suptitle(r"NTRU convergence efficiency ($\beta=20$, fplll): SD-BKZ reaches "
                 r"BKZ's converged $d(\mathrm{LN})$ partway through, then surpasses it",
                 y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
