#!/usr/bin/env python3
"""Firm the estimator-d(LN) probe over EXISTING main LWE seeds (no new BKZ).

Each main seed stores both initial_gs_lognorms (LLL'd) and gs_lognorms_bkz
(final real BKZ). Run the CN11 simulator FROM the stored initial profile,
compare to the stored real final profile -> d(real, CN11) at real dims with
~100 seeds/cell. Trend over (beta, n) answers the decisive question the toy
probe couldn't: does the real-vs-estimator-model residual GROW toward
deployed beta/dim, or stay small+flat (-> NO-GO)?

d(real,CN11) = mean | slope-removed(real) - slope-removed(CN11) | (paper-1
reference-free style). Reads results/seeds/main only. Needs fpylll (simulate);
run in sdbkz-benchmark:ci, CPU-capped.
"""
import glob
import json
import math
import os
import statistics as st

from fpylll import BKZ
from fpylll.tools.bkz_simulator import simulate

BASE = "/work"  # repo root inside the container (worktree bind-mount)


def slope_removed(p):
    n = len(p)
    xs = range(n)
    mx = (n - 1) / 2.0
    my = sum(p) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (p[x] - my) for x in xs)
    s = sxy / sxx
    c = my - s * mx
    return [p[i] - (s * i + c) for i in range(n)]


def dln(a, b):
    ra, rb = slope_removed(a), slope_removed(b)
    return sum(abs(ra[i] - rb[i]) for i in range(len(ra))) / len(ra)


def main():
    cells = {}
    for f in glob.glob(os.path.join(BASE, "results/seeds/main/**/seed*.json"),
                       recursive=True):
        d = json.load(open(f))
        init = d.get("initial_gs_lognorms")
        real = d.get("gs_lognorms_bkz")
        beta, n = d.get("beta"), d.get("n")
        mt = d.get("max_tours") or 20
        if not init or not real or beta is None:
            continue
        # CN11 simulate from the stored initial profile (r_i = exp(2*lognorm)).
        r0 = [math.exp(2 * x) for x in init]
        try:
            r_sim, _ = simulate(r0, BKZ.Param(block_size=beta, max_loops=mt))
        except Exception:
            continue
        cn11 = [0.5 * math.log(x) for x in r_sim]
        if len(cn11) != len(real):
            continue
        cells.setdefault((beta, n), []).append(dln(real, cn11))
    print("d(real, CN11) over existing main LWE seeds (mean | per-cell):")
    print(f"{'beta':>5} {'n':>5} {'seeds':>6} {'d(real,CN11)':>13}")
    for (beta, n) in sorted(cells):
        v = cells[(beta, n)]
        print(f"{beta:>5} {n:>5} {len(v):>6} {st.mean(v):>13.4f}")
    print()
    print("=== beta-trend (mean over n) -- the decisive scaling ===")
    bybeta = {}
    for (beta, n), v in cells.items():
        bybeta.setdefault(beta, []).extend(v)
    for beta in sorted(bybeta):
        print(f"  beta={beta}: d(real,CN11)={st.mean(bybeta[beta]):.4f} "
              f"(n={len(bybeta[beta])} seeds)")


if __name__ == "__main__":
    main()
