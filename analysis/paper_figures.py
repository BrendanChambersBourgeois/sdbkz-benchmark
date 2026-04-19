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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from log import get_logger  # noqa: E402
PIPELINE = get_logger("paper_figures")


def main():
    PIPELINE.info("paper_figures start", cat="analysis")
    parser = argparse.ArgumentParser(
        description="Generate paper figures and analysis from BKZ seed data."
    )
    parser.add_argument(
        "--campaign", default="main",
        help="Manifest campaign to pull the main figure-pipeline seeds "
        "from (default: main). Set to empty string to opt out of the "
        "manifest and use the legacy --results-dir / --cloud-dir flags "
        "instead.",
    )
    parser.add_argument(
        "--tour-campaign", default="tours3x",
        help="Manifest campaign for the 3x-tour experiment "
        "(default: tours3x). Set to empty string to use --tour-dir.",
    )
    parser.add_argument(
        "--results-dir", nargs="+",
        default=None,
        help="Legacy override: directories containing seed JSONs. Used "
        "only when --campaign is empty. Pre-v1.3 invocations passed "
        "`results/raw results/cloud` here; post-v1.3 the manifest is "
        "the canonical source and this flag is a fallback for unusual "
        "inputs.",
    )
    parser.add_argument(
        "--cloud-dir", default=None,
        help="Legacy override: cloud results directory, merged with "
        "--results-dir. Used only when --campaign is empty.",
    )
    parser.add_argument(
        "--tour-dir", default=None,
        help="Legacy override: 3x tour experiment directory. Used only "
        "when --tour-campaign is empty.",
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

    # Manifest-first default: no positional dir paths needed. Callers
    # that pass --campaign="" opt back into the pre-v1.3 globber path
    # for special-case data layouts.
    if args.campaign:
        results_dirs = None
        campaign = args.campaign
    else:
        results_dirs = list(args.results_dir or [
            os.path.join(REPO_ROOT, "results", "raw"),
        ])
        if args.cloud_dir and os.path.isdir(args.cloud_dir):
            results_dirs.append(args.cloud_dir)
        campaign = None

    if args.tour_campaign:
        tour_dir = None
        tour_campaign = args.tour_campaign
    else:
        tour_dir = args.tour_dir or os.path.join(
            REPO_ROOT, "results", "3x_tours",
        )
        if not os.path.isdir(tour_dir):
            tour_dir = None
        tour_campaign = None

    generate_all(
        results_dirs=results_dirs,
        output_dir=args.output_dir,
        tour_dir=tour_dir,
        min_seeds=args.min_seeds,
        campaign=campaign,
        tour_campaign=tour_campaign,
    )
    PIPELINE.info("paper_figures complete", cat="analysis")


if __name__ == "__main__":
    main()
