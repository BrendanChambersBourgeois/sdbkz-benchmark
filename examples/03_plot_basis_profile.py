#!/usr/bin/env python3
"""
Example 3: Plot the GSO log-norm staircase for one seed.

Loads a single seed and produces a small chart showing log||b*_i|| vs basis
position for both BKZ and SD-BKZ, with the GSA and Li-Nguyen theoretical
predictions overlaid. This is a single-seed version of fig10 from the paper.

Usage:
    python3 examples/03_plot_basis_profile.py
    python3 examples/03_plot_basis_profile.py --n 100 --beta 30 --seed 1

Expected output: PNG saved to examples/output/single_seed_profile.png.
Runtime: ~2 seconds.
"""
import argparse
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
sys.path.insert(0, REPO_ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--beta", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--campaign", default="main",
                        help="Manifest campaign to query (default: main)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Where the PNG lands (default: examples/output/). "
                             "CI / read-only-mount callers must override.")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    from analysis._data import load_all_seeds  # noqa: E402

    groups = load_all_seeds(campaign=args.campaign, q=97)
    key = (args.n, args.beta)
    if key not in groups:
        print(f"ERROR: no (n={args.n}, beta={args.beta}) group in "
              f"campaign={args.campaign}")
        sys.exit(1)
    d = next((s for s in groups[key] if s.get("seed") == args.seed), None)
    if d is None:
        print(f"ERROR: no seed={args.seed} in (n={args.n}, beta={args.beta})")
        sys.exit(1)

    gs_bkz = np.array(d["gs_lognorms_bkz"])
    gs_sd = np.array(d["gs_lognorms_sdbkz"])
    m = d["m"]

    # Slice to active block
    bkz_active = gs_bkz[m:]
    sd_active = gs_sd[m:]
    size = len(bkz_active)
    positions = np.arange(1, size + 1)

    # GSA and LN theoretical predictions
    log_factor = math.log(args.beta / (2 * math.pi * math.e))
    log_delta_gsa = log_factor / (2 * args.beta)
    log_delta_ln = log_factor / (2 * (args.beta - 1))
    log_vol = float(np.sum(bkz_active))

    gsa_line = np.array([
        (size + 1 - 2 * i) * log_delta_gsa + log_vol / size
        for i in range(1, size + 1)
    ])
    ln_line = np.array([
        (size + 1 - 2 * i) * log_delta_ln + log_vol / size
        for i in range(1, size + 1)
    ])

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(positions, gsa_line, color="#f85149", linewidth=1.4, linestyle=":",
            label="GSA prediction", alpha=0.85)
    ax.plot(positions, ln_line, color="#e3b341", linewidth=1.6, linestyle="--",
            label="Li-Nguyen prediction", alpha=0.9)
    ax.plot(positions, bkz_active, color="#000000", linewidth=1.6, label="BKZ")
    ax.plot(positions, sd_active, color="#15803d", linewidth=1.6, label="SD-BKZ")

    ax.set_xlabel("Basis position $i$ (active region)")
    ax.set_ylabel(r"$\log\,\|b^*_i\|$")
    ax.set_title(f"GSO log-norm profile — n={args.n}, $\\beta$={args.beta}, "
                 f"seed={args.seed}")
    ax.legend(fontsize=9, loc="upper right")
    ax.text(0.97, 0.05,
            f"BKZ d(LN):    {d['bkz_final_dln']:.4f}\n"
            f"SD-BKZ d(LN): {d['sdbkz_final_dln']:.4f}\n"
            f"advantage:    {d['advantage']:+.4f}",
            transform=ax.transAxes, fontsize=8, ha="right", va="bottom",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85))

    out = os.path.join(output_dir,
                       f"profile_n{args.n}_beta{args.beta}_seed{args.seed}.png")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
