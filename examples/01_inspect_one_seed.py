#!/usr/bin/env python3
"""
Example 1: Inspect a single seed's result.

The simplest possible interaction with this benchmark — load one seed file
and print a human-readable summary of what was measured. No new computation,
no figures, just data inspection.

Usage:
    python3 examples/01_inspect_one_seed.py
    python3 examples/01_inspect_one_seed.py --n 100 --beta 30 --seed 1

Expected output: ~20 lines describing one (n, beta, seed) result.
Runtime: <1 second.
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=100, help="Lattice dimension")
    parser.add_argument("--beta", type=int, default=30, help="Block size")
    parser.add_argument("--seed", type=int, default=1, help="Seed number")
    args = parser.parse_args()

    # Look in both raw (local sweep) and cloud (AWS sweep) directories
    candidates = [
        os.path.join(REPO_ROOT, "results", "raw",
                     f"n{args.n}_beta{args.beta}_seed{args.seed}.json"),
        os.path.join(REPO_ROOT, "results", "cloud",
                     f"n{args.n}_beta{args.beta}_seed{args.seed}.json"),
    ]
    path = next((p for p in candidates if os.path.isfile(p)), None)
    if path is None:
        print(f"ERROR: no result for n={args.n}, beta={args.beta}, seed={args.seed}")
        print("Tried:")
        for p in candidates:
            print(f"  {p}")
        sys.exit(1)

    with open(path) as f:
        d = json.load(f)

    print("=" * 60)
    print(f"  n={d['n']}, beta={d['beta']}, seed={d['seed']}, q={d.get('q', 97)}")
    print(f"  Lattice dimension: dim = {d.get('dim', '?')}")
    print(f"  MPFR precision:    {d.get('precision', '?')} bits")
    print("=" * 60)
    print()
    print("FINAL d(LN) — distance from Li-Nguyen fixed point:")
    print(f"  BKZ:    {d['bkz_final_dln']:.4f} nats")
    print(f"  SD-BKZ: {d['sdbkz_final_dln']:.4f} nats")
    print(f"  → SD-BKZ advantage: {d['advantage']:+.4f} nats")
    print()
    if "rhf_bkz" in d and "rhf_sdbkz" in d:
        print("ROOT HERMITE FACTOR (standard metric):")
        print(f"  BKZ:    {d['rhf_bkz']:.6f}")
        print(f"  SD-BKZ: {d['rhf_sdbkz']:.6f}")
        print(f"  → RHF advantage: {d.get('rhf_advantage', 0):+.6f}")
        print()
    print("RUNTIME:")
    print(f"  BKZ:    {d.get('bkz_time', 0):.1f}s ({d.get('bkz_tours_run', '?')} tours)")
    print(f"  SD-BKZ: {d.get('sdbkz_time', 0):.1f}s ({d.get('sdbkz_tours_run', '?')} tours)")
    if d.get("bkz_time") and d.get("sdbkz_time"):
        ratio = d["sdbkz_time"] / d["bkz_time"]
        print(f"  → SD-BKZ runtime ratio: {ratio:.2f}x")
    print()
    print(f"Source: {os.path.relpath(path, REPO_ROOT)}")


if __name__ == "__main__":
    main()
