#!/usr/bin/env python3
"""Aggregate fplll version-sensitivity runs into a single comparison.

Reads per-seed JSONs from each fplll version's output dir + the
matching seeds from the paper's main sweep (fplll 5.5.0), produces:

  - per-seed advantages table across versions
  - mean / stdev / win rate per version
  - Welch t comparison of each legacy version vs 5.5.0 baseline
  - verdict JSON in results/paper_claims/fplll_version_robustness.json

Usage: python3 analysis/fplll_sensitivity_compare.py
"""
import os, sys, json, glob, statistics, math

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from log import get_logger  # noqa: E402
PIPELINE = get_logger("fplll_sensitivity_compare")

VERSIONS = [
    ("5.4.3", os.path.join(REPO, "results", "fplll543_sensitivity")),
    ("5.4.4", os.path.join(REPO, "results", "fplll544_sensitivity")),
    ("5.4.5", os.path.join(REPO, "results", "fplll54_sensitivity")),
]
BASELINE_VER = "5.5.0"
BASELINE_DIR = os.path.join(REPO, "results", "raw")
SEEDS = list(range(1, 6))
N, BETA = 100, 30


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _seeds_for_dir(out_dir, seeds, pattern):
    advs = {}
    for s in seeds:
        p = os.path.join(out_dir, pattern.format(seed=s))
        r = _load(p)
        if r is not None and "advantage" in r:
            advs[s] = r["advantage"]
    return advs


def _stat(advs):
    if len(advs) < 2:
        return {"n": len(advs), "mean": advs[0] if advs else None,
                "stdev": None, "wins": sum(1 for a in advs if a > 0)}
    return {
        "n": len(advs),
        "mean": statistics.mean(advs),
        "stdev": statistics.stdev(advs),
        "wins": sum(1 for a in advs if a > 0),
    }


def _welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    ma, sa = statistics.mean(a), statistics.stdev(a)
    mb, sb = statistics.mean(b), statistics.stdev(b)
    se = math.sqrt(sa**2/len(a) + sb**2/len(b))
    return (ma - mb) / se if se > 0 else None


def main():
    baseline_advs = _seeds_for_dir(
        BASELINE_DIR, SEEDS, f"n{N}_beta{BETA}_seed{{seed}}.json"
    )
    legacy = {}
    for ver, d in VERSIONS:
        legacy[ver] = _seeds_for_dir(
            d, SEEDS, f"n{N}_beta{BETA}_q97_seed{{seed}}.json"
        )

    print("=" * 70)
    print(f"fplll version sensitivity — n={N} β={BETA} q=97 250-bit MPFR")
    print(f"Baseline: fplll {BASELINE_VER} (paper main-sweep, results/raw/)")
    print(f"Seeds compared: {SEEDS}")
    print("=" * 70)

    header = f"{'seed':>4} | " + f"{BASELINE_VER:>10} | " + \
             " | ".join(f"{v:>10}" for v, _ in VERSIONS)
    print(header)
    print("-" * len(header))
    for s in SEEDS:
        row = [f"{s:>4}", f"{baseline_advs.get(s, float('nan')):+10.4f}"
               if s in baseline_advs else f"{'--':>10}"]
        for ver, _ in VERSIONS:
            advs = legacy[ver]
            row.append(f"{advs.get(s, float('nan')):+10.4f}"
                       if s in advs else f"{'pending':>10}")
        print(" | ".join(row))
    print()

    summary = {
        "comparison": {"seeds": SEEDS, "n": N, "beta": BETA, "q": 97,
                       "precision_bits": 250},
        "baseline": {"fplll_version": BASELINE_VER,
                     "source": "results/raw/ (paper main-sweep Docker)",
                     **_stat(list(baseline_advs.values())),
                     "per_seed": {s: baseline_advs[s] for s in baseline_advs}},
        "legacy": {},
    }
    print(f"  {BASELINE_VER:>10}: {summary['baseline']}")
    for ver, _ in VERSIONS:
        advs = legacy[ver]
        stat = _stat(list(advs.values()))
        welch = _welch(list(advs.values()), list(baseline_advs.values()))
        summary["legacy"][ver] = {**stat,
                                  "welch_t_vs_5_5_0": welch,
                                  "per_seed": advs}
        print(f"  {ver:>10}: {stat}  Welch t vs {BASELINE_VER}: {welch}")

    all_means = [summary["baseline"]["mean"]] + \
                [summary["legacy"][v]["mean"] for v, _ in VERSIONS
                 if summary["legacy"][v]["mean"] is not None]
    if all_means and None not in all_means:
        spread = max(all_means) - min(all_means)
        summary["cross_version_mean_spread_nats"] = spread
        print(f"\nCross-version mean spread: {spread:.4f} nats "
              f"(max - min across {len(all_means)} versions)")

    # Guard: refuse to overwrite the claim JSON with a data-empty run.
    # If every legacy version has zero seeds, the comparison is vacuous
    # and would clobber any real prior file.
    any_legacy_data = any(
        summary["legacy"][v]["n"] > 0 for v, _ in VERSIONS
    )
    out_path = os.path.join(REPO, "results", "paper_claims",
                            "fplll_version_robustness.json")
    if not any_legacy_data:
        print("\nNo legacy-version seeds found. Skipping claim JSON write "
              "(pass --force to override).")
        PIPELINE.warning(
            "fplll sensitivity compare skipped — no legacy data",
            cat="sweep", versions=[v for v, _ in VERSIONS],
        )
        if "--force" not in sys.argv:
            return

    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {out_path}")
    PIPELINE.info(
        "fplll sensitivity compare complete",
        cat="sweep",
        baseline_n=summary["baseline"]["n"],
        legacy_versions=[v for v, _ in VERSIONS],
        spread_nats=summary.get("cross_version_mean_spread_nats"),
        out_path=out_path,
    )


if __name__ == "__main__":
    main()
