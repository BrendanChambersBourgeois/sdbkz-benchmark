#!/usr/bin/env python3
"""
Update bkz_dashboard.jsx with latest experiment data.

Reads from:
  - results/summary.json (main sweep)
  - results/cloud/ directory (cloud results)
  - results/q3329/ directory (q=3329 verification)

Updates the GROUPS array in bkz_dashboard.jsx in-place.
If bkz_dashboard.jsx doesn't exist, exits silently.

Usage:
    python3 update_dashboard.py
    python3 update_dashboard.py --dashboard path/to/dashboard.jsx
"""
import json, glob, os, sys, re, argparse
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DASHBOARD = os.path.join(SCRIPT_DIR, "bkz_dashboard.jsx")
SUMMARY_PATH = os.path.join(SCRIPT_DIR, "..", "results", "summary.json")
CLOUD_DIR = os.path.join(SCRIPT_DIR, "..", "results", "cloud")
Q3329_DIR = os.path.join(SCRIPT_DIR, "..", "results", "q3329")


def load_local_groups():
    """Load completed groups from the main sweep summary."""
    groups = []
    if not os.path.exists(SUMMARY_PATH):
        return groups

    with open(SUMMARY_PATH) as f:
        summary = json.load(f)

    for key, g in summary.get("by_n_beta", {}).items():
        if g["num_seeds"] < 10:
            continue
        adv = np.array([])  # we don't have per-seed data here, use summary stats
        groups.append({
            "n": g["n"],
            "beta": g["beta"],
            "seeds": g["num_seeds"],
            "mean": round(g["mean_advantage"], 4),
            "std": round(g["std_advantage"], 4),
            "win": round(g["win_rate"] * 100, 1),
            "source": "local",
        })

    return groups


def load_cloud_groups():
    """Load cloud results by scanning the results/cloud/ directory."""
    groups = []
    if not os.path.isdir(CLOUD_DIR):
        return groups

    # Group files by (n, beta) — exclude q3329 files (they live in q3329/
    # but historically also synced into cloud/, and have a different format).
    by_group = {}
    for fp in glob.glob(os.path.join(CLOUD_DIR, "n*_beta*_seed*.json")):
        if "q3329" in fp:
            continue
        fname = os.path.basename(fp)
        try:
            parts = fname.replace(".json", "").split("_")
            n = int(parts[0].replace("n", ""))
            beta = int(parts[1].replace("beta", ""))
            key = (n, beta)
            if key not in by_group:
                by_group[key] = []
            with open(fp) as f:
                data = json.load(f)
            by_group[key].append(data["advantage"])
        except (ValueError, KeyError, json.JSONDecodeError):
            continue

    for (n, beta), advantages in sorted(by_group.items()):
        if len(advantages) < 5:
            continue
        adv = np.array(advantages)
        groups.append({
            "n": n,
            "beta": beta,
            "seeds": len(advantages),
            "mean": round(float(np.mean(adv)), 4),
            "std": round(float(np.std(adv, ddof=1)), 4),
            "win": round(float(np.sum(adv > 0) / len(adv) * 100), 1),
            "source": "cloud",
        })

    return groups


def merge_groups(local, cloud):
    """Merge local and cloud groups. Cloud overrides local for same (n, beta)."""
    by_key = {}
    for g in local:
        by_key[(g["n"], g["beta"])] = g
    for g in cloud:
        key = (g["n"], g["beta"])
        if key in by_key:
            # Keep whichever has more seeds
            if g["seeds"] > by_key[key]["seeds"]:
                by_key[key] = g
        else:
            by_key[key] = g

    return sorted(by_key.values(), key=lambda g: (g["n"], g["beta"]))


def format_groups_js(groups):
    """Format groups as a JavaScript array string."""
    lines = ["const GROUPS = ["]
    for g in groups:
        lines.append(
            f'  {{ n: {g["n"]}, beta: {g["beta"]}, seeds: {g["seeds"]}, '
            f'mean: {g["mean"]}, std: {g["std"]}, win: {g["win"]}, '
            f'd: null, source: "{g["source"]}" }},'
        )
    lines.append("];")
    return "\n".join(lines)


def update_dashboard(dashboard_path, groups_js):
    """Replace the GROUPS array in the dashboard file."""
    with open(dashboard_path, "r") as f:
        content = f.read()

    # Match the GROUPS array: from "const GROUPS = [" to the closing "];"
    pattern = r'const GROUPS = \[.*?\];'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print("ERROR: Could not find GROUPS array in dashboard file")
        return False

    new_content = content[:match.start()] + groups_js + content[match.end():]

    with open(dashboard_path, "w") as f:
        f.write(new_content)

    return True


def main():
    parser = argparse.ArgumentParser(description="Update dashboard with latest data")
    parser.add_argument("--dashboard", default=DEFAULT_DASHBOARD, help="Path to dashboard.jsx")
    parser.add_argument("--dry-run", action="store_true", help="Print data without writing")
    args = parser.parse_args()

    # Skip silently if dashboard doesn't exist
    if not os.path.exists(args.dashboard):
        return

    # Load data
    local = load_local_groups()
    cloud = load_cloud_groups()
    groups = merge_groups(local, cloud)

    if not groups:
        print("No data found to update")
        return

    groups_js = format_groups_js(groups)

    if args.dry_run:
        print(f"Found {len(groups)} groups ({len(local)} local, {len(cloud)} cloud)")
        print()
        print(groups_js)
        print()
        for g in groups:
            status = "✓" if g["seeds"] >= 100 else f"({g['seeds']})"
            print(f"  n={g['n']:>3} β={g['beta']:>2}: {g['mean']:+.4f} nats, "
                  f"win={g['win']:>5.1f}%, seeds={g['seeds']:>3} {status} [{g['source']}]")
        return

    if update_dashboard(args.dashboard, groups_js):
        total = sum(g["seeds"] for g in groups)
        complete = sum(1 for g in groups if g["seeds"] >= 100)
        print(f"Dashboard updated: {len(groups)} groups, {total} seeds, {complete} complete")


if __name__ == "__main__":
    main()
