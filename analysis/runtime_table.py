#!/usr/bin/env python3
"""Mean wall-clock runtime per seed by (n, β) for BKZ and SD-BKZ.

Reads bkz_time and sdbkz_time from every q=97 seed JSON, groups by
(n, β), and writes both a machine-readable JSON and a self-contained
HTML <table> suitable for pasting into the paper.

Usage:
    python3 analysis/runtime_table.py

Outputs:
    results/runtime_table.json   — full data + provenance
"""
import datetime
import json
import os
import sys

import numpy as np

# Repo root derived from this file's location — works for any checkout path.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from analysis._data import load_all_seeds  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("runtime_table")


# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_CAMPAIGN = "main"
OUT_DIR = os.path.join(REPO_ROOT, "results")
MIN_SEEDS = 100   # only complete groups


def compute_runtime_table(groups, min_seeds=MIN_SEEDS):
    """Per-group mean BKZ and SD-BKZ wall-clock seconds.

    Returns a list of dicts sorted by (n, beta) with these keys:
        n, beta, seeds,
        bkz_mean_s, bkz_std_s,
        sdbkz_mean_s, sdbkz_std_s,
        ratio (SD-BKZ mean / BKZ mean)

    Only seeds with both bkz_time and sdbkz_time populated contribute.
    Groups with fewer than min_seeds usable seeds are skipped.
    """
    rows = []
    for (n, beta), seeds in sorted(groups.items()):
        # Seeds 1-100 only: the set the paper's runtime table reports.
        seeds = [s for s in seeds if s["seed"] <= 100]
        bkz_times = [s["bkz_time"] for s in seeds
                     if s.get("bkz_time") is not None]
        sd_times = [s["sdbkz_time"] for s in seeds
                    if s.get("sdbkz_time") is not None]
        n_usable = min(len(bkz_times), len(sd_times))
        if n_usable < min_seeds:
            continue

        bkz_arr = np.array(bkz_times[:n_usable])
        sd_arr = np.array(sd_times[:n_usable])
        bkz_mean = float(np.mean(bkz_arr))
        sd_mean = float(np.mean(sd_arr))
        ratio = sd_mean / bkz_mean if bkz_mean > 0 else float("nan")

        rows.append({
            "n": n,
            "beta": beta,
            "seeds": n_usable,
            "bkz_mean_s": bkz_mean,
            "bkz_std_s": float(np.std(bkz_arr, ddof=1)),
            "sdbkz_mean_s": sd_mean,
            "sdbkz_std_s": float(np.std(sd_arr, ddof=1)),
            "ratio": ratio,
        })
    return rows


def main():
    PIPELINE.info("runtime_table start", cat="analysis")
    # v1.3+ manifest mode. Legacy dir globber still reachable by passing
    # positional dirs to load_all_seeds explicitly; keeping that path
    # available guards against the manifest being stale / absent.
    print(f"Loading seeds via manifest (campaign={DEFAULT_CAMPAIGN!r}).")
    groups = load_all_seeds(campaign=DEFAULT_CAMPAIGN)
    if not groups:
        print("ERROR: no seed files loaded.")
        sys.exit(1)

    rows = compute_runtime_table(groups, min_seeds=MIN_SEEDS)
    if not rows:
        print(f"No groups with ≥{MIN_SEEDS} usable seeds — nothing to write.")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    # JSON output (machine-readable)
    json_path = os.path.join(OUT_DIR, "runtime_table.json")
    payload = {
        "description": (
            "Mean wall-clock runtime per seed per (n, β) group. "
            "Single-core fpylll on q=97 LWE-Kannan instances, "
            "50/70/100 tours for β=20/30/40, seeds 1-100. "
            "Includes only complete groups (≥ min_seeds seeds with both "
            "bkz_time and sdbkz_time populated)."
        ),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "min_seeds": MIN_SEEDS,
        "n_groups": len(rows),
        "groups": rows,
    }
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved JSON: {json_path}")

    # HTML output (paste-able into paper)

    # Stdout summary
    print()
    print(f"{'n':>4} {'β':>3} {'seeds':>6} {'BKZ (s)':>12} "
          f"{'SD-BKZ (s)':>14} {'ratio':>8}")
    print("-" * 56)
    for row in rows:
        print(f"{row['n']:>4} {row['beta']:>3} {row['seeds']:>6} "
              f"{row['bkz_mean_s']:>12.2f} {row['sdbkz_mean_s']:>14.2f} "
              f"{row['ratio']:>7.2f}×")
    print()
    print(f"{len(rows)} complete groups summarized.")
    PIPELINE.info("runtime_table complete", cat="analysis")


if __name__ == "__main__":
    main()
