"""Paper 2, figure: SD-BKZ convergence efficiency vs BKZ, faceted by n.

Per-tour mean d(LN) (distance to the Li--Nguyen fixed point) for BKZ and SD-BKZ
on overstretched NTRU, one panel per dimension. The reported observable is the
*per-seed crossover tour*: the first tour at which a seed's SD-BKZ d(LN) drops
below the SAME seed's BKZ final d(LN) (the stored `crossover_tour` field,
_bkz_core.py: first tour with sdbkz_dln < bkz_final_dln). The panel reports its
median and interquartile range over seeds, plus how many seeds cross at all
(a seed whose SD-BKZ never gets below its BKZ final value is right-censored and
counted as never crossing, i.e. +inf for the median).

Measured on the committed cells (N=100 each): median crossover tour 19 (n=89),
27 (n=101), 26 (n=113); 98/100, 100/100 and 99/100 seeds cross. The
tours-to-match is NOT monotone in n.

Curves: runs stop at different tours (BKZ stagnation, or the 50-tour cap), so
each seed's trajectory is carried forward at its own final value up to the
longest run before averaging. A stopped run's last value is its converged value,
so the carried-forward mean at the last tour equals the mean of the per-seed
final values exactly. (The previous version truncated every seed to the
shortest run in the cell, which at n=89 read "BKZ converged" at tour 18, where
no BKZ run had terminated: 59.73 plotted vs 47.26 true mean.)

§7 note: the per-engine curves are d(LN) DISTANCES (paper 1's convergence
metric) and the reported result is the crossover TOUR measured against BKZ's own
final value -- a timing/efficiency observable, not the signed d(LN) advantage
(whose magnitude is not a reported result outside the n≈71--73 spike). The
quantitative DSD result is the rate-based onset (onset sigmoids / fatigue figs).

β=20, fplll, at a representative overstretched q per n (N=100 seeds/cell). Reads
bkz_dln_per_tour / sdbkz_dln_per_tour / bkz_final_dln / crossover_tour from the
per-seed JSONs. No RNG.
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


def _carry_forward(traj, length):
    """Pad a per-tour trajectory to `length` with its own final value."""
    return list(traj) + [traj[-1]] * (length - len(traj))


def _cell(n, q):
    """Per-cell summary: carried-forward mean curves plus per-seed crossover.

    Returns None when the cell has no usable seeds, else a dict with
    bkz_mean, sd_mean (arrays of the longest run length), bkz_final (mean of
    per-seed final BKZ d(LN)), xover (array of per-seed crossover tours,
    +inf where the seed never crosses) and n_seeds.
    """
    pat = os.path.join(_REPO, "results", "seeds", TREE, f"q{q}", "p*_mt*",
                       f"n{n:03d}_beta{BETA:02d}", "seed*.json")
    bkz, sd, finals, xover = [], [], [], []
    for f in sorted(glob.glob(pat)):
        with open(f) as fh:
            d = json.load(fh)
        b, s = d.get("bkz_dln_per_tour"), d.get("sdbkz_dln_per_tour")
        if not (b and s):
            continue
        bkz.append(b)
        sd.append(s)
        finals.append(float(d.get("bkz_final_dln", b[-1])))
        x = d.get("crossover_tour")
        xover.append(np.inf if x is None else float(x))
    if not bkz:
        return None
    length = max(max(len(x) for x in bkz), max(len(x) for x in sd))
    bm = np.mean([_carry_forward(x, length) for x in bkz], axis=0)
    sm = np.mean([_carry_forward(x, length) for x in sd], axis=0)
    return {"bkz_mean": bm, "sd_mean": sm, "bkz_final": float(np.mean(finals)),
            "xover": np.array(xover), "n_seeds": len(bkz)}


def crossover_summary(xover):
    """Median, quartiles and crossed count of per-seed crossover tours.

    Censored seeds are +inf, so they sort last and the median stays defined
    while fewer than half the seeds are censored (None otherwise).
    """
    n_total = int(xover.size)
    n_crossed = int(np.isfinite(xover).sum())
    if n_total == 0 or n_crossed * 2 <= n_total:
        return {"median": None, "q25": None, "q75": None,
                "n_crossed": n_crossed, "n_total": n_total}
    q25, med, q75 = np.percentile(xover, [25, 50, 75], method="lower")
    return {"median": float(med), "q25": float(q25),
            "q75": float(q75) if np.isfinite(q75) else None,
            "n_crossed": n_crossed, "n_total": n_total}


def fig_ntru_crossover_dynamics(output_dir=".", fname="crossover_dynamics.png"):
    """Per-tour d(LN); median per-seed crossover tour marked, faceted by n."""
    sd_c, bkz_c = COLORS["sdbkz"], COLORS["bkz"]
    ns = sorted(CELLS)
    fig, axes = plt.subplots(1, len(ns), figsize=(12, 4.4), sharey=False)

    for ax, n in zip(axes, ns, strict=True):
        res = _cell(n, CELLS[n])
        if res is None:
            ax.axis("off")
            continue
        bm, sm = res["bkz_mean"], res["sd_mean"]
        tours = np.arange(1, len(bm) + 1)
        bkz_final = res["bkz_final"]
        summ = crossover_summary(res["xover"])

        ax.plot(tours, bm, color=bkz_c, lw=1.8, marker="s", markersize=3,
                label="BKZ", zorder=3)
        ax.plot(tours, sm, color=sd_c, lw=1.8, marker="o", markersize=3,
                label="SD-BKZ", zorder=3)
        ax.axhline(bkz_final, color=bkz_c, lw=1.0, ls="--", alpha=0.55, zorder=1)
        # label at the left end: the curves are far above the line there
        ax.annotate("BKZ final (mean over seeds)", xy=(tours[0], bkz_final),
                    xytext=(tours[0], bkz_final + (bm[0] - bkz_final) * 0.03),
                    fontsize=7.5, color=bkz_c, ha="left", va="bottom")
        if summ["median"] is not None:
            med = summ["median"]
            if summ["q75"] is not None:
                ax.axvspan(summ["q25"], summ["q75"], color="#334155",
                           alpha=0.10, lw=0, zorder=0)
            ax.axvline(med, color="#334155", lw=1.1, ls=":", alpha=0.8, zorder=2)
            ax.plot([med], [bkz_final], marker="o", color="#334155",
                    markersize=6, zorder=4)
            iqr = (f"IQR {summ['q25']:.0f}–{summ['q75']:.0f}"
                   if summ["q75"] is not None else "IQR open")
            ax.annotate(f"per-seed crossover\nmedian tour {med:.0f} ({iqr})\n"
                        f"crossed {summ['n_crossed']}/{summ['n_total']}",
                        xy=(med, bkz_final),
                        xytext=(med + len(bm) * 0.04,
                                bm[0] - (bm[0] - bkz_final) * 0.18),
                        fontsize=8, color="#334155", va="top")
        ax.set_title(f"$n={n}$, $q={CELLS[n]}$ ($N={res['n_seeds']}$)")
        ax.set_xlabel("tour")
        ax.grid(alpha=0.15, zorder=0)

    axes[0].set_ylabel(r"mean $d(\mathrm{LN})$ (distance to fixed point), nats")
    axes[0].legend(loc="upper right", framealpha=0.9, fontsize=9)
    fig.suptitle(r"NTRU convergence efficiency ($\beta=20$, fplll): per-seed tour at "
                 r"which SD-BKZ first reaches its BKZ final $d(\mathrm{LN})$",
                 y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
