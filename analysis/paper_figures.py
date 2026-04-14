#!/usr/bin/env python3
"""paper_figures.py — entry point for the SD-BKZ benchmark figure pipeline.

The actual figure / diagnostic / table code lives in the `analysis`
package as of the 2026-04-09 refactor:

    analysis/
        _data.py            Data loading + lattice math + decomposition helpers
        _style.py           Shared color palette + matplotlib rcParams
        plots/              One module per figure (fig01..fig13) + orchestrator
        diagnostics.py      Statistical diagnostics (diag_*)
        tables.py           Paper-ready text tables (table_*)
        paper_figures.py    This file — argparse + entry point

This script keeps the original CLI invocation working
(`python3 analysis/paper_figures.py --output-dir foo`). The sys.path hack
puts the repo root on sys.path so `from analysis...` imports resolve when
the script is run directly. The package is also importable normally:

    from analysis.plots import generate_all, fig_dimension_scaling
    from analysis._data import load_all_seeds
    from analysis import diagnostics, tables
"""
import os
import sys
import argparse

# Repo root derived from this file's location — works for any checkout path.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from analysis.plots import generate_all  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Generate paper figures and analysis from BKZ seed data."
    )
    parser.add_argument(
        "--results-dir", nargs="+",
        default=[os.path.join(REPO_ROOT, "results", "raw")],
        help="Directories containing seed JSONs (can specify multiple).",
    )
    parser.add_argument(
        "--cloud-dir",
        default=os.path.join(REPO_ROOT, "results", "cloud"),
        help="Cloud results directory (merged with results-dir).",
    )
    parser.add_argument(
        "--tour-dir",
        default=os.path.join(REPO_ROOT, "results", "3x_tours"),
        help="3x tour experiment directory (loads only the *_3x_seed*.json files).",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(REPO_ROOT, "analysis", "figures"),
        help="Where to save output PNGs.",
    )
    parser.add_argument(
        "--min-seeds", type=int, default=10,
        help="Minimum seeds per group to include (default: 10).",
    )
    args = parser.parse_args()

    all_dirs = args.results_dir
    if args.cloud_dir and os.path.isdir(args.cloud_dir):
        all_dirs.append(args.cloud_dir)

    generate_all(
        results_dirs=all_dirs,
        output_dir=args.output_dir,
        tour_dir=args.tour_dir if os.path.isdir(args.tour_dir) else None,
        min_seeds=args.min_seeds,
    )


if __name__ == "__main__":
    main()
