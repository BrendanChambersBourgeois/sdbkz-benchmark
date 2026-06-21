#!/usr/bin/env python3
"""Cross-architecture seed compare: results/seeds/ntru_xarch vs results/seeds/ntru.

A seed regenerated on another machine lands in the ntru_xarch tree (separate
seed_tag, never the canonical ntru/ tree). This tool walks the ntru_xarch tree
and, for each seed that has a canonical ntru/ counterpart at the isomorphic path
(the two paths differ ONLY in the campaign segment), compares them by
science_hash (_seed_hash). Three buckets:

  - matched              counterpart exists and science_hash is identical
  - mismatched           counterpart exists but science_hash differs
  - topup-no-baseline    no canonical counterpart (extra seeds banked beyond
                         the verify baseline) -- informational, NOT an error

Verdict: PASS iff there is at least one matched pair and ZERO mismatches.
On a mismatch, a per-field tolerance diff (max abs difference over the numeric
science fields) is reported so a last-ULP near-miss is distinguishable from real
numerical drift.

Usage:
    python3 scripts/compare_seed_trees.py [--xarch-root R] [--canonical-root R]
                                          [--tol 1e-4] [--report out.json]
Exit code 0 on PASS, 1 on mismatch (so `make` / CI can gate on it).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from _seed_hash import SCIENCE_EXCLUDE, science_hash  # noqa: E402
from log import get_logger  # noqa: E402

PIPELINE = get_logger("compare_seed_trees")
DEFAULT_XARCH = os.path.join("results", "seeds", "ntru_xarch")
DEFAULT_CANON = os.path.join("results", "seeds", "ntru")


def _counterpart(xarch_path: str, xarch_root: str, canon_root: str) -> str:
    """Canonical path isomorphic to an ntru_xarch seed path (same n/β/seed/q/...,
    only the campaign root differs)."""
    rel = os.path.relpath(xarch_path, xarch_root)
    return os.path.join(canon_root, rel)


def _max_field_diffs(a: dict, b: dict) -> dict:
    """Max abs numeric difference per top-level science field (recurses lists)."""
    def _maxdiff(x, y):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return abs(float(x) - float(y))
        if isinstance(x, list) and isinstance(y, list):
            return max((_maxdiff(u, v) for u, v in zip(x, y, strict=False)),
                       default=0.0)
        return 0.0 if x == y else float("inf")

    diffs = {}
    for k in sorted(set(a) | set(b)):
        if k in SCIENCE_EXCLUDE:
            continue
        diffs[k] = _maxdiff(a.get(k), b.get(k))
    return {k: v for k, v in diffs.items() if v > 0.0}


def compare(xarch_root: str, canon_root: str, tol: float) -> dict:
    matched, mismatched, topup = [], [], []
    seeds = sorted(glob.glob(os.path.join(xarch_root, "**", "seed*.json"),
                             recursive=True))
    for xp in seeds:
        rel = os.path.relpath(xp, xarch_root)
        cp = _counterpart(xp, xarch_root, canon_root)
        if not os.path.exists(cp):
            topup.append(rel)
            continue
        if science_hash(xp) == science_hash(cp):
            matched.append(rel)
        else:
            with open(xp) as f:
                a = json.load(f)
            with open(cp) as f:
                b = json.load(f)
            fdiffs = _max_field_diffs(a, b)
            worst = max(fdiffs.values(), default=0.0)
            mismatched.append({
                "seed": rel,
                "max_abs_diff": worst,
                "within_tol": worst <= tol,
                "fields": fdiffs,
            })
    verdict = bool(matched) and not mismatched
    return {
        "verdict": "PASS" if verdict else "FAIL",
        "n_matched": len(matched),
        "n_mismatched": len(mismatched),
        "n_topup_no_baseline": len(topup),
        "mismatched": mismatched,
        "topup_no_baseline": topup,
        "matched": matched,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-arch seed tree compare.")
    ap.add_argument("--xarch-root", default=DEFAULT_XARCH)
    ap.add_argument("--canonical-root", default=DEFAULT_CANON)
    ap.add_argument("--tol", type=float, default=1e-4,
                    help="abs tolerance for the per-field near-miss report")
    ap.add_argument("--report", default=None,
                    help="optional path to write the full JSON report")
    args = ap.parse_args()

    PIPELINE.info("compare_seed_trees start", cat="verify",
                  xarch=args.xarch_root, canonical=args.canonical_root,
                  tol=args.tol)
    res = compare(args.xarch_root, args.canonical_root, args.tol)
    PIPELINE.info("compare_seed_trees done", cat="verify",
                  verdict=res["verdict"], matched=res["n_matched"],
                  mismatched=res["n_mismatched"],
                  topup=res["n_topup_no_baseline"])

    print(f"verdict: {res['verdict']}")
    print(f"  matched (verify baseline):  {res['n_matched']}")
    print(f"  mismatched:                 {res['n_mismatched']}")
    print(f"  topup (no baseline):        {res['n_topup_no_baseline']}")
    for m in res["mismatched"]:
        tag = "within tol" if m["within_tol"] else "DRIFT"
        print(f"  MISMATCH {m['seed']}: max|Δ|={m['max_abs_diff']:.3e} ({tag})")
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w") as f:
            json.dump(res, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"wrote {args.report}")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
