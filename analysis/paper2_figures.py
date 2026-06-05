#!/usr/bin/env python3
"""paper2_figures.py -- figure pipeline for the NTRU cross-engine report (paper 2).

Renders the paper-2 figures directly into paper2/latex/figs/, reusing the
shared analysis style (analysis/_style.py) and seed loader (analysis/_data.py)
so the visual identity matches paper 1. Kept separate from paper_figures.py
(paper 1's LWE pipeline) and from the paper1 figs_source_map parity gate --
paper 2 figures are not part of that gate.

Each figure is one module under analysis/plots/ (ntru_*), matching the
one-module-per-figure convention.

Usage:
    python3 analysis/paper2_figures.py [--output-dir paper2/latex/figs]
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from analysis._data import load_all_seeds  # noqa: E402
from analysis.plots.ntru_dimension_onset import fig_ntru_dimension_onset  # noqa: E402
from analysis.plots.ntru_dsd_onset_trend import fig_ntru_dsd_onset_trend  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("paper2_figures")
DEFAULT_OUT = os.path.join(REPO_ROOT, "paper2", "latex", "figs")


def main():
    parser = argparse.ArgumentParser(description="Generate paper-2 figures.")
    parser.add_argument("--output-dir", default=DEFAULT_OUT,
                        help="directory for the PNGs (default: paper2/latex/figs)")
    parser.add_argument("--campaign", default="ntru",
                        help="manifest campaign for the NTRU seeds (default: ntru)")
    args = parser.parse_args()

    PIPELINE.info("paper2_figures start", cat="analysis",
                  output_dir=args.output_dir)

    groups = load_all_seeds(campaign=args.campaign, q=97)
    out1 = fig_ntru_dimension_onset(groups, output_dir=args.output_dir)
    out2 = fig_ntru_dsd_onset_trend(output_dir=args.output_dir)

    for out in (out1, out2):
        PIPELINE.info("wrote figure", cat="analysis", path=out)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
