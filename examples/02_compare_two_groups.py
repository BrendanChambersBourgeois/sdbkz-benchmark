#!/usr/bin/env python3
"""
Example 2: Compare two (n, beta) groups statistically.

Loads all seeds from two groups and computes the SD-BKZ advantage with
mean, standard deviation, win rate, and Cohen's d. No new computation.

Usage:
    python3 examples/02_compare_two_groups.py
    python3 examples/02_compare_two_groups.py --group1 100 30 --group2 150 30

Expected output: ~30 lines with summary statistics for both groups.
Runtime: ~2 seconds (loads ~200 JSON files).
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_group(n, beta):
    """Load all seeds for one (n, beta) group from raw or cloud directories."""
    patterns = [
        os.path.join(REPO_ROOT, "results", "raw", f"n{n}_beta{beta}_seed*.json"),
        os.path.join(REPO_ROOT, "results", "cloud", f"n{n}_beta{beta}_seed*.json"),
    ]
    files = []
    for pat in patterns:
        files.extend(f for f in glob.glob(pat) if "q3329" not in f)
    seen, unique = set(), []
    for f in sorted(files):
        name = os.path.basename(f)
        if name not in seen:
            seen.add(name)
            unique.append(f)
    return [json.load(open(f)) for f in unique]


def summarize(seeds, label):
    if not seeds:
        print(f"  {label}: NO DATA")
        return None
    advs = np.array([s["advantage"] for s in seeds])
    n_seeds = len(advs)
    mean = float(np.mean(advs))
    std = float(np.std(advs, ddof=1)) if n_seeds > 1 else 0.0
    median = float(np.median(advs))
    win_rate = float(np.mean(advs > 0)) * 100
    cohen_d = mean / std if std > 0 else float("nan")

    print(f"  {label}")
    print(f"    seeds:      {n_seeds}")
    print(f"    mean adv:   {mean:+.4f} nats")
    print(f"    median adv: {median:+.4f} nats")
    print(f"    std:        {std:.4f}")
    print(f"    win rate:   {win_rate:.0f}% (SD-BKZ better)")
    print(f"    Cohen's d:  {cohen_d:.2f}")
    return advs


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--group1", nargs=2, type=int, default=[100, 30],
                        metavar=("N", "BETA"), help="First group (n beta)")
    parser.add_argument("--group2", nargs=2, type=int, default=[150, 30],
                        metavar=("N", "BETA"), help="Second group (n beta)")
    args = parser.parse_args()

    n1, b1 = args.group1
    n2, b2 = args.group2

    print(f"Comparing n={n1} β={b1}  vs  n={n2} β={b2}")
    print("=" * 60)
    seeds1 = load_group(n1, b1)
    seeds2 = load_group(n2, b2)

    print()
    print(f"Group 1 — n={n1}, β={b1}:")
    a1 = summarize(seeds1, f"n={n1}_beta{b1}")
    print()
    print(f"Group 2 — n={n2}, β={b2}:")
    a2 = summarize(seeds2, f"n={n2}_beta{b2}")

    if a1 is not None and a2 is not None:
        print()
        print("DIFFERENCE:")
        print(f"  Δ mean = {np.mean(a1) - np.mean(a2):+.4f} nats")
        print(f"  Δ win rate = {np.mean(a1 > 0)*100 - np.mean(a2 > 0)*100:+.0f} pp")


if __name__ == "__main__":
    main()
