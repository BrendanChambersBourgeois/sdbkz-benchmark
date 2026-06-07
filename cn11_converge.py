#!/usr/bin/env python3
"""Disambiguate the d(real,CN11) dim-growth: convergence artifact vs structural.

Compare d(real,CN11) at MATCHED (n, beta=40) across max_tours: main (mt=50)
vs convergence (mt=500/1000). CN11 simulate uses each seed's own max_tours.
- residual SHRINKS with more tours -> real BKZ was under-converged at mt50;
  the dim-growth is an undertraining artifact -> NO-GO.
- residual STABLE across tours -> real BKZ converged by mt50; the gap is
  STRUCTURAL and grows with dim -> GO.

Read-only over results/seeds/{main,convergence}. Needs fpylll (simulate).
"""
import glob
import json
import math
import os
import statistics as st

from fpylll import BKZ
from fpylll.tools.bkz_simulator import simulate

BASE = "/work"


def slope_removed(p):
    n = len(p); mx = (n - 1) / 2.0; my = sum(p) / n
    sxx = sum((x - mx) ** 2 for x in range(n))
    sxy = sum((x - mx) * (p[x] - my) for x in range(n))
    s = sxy / sxx; c = my - s * mx
    return [p[i] - (s * i + c) for i in range(n)]


def dln(a, b):
    ra, rb = slope_removed(a), slope_removed(b)
    return sum(abs(ra[i] - rb[i]) for i in range(len(ra))) / len(ra)


def d_real_cn11(seed):
    init = seed.get("initial_gs_lognorms"); real = seed.get("gs_lognorms_bkz")
    if not init or not real:
        return None
    r0 = [math.exp(2 * x) for x in init]
    try:
        r_sim, _ = simulate(r0, BKZ.Param(block_size=seed["beta"],
                                          max_loops=seed.get("max_tours") or 50))
    except Exception:
        return None
    cn11 = [0.5 * math.log(x) for x in r_sim]
    return dln(real, cn11) if len(cn11) == len(real) else None


def main():
    # (n, mt) -> [d, ...], beta=40 only
    cells = {}
    for tree in ("main", "convergence"):
        for f in glob.glob(os.path.join(BASE, f"results/seeds/{tree}/**/seed*.json"),
                           recursive=True):
            d = json.load(open(f))
            if d.get("beta") != 40 or d.get("n") not in (110, 120, 130, 140, 150):
                continue
            v = d_real_cn11(d)
            if v is not None:
                cells.setdefault((d["n"], d.get("max_tours")), []).append(v)
    print("d(real,CN11) at beta=40, matched n across max_tours:")
    print(f"{'n':>5} {'mt':>6} {'seeds':>6} {'d(real,CN11)':>13}")
    for (n, mt) in sorted(cells):
        v = cells[(n, mt)]
        print(f"{n:>5} {mt:>6} {len(v):>6} {st.mean(v):>13.4f}")
    print()
    print("=== per-n: mt50 vs high-mt (the verdict) ===")
    ns = sorted({n for (n, mt) in cells})
    for n in ns:
        row = {mt: st.mean(v) for (nn, mt), v in cells.items() if nn == n}
        lo = row.get(50)
        hi = max((m for m in row if m and m >= 500), default=None)
        if lo and hi:
            r = row[hi] / lo
            tag = "SHRINKS->artifact" if r < 0.6 else ("STABLE->structural" if r > 0.85 else "partial")
            print(f"  n={n}: mt50={lo:.4f} -> mt{hi}={row[hi]:.4f}  ratio={r:.2f}  {tag}")
        else:
            print(f"  n={n}: have mt={sorted(k for k in row)} (need both 50 and >=500)")


if __name__ == "__main__":
    main()
