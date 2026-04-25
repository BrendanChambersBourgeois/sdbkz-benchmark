#!/usr/bin/env python3
"""Refresh paper/fig{N}_<name>.png from analysis/figures/<source>.png.

Reads the declarative mapping at paper/figs_source_map.json and copies
each canonical source figure into the paper bundle under its renamed
HTML-friendly path. Idempotent: if a paper file already byte-matches
its source, it is skipped (preserves mtime, avoids spurious git diffs).

Usage:
    python3 scripts/sync_paper_figures.py [--check]

    --check : report drift without modifying any files; exit 1 if any
              pair differs. Use as a paranoid pre-commit step. The
              CI gate uses scripts/verify_paper_figures_parity.py
              instead, which is the same logic surfaced via a
              dedicated entry-point name.

Origin: backlog F1 option 4 in
/mnt/hgfs/Research/backlog/_shipped/2026-04-20_repo_dir_organization_audit.md.
The drift this guards against was caught at audit-followup 2026-04-25
when 11 of 12 paper/fig*.png had silently fallen out of parity with
analysis/figures/ since commit a34122e (variance-fill SHA refresh).
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("sync_paper_figures")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING = os.path.join(REPO, "paper", "figs_source_map.json")
PAPER_DIR = os.path.join(REPO, "paper")
SOURCE_DIR = os.path.join(REPO, "analysis", "figures")


def _load_pairs() -> list[tuple[str, str]]:
    with open(MAPPING, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    return [(p["paper"], p["source"]) for p in spec["pairs"]]


def _paths(paper_name: str, source_name: str) -> tuple[str, str]:
    return (os.path.join(PAPER_DIR, paper_name),
            os.path.join(SOURCE_DIR, source_name))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report drift only; do not write")
    args = ap.parse_args(argv)

    pairs = _load_pairs()
    drift: list[tuple[str, str]] = []
    copied: list[tuple[str, str]] = []
    missing_source: list[tuple[str, str]] = []

    for paper_name, source_name in pairs:
        paper_path, source_path = _paths(paper_name, source_name)
        if not os.path.exists(source_path):
            missing_source.append((paper_name, source_name))
            continue
        if os.path.exists(paper_path) and filecmp.cmp(paper_path, source_path, shallow=False):
            continue
        drift.append((paper_name, source_name))
        if not args.check:
            shutil.copy2(source_path, paper_path)
            copied.append((paper_name, source_name))

    if missing_source:
        for paper_name, source_name in missing_source:
            PIPELINE.warning(
                "missing source figure", cat="paper_figures",
                paper=paper_name, source=source_name,
            )
            print(f"MISSING SOURCE: analysis/figures/{source_name} "
                  f"(needed for paper/{paper_name})", file=sys.stderr)

    if args.check:
        if drift:
            PIPELINE.warning(
                "drift detected (check mode)", cat="paper_figures",
                drift_count=len(drift),
            )
            print(f"DRIFT: {len(drift)} of {len(pairs)} paper figs "
                  f"differ from their analysis/figures/ source.",
                  file=sys.stderr)
            for paper_name, source_name in drift:
                print(f"  paper/{paper_name}  !=  analysis/figures/{source_name}",
                      file=sys.stderr)
            print("\nFix: bash scripts/sync_paper_figures.py (drop --check)",
                  file=sys.stderr)
            return 1
        if missing_source:
            return 1
        PIPELINE.info(
            "parity check passed", cat="paper_figures",
            pairs_checked=len(pairs),
        )
        return 0

    PIPELINE.info(
        "sync complete", cat="paper_figures",
        copied_count=len(copied), drift_count=len(drift),
        missing_source_count=len(missing_source),
    )
    if copied:
        print(f"refreshed {len(copied)} paper figures from analysis/figures/:",
              file=sys.stderr)
        for paper_name, source_name in copied:
            print(f"  paper/{paper_name}  <-  analysis/figures/{source_name}",
                  file=sys.stderr)
    elif not missing_source:
        print("no drift; nothing to refresh.", file=sys.stderr)
    return 1 if missing_source else 0


if __name__ == "__main__":
    sys.exit(main())
