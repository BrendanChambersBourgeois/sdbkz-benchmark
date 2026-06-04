#!/usr/bin/env python3
"""Cross-engine comparator: fplll vs g6k on a matched seed cell.

For a given (n, β, max_tours, q), compare the per-seed SD-BKZ vs BKZ
behaviour between the fplll seed tree (results/seeds/<fplll_tag>/) and the
g6k tree (results/seeds/<g6k_tag>/) — they must share the same q/p_mt/n_beta
leaf. The headline question (g6k SD-BKZ anomaly, ADR-008 follow-up): does
each engine's SD-BKZ "fire" a short-vector event (final gs_lognorms_sdbkz[0]
drops below the q-vector floor) on the SAME seeds?

Writes a results/validation/ record (see results/validation/README.md) and
prints a per-seed table. Pure analysis — never runs a reduction, never
touches the science seed trees. Reused by the night chain, the morning
review, and the eventual writeup.

CLI:
    python3 scripts/compare_xengine.py --n 89 --beta 40 --max-tours 50 --q 97
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("compare_xengine")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# q-vector floor: a head GS log-norm at/above ~ln(q) is an unbroken q-vector;
# "fired" = SD-BKZ pulled a vector below it to position 0 (short-vector /
# DSD-like event). Default threshold sits below ln(97)=4.57.
DEFAULT_FIRE_THRESHOLD = 3.5


def _cell_glob(tag: str, n: int, beta: int, mt: int, q: int) -> str:
    return os.path.join(
        BASE, "results", "seeds", tag, f"q{q}", f"p250_mt{mt}",
        f"n{n:03d}_beta{beta:02d}", "seed*.json"
    )


def _load(tag: str, n: int, beta: int, mt: int, q: int) -> dict[int, dict]:
    out = {}
    for f in glob.glob(_cell_glob(tag, n, beta, mt, q)):
        d = json.load(open(f))
        out[int(d["seed"])] = d
    return out


def _gs0(d: dict, variant: str):
    gs = d.get(f"gs_lognorms_{variant}") or []
    return gs[0] if gs else None


def compare(n, beta, mt, q, fplll_tag, g6k_tag, threshold):
    fp = _load(fplll_tag, n, beta, mt, q)
    g6 = _load(g6k_tag, n, beta, mt, q)
    seeds = sorted(set(fp) & set(g6))
    rows = []
    def _rhf_diff(d: dict):
        # Guarded: a partial/legacy seed JSON missing an rhf field must skip,
        # not KeyError-abort the whole comparison.
        b, s_ = d.get("rhf_bkz"), d.get("rhf_sdbkz")
        return (b - s_) if (b is not None and s_ is not None) else None

    for s in seeds:
        fs0 = _gs0(fp[s], "sdbkz")
        gs0 = _gs0(g6[s], "sdbkz")
        rows.append({
            "seed": s,
            "fplll_sdbkz_gs0": fs0,
            "g6k_sdbkz_gs0": gs0,
            "fplll_fired": (fs0 is not None and fs0 < threshold),
            "g6k_fired": (gs0 is not None and gs0 < threshold),
            "fplll_rhf_diff": _rhf_diff(fp[s]),
            "g6k_rhf_diff": _rhf_diff(g6[s]),
        })
    fp_fired = {r["seed"] for r in rows if r["fplll_fired"]}
    g6_fired = {r["seed"] for r in rows if r["g6k_fired"]}
    both = fp_fired & g6_fired
    either = fp_fired | g6_fired
    agreement = (len(both) / len(either)) if either else 1.0  # Jaccard
    return {
        "validation": f"g6k_sd_xengine_n{n}_mt{mt}",
        "adr": "ADR-008",
        "engine": "g6k-vs-fplll",
        "params": {"n": n, "beta": beta, "max_tours": mt, "q": q,
                   "fire_threshold": threshold,
                   "fplll_tag": fplll_tag, "g6k_tag": g6k_tag},
        "result": "INFO",
        "data": {
            "matched_seeds": len(seeds),
            "fplll_fired_seeds": sorted(fp_fired),
            "g6k_fired_seeds": sorted(g6_fired),
            "both_fired": sorted(both),
            "jaccard_agreement": round(agreement, 3),
            "per_seed": rows,
        },
        "conclusion": (
            f"n={n} mt={mt}: g6k fired {len(g6_fired)}/{len(seeds)}, "
            f"fplll fired {len(fp_fired)}/{len(seeds)}, "
            f"Jaccard {agreement:.2f}. "
            "High agreement → real DSD-onset (construction sound); "
            "g6k-fires-where-fplll-does-not → suspect high-tour drift."
        ),
        "reproduce": (
            f"python3 scripts/compare_xengine.py --n {n} --beta {beta} "
            f"--max-tours {mt} --q {q}"
        ),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--beta", type=int, default=40)
    ap.add_argument("--max-tours", type=int, default=50, dest="mt")
    ap.add_argument("--q", type=int, default=97)
    ap.add_argument("--fplll-tag", default="ntru", dest="fplll_tag")
    ap.add_argument("--g6k-tag", default="ntru_g6k", dest="g6k_tag")
    ap.add_argument("--threshold", type=float, default=DEFAULT_FIRE_THRESHOLD)
    ap.add_argument("--out", default=None,
                    help="output JSON path (default results/validation/<id>.json)")
    args = ap.parse_args(argv)

    rec = compare(args.n, args.beta, args.mt, args.q,
                  args.fplll_tag, args.g6k_tag, args.threshold)
    out = args.out or os.path.join(
        BASE, "results", "validation", rec["validation"] + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(rec, fh, indent=2)

    d = rec["data"]
    print(f"  cross-engine n={args.n} β={args.beta} mt={args.mt} q={args.q}  "
          f"({d['matched_seeds']} matched seeds)")
    print(f"  {'seed':>4} {'fplll_gs0':>10} {'g6k_gs0':>9} "
          f"{'fp_fire':>7} {'g6k_fire':>8}")
    for r in d["per_seed"]:
        fs = f"{r['fplll_sdbkz_gs0']:.3f}" if r['fplll_sdbkz_gs0'] is not None else "n/a"
        gs = f"{r['g6k_sdbkz_gs0']:.3f}" if r['g6k_sdbkz_gs0'] is not None else "n/a"
        print(f"  {r['seed']:>4} {fs:>10} {gs:>9} "
              f"{str(r['fplll_fired']):>7} {str(r['g6k_fired']):>8}")
    print(f"\n  {rec['conclusion']}")
    print(f"  wrote {os.path.relpath(out, BASE)}")
    PIPELINE.info("xengine compare", cat="validation", n=args.n, mt=args.mt,
                  g6k_fired=len(d["g6k_fired_seeds"]),
                  fplll_fired=len(d["fplll_fired_seeds"]),
                  jaccard=d["jaccard_agreement"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
