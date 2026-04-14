#!/usr/bin/env python3
"""Mean wall-clock runtime per seed by (n, β) for BKZ and SD-BKZ.

Reads bkz_time and sdbkz_time from every q=97 seed JSON, groups by
(n, β), and writes both a machine-readable JSON and a self-contained
HTML <table> suitable for pasting into the paper.

Usage:
    python3 analysis/runtime_table.py

Outputs:
    results/runtime_table.json   — full data + provenance
    results/runtime_table.html   — standalone <table> with inline styles
"""
import os
import sys
import json
import datetime

import numpy as np

# Repo root derived from this file's location — works for any checkout path.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from analysis._data import load_all_seeds  # noqa: E402


# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_RAW_DIR = os.path.join(REPO_ROOT, "results", "raw")
DEFAULT_CLOUD_DIR = os.path.join(REPO_ROOT, "results", "cloud")
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


def render_html(rows):
    """Render the runtime table as a standalone HTML <table> element.

    Uses inline styles so the paste is self-contained — no external CSS,
    no class dependencies. Drops cleanly into a paper draft, blog post,
    or any HTML container.
    """
    parts = []
    parts.append(
        '<table cellspacing="0" cellpadding="6" '
        'style="border-collapse: collapse; font-family: serif; '
        'border-top: 2px solid #333; border-bottom: 2px solid #333;">'
    )
    parts.append(
        '  <caption style="text-align: left; padding: 6px 0; '
        'font-style: italic; caption-side: top;">'
        'Mean wall-clock runtime per seed by lattice dimension and block '
        'size, for BKZ and SD-BKZ on q=97 LWE-Kannan instances at 70 '
        'tours, single-core fpylll. Complete 100-seed groups only.'
        '</caption>'
    )
    parts.append('  <thead>')
    parts.append(
        '    <tr style="border-bottom: 1px solid #333;">'
    )
    headers = [
        "n", "β", "seeds", "BKZ mean (s)", "SD-BKZ mean (s)", "SD-BKZ / BKZ"
    ]
    for h in headers:
        parts.append(
            f'      <th style="text-align: right; padding: 6px 14px; '
            f'font-weight: bold;">{h}</th>'
        )
    parts.append('    </tr>')
    parts.append('  </thead>')
    parts.append('  <tbody>')

    for row in rows:
        parts.append('    <tr>')
        cells = [
            str(row["n"]),
            str(row["beta"]),
            str(row["seeds"]),
            f'{row["bkz_mean_s"]:.2f}',
            f'{row["sdbkz_mean_s"]:.2f}',
            f'{row["ratio"]:.2f}×',
        ]
        for c in cells:
            parts.append(
                f'      <td style="text-align: right; padding: 4px 14px;">'
                f'{c}</td>'
            )
        parts.append('    </tr>')

    parts.append('  </tbody>')
    parts.append('</table>')
    return "\n".join(parts)


def main():
    print(f"Loading seeds from:")
    print(f"  {DEFAULT_RAW_DIR}")
    print(f"  {DEFAULT_CLOUD_DIR}")
    groups = load_all_seeds(DEFAULT_RAW_DIR, DEFAULT_CLOUD_DIR)
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
            "Single-core fpylll on q=97 LWE-Kannan instances, 70 tours. "
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
    html_path = os.path.join(OUT_DIR, "runtime_table.html")
    with open(html_path, "w") as f:
        f.write(render_html(rows) + "\n")
    print(f"Saved HTML: {html_path}")

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


if __name__ == "__main__":
    main()
