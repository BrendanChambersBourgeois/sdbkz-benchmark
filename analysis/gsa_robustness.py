#!/usr/bin/env python3
"""Compute d(GSA) for every seed and produce a summary JSON.

Mirrors the d(LN) metric (mean absolute distance to reference Rankin
profile) but uses the GSA fixed point instead of Li-Nguyen. Reads the
stored rankin_profile_bkz / rankin_profile_sdbkz from each seed JSON
and computes distance post-hoc — no re-running experiments.

Usage:
    python3 analysis/gsa_robustness.py [--output results/dGSA_summary.json]

Output schema:
{
  "generated": "ISO timestamp",
  "metric": "mean_absolute_distance",
  "note": "...",
  "total_seeds": N,
  "correlation_with_dLN": { "pearson_r": ..., "p_value": ... },
  "groups": {
    "n50_beta20": {
      "n": 50, "beta": 20, "seeds": 100,
      "dLN_mean_advantage": ..., "dGSA_mean_advantage": ...,
      "dLN_win_rate": ..., "dGSA_win_rate": ...,
      "same_sign": true/false,
      "per_seed_sign_agreement": 0.98,
    }, ...
  },
  "reversals": [ ... groups where mean advantage sign differs ... ]
}
"""
import argparse
import datetime
import json
import math
import os
import sys

import numpy as np
from scipy import stats as sp_stats

# Use the canonical implementations from analysis/_data.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from _data import gsa_fixed_point, ln_fixed_point, load_all_seeds

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("gsa_robustness")


def d_metric(profile, reference):
    """Mean absolute distance — same as sweep_parallel._metrics_from_gso."""
    return float(np.mean(np.abs(np.array(profile) - np.array(reference))))


