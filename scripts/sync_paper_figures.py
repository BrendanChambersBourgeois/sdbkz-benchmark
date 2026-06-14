#!/usr/bin/env python3
"""Refresh the paper figure bundles from analysis/figures/.

Two channels share the single canonical source dir analysis/figures/:

  1. HTML bundle  — paper1/fig{N}_<name>.png   (figs_source_map.json "pairs")
  2. LaTeX build  — paper1/latex/figs/figNN.png (figs_source_map.json "latex_pairs")

Both are copied from their mapped analysis/figures/<source>.png. Idempotent:
if a target already byte-matches its source it is skipped (preserves mtime,
avoids spurious git diffs).

Usage:
    python3 scripts/sync_paper_figures.py [--check]

    --check : report drift across BOTH channels without modifying files;
              exit 1 if any pair differs. The CI "Paper figure parity
              gate" step in .github/workflows/build-and-verify.yml invokes
              exactly this (`sync_paper_figures.py --check`) inside the
              pinned image, so local --check == the CI gate.

Origin: backlog F1 option 4 in
backlog/_shipped/2026-04-20_repo_dir_organization_audit.md.
The HTML-channel drift this guards against was caught at audit-followup
2026-04-25 when 11 of 12 paper1/fig*.png had silently fallen out of parity
with analysis/figures/ since commit a34122e (variance-fill SHA refresh).

The LaTeX channel was added 2026-06-02: paper1/latex/figs/ was a frozen
one-time manual export (2026-04-14) sitting OUTSIDE this gate, and it
silently diverged through the variance-fill (the C1 contradiction —
LaTeX text said 122 while its figures showed pre-fill data + "100 seeds").
It is now byte-synced to analysis/figures/ and gated here so the blind
spot cannot recur: --check covers both channels.
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
MAPPING = os.path.join(REPO, "paper1", "figs_source_map.json")
PAPER_DIR = os.path.join(REPO, "paper1")
LATEX_DIR = os.path.join(REPO, "paper1", "latex", "figs")
SOURCE_DIR = os.path.join(REPO, "analysis", "figures")


def _load_targets() -> list[tuple[str, str, str]]:
    """Flatten both channels into (target_abs, source_abs, display) tuples."""
    with open(MAPPING, encoding="utf-8") as fh:
        spec = json.load(fh)
    targets: list[tuple[str, str, str]] = []
    for p in spec.get("pairs", []):
        targets.append((
            os.path.join(PAPER_DIR, p["paper"]),
            os.path.join(SOURCE_DIR, p["source"]),
            f"paper1/{p['paper']}",
        ))
    for p in spec.get("latex_pairs", []):
        targets.append((
            os.path.join(LATEX_DIR, p["latex"]),
            os.path.join(SOURCE_DIR, p["source"]),
            f"paper1/latex/figs/{p['latex']}",
        ))
    return targets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report drift only (both channels); do not write")
    args = ap.parse_args(argv)

    targets = _load_targets()
    drift: list[str] = []
    copied: list[str] = []
    missing_source: list[str] = []

    for target_path, source_path, display in targets:
        if not os.path.exists(source_path):
            missing_source.append(display)
            continue
        if os.path.exists(target_path) and filecmp.cmp(target_path, source_path, shallow=False):
            continue
        drift.append(display)
        if not args.check:
            shutil.copy2(source_path, target_path)
            copied.append(display)

    if missing_source:
        for display in missing_source:
            PIPELINE.warning(
                "missing source figure", cat="paper_figures", target=display,
            )
            print(f"MISSING SOURCE for {display}", file=sys.stderr)

    if args.check:
        if drift:
            PIPELINE.warning(
                "drift detected (check mode)", cat="paper_figures",
                drift_count=len(drift),
            )
            print(f"DRIFT: {len(drift)} of {len(targets)} paper figs "
                  f"differ from their analysis/figures/ source.",
                  file=sys.stderr)
            for display in drift:
                print(f"  {display}  !=  analysis/figures/ source",
                      file=sys.stderr)
            print("\nFix: bash scripts/sync_paper_figures.py (drop --check)",
                  file=sys.stderr)
            return 1
        if missing_source:
            return 1
        PIPELINE.info(
            "parity check passed", cat="paper_figures",
            pairs_checked=len(targets),
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
        for display in copied:
            print(f"  {display}  <-  analysis/figures/ source",
                  file=sys.stderr)
    elif not missing_source:
        print("no drift; nothing to refresh.", file=sys.stderr)
    return 1 if missing_source else 0


if __name__ == "__main__":
    sys.exit(main())
