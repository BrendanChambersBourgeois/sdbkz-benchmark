#!/usr/bin/env python3
"""Extract the reference-free DSD-onset modulus from seed cells.

For a fixed (n, beta) and a reduction variant (BKZ or SD-BKZ), the
dense-sublattice-discovery (DSD) onset is the modulus q at which the variant
starts cracking the dense secret sublattice. A seed's output basis counts as
DSD under the PROPER two-part reference-free criterion

    short = #{i : log||b*_i|| < log(sqrt(2n*2/3)) + 0.5} <= n + 1
    AND   min_i log||b*_i|| > 1.5

i.e. the profile has collapsed to the dense sublattice (at most n+1 vectors
survive below the secret-norm threshold) AND the shortest GS vector clears
the floor. The short-count threshold is n-DEPENDENT (2.746 at n=67, 2.888 at
n=89, 3.008 at n=113): the ternary-secret log-norm plus a 0.5-nat margin. NOT the gs_lognorms[0] < 3.5 "fired" proxy (which double-bit us this
session), and NOT the b1>1.5 half alone -- that over-fires at small n, where a
reduced-but-uncracked basis already has min(gs)>1.5 (e.g. n=67 q=97:
min(gs)~1.7-2.0 but short=2n, no collapse). The onset q is the modulus at which
the DSD rate crosses 0.5, linearly interpolated between bracketing cells.

This reproduces the committed paper-2 trend (Table tab:dsdgap) EXACTLY at all
five rows -- n=67 144.6/145.4, n=79 171.2/171.0, n=89 238.0/283.3,
n=101 428.6/512.2, n=113 729.2/930.4 -- seed-backed end to end since the
2026-06-07 WSL2 ball-out completed the beta=20 precision ladder (grid now
reaches q=1279 at n=113). SENSITIVITY: freezing the threshold at its n=89
value 2.888 across the n-grid (the pre-2026-06-11 behaviour) shifts only the
near-zero-gap rows (n=67 -> 166.6/167.5, n=79 -> 181.7/182.5, n=113 BKZ ->
925.0) and leaves the gap trend unchanged (1,0,19,20,28 -> ...,27).

Pure analysis -- reads results/seeds/, never runs a reduction. Reused for both
engines (fplll tree results/seeds/ntru/, g6k tree results/seeds/ntru_g6k/) and
any n / beta.

CLI:
    python3 scripts/extract_dsd_onset.py --n 89 --beta 20
    python3 scripts/extract_dsd_onset.py --n 89 --beta 40 --engine g6k
    python3 scripts/extract_dsd_onset.py --trend            # the 5-point table
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("extract_dsd_onset")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

B1_FLOOR = 1.5                      # secret-norm floor (log-norm)


def short_threshold(n: int) -> float:
    """n-dependent short-count threshold: ternary-secret log-norm + 0.5-nat
    margin (log(sqrt(2n*2/3)) + 0.5; = 2.888 at n=89)."""
    return 0.5 * math.log(2 * n * 2 / 3) + 0.5


DEFAULT_RATE = 0.5                  # onset = DSD-rate crossing of this fraction
ENGINE_TREE = {"fplll": "ntru", "g6k": "ntru_g6k"}
# The committed paper-2 5-point trend (Table tab:dsdgap), beta=20, fplll.
TREND_NS = [67, 79, 89, 101, 113]


def _is_dsd(seed: dict, variant: str, n: int) -> bool:
    """Proper two-part reference-free DSD criterion (the saturation-record
    definition): the dense sublattice is found when the profile has collapsed
    so that at most n+1 GS vectors survive below the q-floor AND the shortest
    GS vector clears the secret-norm floor. The b1>1.5 half alone over-fires at
    small n, where a reduced-but-uncracked basis already has min(gs)>1.5."""
    gs = seed.get(f"gs_lognorms_{variant}") or []
    if not gs:
        return False
    short = sum(1 for x in gs if x < short_threshold(n))
    return short <= n + 1 and min(gs) > B1_FLOOR


def _cell_rate(tree: str, n: int, beta: int, q: int, variant: str):
    """(fires, total) for one (tree, n, beta, q) cell, or None if absent."""
    pat = os.path.join(BASE, "results", "seeds", tree, f"q{q}",
                       "p*_mt*", f"n{n:03d}_beta{beta:02d}", "seed*.json")
    files = sorted(glob.glob(pat))
    if not files:
        return None
    fires = sum(_is_dsd(json.load(open(f)), variant, n) for f in files)
    return fires, len(files)


def _q_grid(tree: str, n: int, beta: int) -> list[int]:
    pat = os.path.join(BASE, "results", "seeds", tree, "q*",
                       "p*_mt*", f"n{n:03d}_beta{beta:02d}")
    qs = set()
    for d in glob.glob(pat):
        # .../q<NNN>/p<prec>_mt*/n...  (p* spans p250/p500/p1000 ladder)
        for part in d.split(os.sep):
            if part.startswith("q") and part[1:].isdigit():
                qs.add(int(part[1:]))
    return sorted(qs)


def _interp_onset(curve: list[tuple[int, float]], rate: float):
    """First q at which the DSD rate crosses `rate`, linearly interpolated
    between the bracketing cells. Returns (onset_q, note)."""
    if not curve:
        return None, "no cells"
    # already above the threshold at the smallest q -> onset at/below grid
    if curve[0][1] >= rate:
        return float(curve[0][0]), f"<= grid min q={curve[0][0]} (already >= {rate:.0%})"
    prev_q, prev_r = curve[0]
    for q, r in curve[1:]:
        if r >= rate:
            if r == prev_r:
                return float(q), "flat crossing"
            onset = prev_q + (q - prev_q) * (rate - prev_r) / (r - prev_r)
            return round(onset, 1), f"interp [{prev_q},{q}]"
        prev_q, prev_r = q, r
    return None, f"never reaches {rate:.0%} (grid max q={curve[-1][0]}, max rate {curve[-1][1]:.0%})"


def onset_for(tree: str, n: int, beta: int, variant: str, rate: float):
    """Return (onset_q_or_None, note, curve) for one variant."""
    curve = []
    for q in _q_grid(tree, n, beta):
        cell = _cell_rate(tree, n, beta, q, variant)
        if cell:
            curve.append((q, cell[0] / cell[1]))
    onset, note = _interp_onset(curve, rate)
    return onset, note, curve


def report_cell(tree: str, n: int, beta: int, rate: float) -> dict:
    out = {}
    for variant in ("sdbkz", "bkz"):
        onset, note, curve = onset_for(tree, n, beta, variant, rate)
        out[variant] = {"onset": onset, "note": note,
                        "curve": [(q, round(r, 3)) for q, r in curve]}
    sd, bkz = out["sdbkz"]["onset"], out["bkz"]["onset"]
    out["gap_pct"] = (round(100.0 * (bkz - sd) / sd)
                      if sd and bkz else None)
    return out


def _print_one(n: int, beta: int, tree: str, r: dict) -> None:
    sd, bkz, gap = r["sdbkz"]["onset"], r["bkz"]["onset"], r["gap_pct"]
    print(f"n={n:3d} beta={beta} ({tree}): "
          f"SD onset {sd}  BKZ onset {bkz}  gap {gap}%"
          if gap is not None else
          f"n={n:3d} beta={beta} ({tree}): SD {sd} ({r['sdbkz']['note']})  "
          f"BKZ {bkz} ({r['bkz']['note']})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract reference-free DSD-onset q from seeds.")
    ap.add_argument("--n", type=int, help="NTRU parameter n")
    ap.add_argument("--beta", type=int, default=20)
    ap.add_argument("--engine", choices=("fplll", "g6k"), default="fplll")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE,
                    help="DSD-rate crossing that defines onset (default 0.5)")
    ap.add_argument("--trend", action="store_true",
                    help="print the 5-point beta=20 fplll trend (Table tab:dsdgap)")
    ap.add_argument("--show-curve", action="store_true",
                    help="print the per-q DSD-rate curve")
    args = ap.parse_args()

    tree = ENGINE_TREE[args.engine]

    if args.trend:
        PIPELINE.info("dsd-onset trend", cat="analysis", beta=args.beta, engine=args.engine)
        print(f"Reference-free DSD-onset trend (short<=n+1 AND b1>{B1_FLOOR}, "
              f"rate {args.rate:.0%} crossing), beta={args.beta}, {tree}:")
        print(f"{'n':>4} {'SD onset':>9} {'BKZ onset':>10} {'gap%':>5}")
        for n in TREND_NS:
            r = report_cell(tree, n, args.beta, args.rate)
            sd, bkz, gap = r["sdbkz"]["onset"], r["bkz"]["onset"], r["gap_pct"]
            print(f"{n:>4} {str(sd):>9} {str(bkz):>10} {str(gap):>5}"
                  + ("" if gap is not None else f"   <- {r['sdbkz']['note']} / {r['bkz']['note']}"))
        return 0

    if args.n is None:
        ap.error("provide --n (or --trend)")
    r = report_cell(tree, args.n, args.beta, args.rate)
    _print_one(args.n, args.beta, tree, r)
    if args.show_curve:
        for variant in ("sdbkz", "bkz"):
            print(f"  {variant}: {r[variant]['curve']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