def main():
    PIPELINE.info("gsa_robustness start", cat="analysis")
    parser = argparse.ArgumentParser(
        description="Compute d(GSA) robustness check across all seeds."
    )
    parser.add_argument(
        "--output", default="results/dGSA_summary.json",
        help="Output path (default: results/dGSA_summary.json)"
    )
    parser.add_argument(
        "--campaign", default="main",
        help="Manifest campaign (default: main). Set to empty string to "
        "opt into the pre-v1.3 --seed-dirs globber for non-standard "
        "layouts.",
    )
    parser.add_argument(
        "--seed-dirs", nargs="+",
        default=["results/raw", "results/cloud"],
        help="Legacy override: directories containing seed JSONs. Used "
        "only when --campaign is empty.",
    )
    args = parser.parse_args()

    if args.campaign:
        groups = load_all_seeds(campaign=args.campaign)
    else:
        groups = load_all_seeds(*args.seed_dirs)
    if not groups:
        print("No seeds found.", file=sys.stderr)
        sys.exit(1)

    all_ln_advs = []
    all_gsa_advs = []
    group_results = {}
    reversals = []

    for (n, beta), seeds in sorted(groups.items()):
        ln_advantages = []
        gsa_advantages = []
        sign_agree = 0

        for s in seeds:
            rp_bkz = s.get("rankin_profile_bkz")
            rp_sd = s.get("rankin_profile_sdbkz")
            if rp_bkz is None or rp_sd is None:
                continue

            size = n + 1
            fp_ln = ln_fixed_point(size, beta)
            fp_gsa = gsa_fixed_point(size, beta)

            if len(fp_ln) != len(rp_bkz) or len(fp_gsa) != len(rp_bkz):
                continue

            d_bkz_ln = d_metric(rp_bkz, fp_ln)
            d_sd_ln = d_metric(rp_sd, fp_ln)
            d_bkz_gsa = d_metric(rp_bkz, fp_gsa)
            d_sd_gsa = d_metric(rp_sd, fp_gsa)

            adv_ln = d_bkz_ln - d_sd_ln
            adv_gsa = d_bkz_gsa - d_sd_gsa

            ln_advantages.append(adv_ln)
            gsa_advantages.append(adv_gsa)

            if (adv_ln > 0) == (adv_gsa > 0):
                sign_agree += 1

        if not ln_advantages:
            continue

        ln_arr = np.array(ln_advantages)
        gsa_arr = np.array(gsa_advantages)

        # Cross-check: dLN advantage should match stored advantage
        stored_advs = [s["advantage"] for s in seeds
                       if "advantage" in s and s.get("rankin_profile_bkz")]
        if stored_advs:
            stored_mean = float(np.mean(stored_advs))
            recomputed_mean = float(np.mean(ln_arr))
            if abs(stored_mean - recomputed_mean) > 0.01:
                print(f"  WARNING n={n} β={beta}: stored advantage mean "
                      f"{stored_mean:.4f} != recomputed {recomputed_mean:.4f}",
                      file=sys.stderr)

        mean_ln = float(np.mean(ln_arr))
        mean_gsa = float(np.mean(gsa_arr))
        same_sign = (mean_ln > 0) == (mean_gsa > 0) or (mean_ln == 0 and mean_gsa == 0)

        key = f"n{n}_beta{beta}"
        entry = {
            "n": n,
            "beta": beta,
            "seeds": len(ln_advantages),
            "dLN_mean_advantage": round(mean_ln, 4),
            "dLN_std": round(float(np.std(ln_arr, ddof=1)), 4),
            "dLN_win_rate": round(float(np.mean(ln_arr > 0)), 4),
            "dGSA_mean_advantage": round(mean_gsa, 4),
            "dGSA_std": round(float(np.std(gsa_arr, ddof=1)), 4),
            "dGSA_win_rate": round(float(np.mean(gsa_arr > 0)), 4),
            "same_sign": same_sign,
            "per_seed_sign_agreement": round(sign_agree / len(ln_advantages), 4),
        }
        group_results[key] = entry

        if not same_sign:
            reversals.append({
                "group": key,
                "n": n,
                "beta": beta,
                "dLN_mean": round(mean_ln, 4),
                "dGSA_mean": round(mean_gsa, 4),
                "dLN_winner": "SDBKZ" if mean_ln > 0 else "BKZ",
                "dGSA_winner": "SDBKZ" if mean_gsa > 0 else "BKZ",
            })

        all_ln_advs.extend(ln_advantages)
        all_gsa_advs.extend(gsa_advantages)

    # Global correlation
    ln_all = np.array(all_ln_advs)
    gsa_all = np.array(all_gsa_advs)
    r, p = sp_stats.pearsonr(ln_all, gsa_all)

    summary = {
        "generated": datetime.datetime.now(datetime.UTC).isoformat(),
        "metric": "mean_absolute_distance",
        "note": (
            "d(LN) = mean|profile - LN_fixed_point|, "
            "d(GSA) = mean|profile - GSA_fixed_point|. "
            "Advantage = d_BKZ - d_SDBKZ (positive = SD-BKZ closer to reference)."
        ),
        "total_seeds": len(all_ln_advs),
        "total_groups": len(group_results),
        "correlation_with_dLN": {
            "pearson_r": round(float(r), 6),
            "p_value": float(p),
        },
        "groups": group_results,
        "reversals": reversals,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n{'Group':>15s}  {'Seeds':>5s}  {'d(LN) adv':>10s}  "
          f"{'d(GSA) adv':>10s}  {'LN win%':>7s}  {'GSA win%':>7s}  {'Agree':>6s}")
    print("-" * 72)
    for key, g in sorted(group_results.items(),
                         key=lambda x: (x[1]["n"], x[1]["beta"])):
        marker = "  <<<" if not g["same_sign"] else ""
        print(f"n={g['n']:>3d} β={g['beta']:>2d}  {g['seeds']:>5d}  "
              f"{g['dLN_mean_advantage']:>+10.4f}  {g['dGSA_mean_advantage']:>+10.4f}  "
              f"{g['dLN_win_rate']*100:>6.0f}%  {g['dGSA_win_rate']*100:>6.0f}%"
              f"{marker}")
    print("-" * 72)
    print(f"Pearson r = {r:.6f} (p = {p:.2e})")
    print(f"Total: {len(all_ln_advs)} seeds, {len(group_results)} groups, "
          f"{len(reversals)} reversal(s)")
    if reversals:
        print("\nReversals:")
        for rev in reversals:
            print(f"  {rev['group']}: d(LN) → {rev['dLN_winner']}, "
                  f"d(GSA) → {rev['dGSA_winner']}")

    print(f"\nWritten to {args.output}")
    PIPELINE.info("gsa_robustness complete", cat="analysis",
                  total_seeds=len(all_ln_advs),
                  groups=len(group_results),
                  reversals=len(reversals),
                  output=args.output)


if __name__ == "__main__":
    main()
