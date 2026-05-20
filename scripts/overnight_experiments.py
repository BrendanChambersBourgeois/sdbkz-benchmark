#!/usr/bin/env python3
"""
Two overnight experiments wrapped for unattended runs:

EXPERIMENT 1: 3x tour count test (paper §5.3)
  - 10 seeds, n=60, beta=30, BKZ at 210 tours vs SD-BKZ at 70 tours
  - Question: can BKZ close the gap with 3x more computation?
  - Output: results/seeds/tours3x/q97/n060_beta30/ (post-v2.0.0 layout)

EXPERIMENT 2: Profile-position decomposition (all completed main-sweep seeds)
  - For each completed seed, split Rankin profile into head/mid/tail thirds
  - Measure where in the profile SD-BKZ improves most
  - Output: results/profile_decomposition.json

Run with:
    nice -n 19 python3 scripts/overnight_experiments.py &

Or run individually:
    nice -n 19 python3 scripts/overnight_experiments.py --3x-only
    nice -n 19 python3 scripts/overnight_experiments.py --profile-only
"""
import datetime
import glob
import json
import math
import os
import sys
import time

import numpy as np
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _math_core import (
    build_lwe_kannan,
    ln_fixed_point,
    log_clamp,
    metrics_from_gso,
)
from log import get_logger

PIPELINE = get_logger("overnight_experiments")

# BASE is the repo root. Two dirname() calls because this script lives
# at scripts/overnight_experiments.py — the first goes to scripts/, the
# second goes to the repo root.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE, "results", "raw")
CLAMP_LOG_FILE = os.path.join(BASE, "results", "clamp_events.jsonl")


def _log_clamp(ctx, position, raw_value):
    log_clamp(ctx, position, raw_value,
              script_name="overnight_experiments", log_path=CLAMP_LOG_FILE)


def _metrics_from_gso(M, dim, m, ln_profile, full=False, clamp_ctx=""):
    return metrics_from_gso(
        M, dim, m, ln_profile, full=full, clamp_ctx=clamp_ctx,
        log_clamp_fn=_log_clamp,
    )


# ═════════════════════════════════════════════════════════════════════════
# EXPERIMENT 1: 3x Tour Count Test
# ═════════════════════════════════════════════════════════════════════════

def run_3x_tour_test():
    """Run BKZ for 210 tours and SD-BKZ for 70 tours. Compare."""
    print("=" * 70)
    print("EXPERIMENT 1: 3x Tour Count Test")
    print("BKZ at 210 tours vs SD-BKZ at 70 tours, n=60, beta=30")
    print("=" * 70)

    N, BETA, Q = 60, 30, 97
    SDBKZ_TOURS = 70       # normal
    BKZ_TOURS = 210        # 3x normal
    PRECISION = 250
    SEEDS = list(range(1, 11))  # 10 seeds

    out_dir = os.path.join(BASE, "results", "3x_tours")
    os.makedirs(out_dir, exist_ok=True)

    results = []

    for seed in SEEDS:
        outpath = os.path.join(out_dir, f"n{N}_beta{BETA}_seed{seed}.json")
        if os.path.exists(outpath):
            print(f"  Seed {seed}: already done, skipping.")
            with open(outpath) as f:
                results.append(json.load(f))
            continue

        print(f"  Seed {seed}: running...", end=" ", flush=True)
        FPLLL.set_precision(PRECISION)
        FPLLL.set_random_seed(seed)

        m = N * 2
        dim = m + N + 1
        L, _, _ = build_lwe_kannan(N, m, Q, seed=seed)
        ln_p = ln_fixed_point(N + 1, BETA)

        # LLL once
        B_init = IntegerMatrix.from_matrix(L)
        LLL.reduction(B_init)
        M_init = GSO.Mat(B_init)
        M_init.update_gso()

        row = {"seed": seed, "n": N, "beta": BETA}

        # --- BKZ at 3x tours ---
        B = IntegerMatrix(B_init)
        bkz_dln = []
        t0 = time.time()
        for t in range(BKZ_TOURS):
            param = BKZ.Param(BETA, max_loops=1,
                              flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT)
            BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)
            M = GSO.Mat(B)
            M.update_gso()
            metrics = _metrics_from_gso(M, dim, m, ln_p)
            bkz_dln.append(metrics["dln"])
        row["bkz_time"] = time.time() - t0
        row["bkz_dln_per_tour"] = bkz_dln
        row["bkz_210_final"] = bkz_dln[-1]
        row["bkz_70_final"] = bkz_dln[69]   # what BKZ had at normal tour count

        # --- SD-BKZ at normal tours ---
        B2 = IntegerMatrix(B_init)
        sd_dln = []
        t0 = time.time()
        for t in range(SDBKZ_TOURS):
            param = BKZ.Param(BETA, max_loops=1,
                              flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT | BKZ.SD_VARIANT)
            BKZ.reduction(B2, param, float_type="mpfr", precision=PRECISION)
            M2 = GSO.Mat(B2)
            M2.update_gso()
            metrics = _metrics_from_gso(M2, dim, m, ln_p)
            sd_dln.append(metrics["dln"])
        row["sdbkz_time"] = time.time() - t0
        row["sdbkz_dln_per_tour"] = sd_dln
        row["sdbkz_70_final"] = sd_dln[-1]

        # --- Comparisons ---
        row["gap_normal"] = bkz_dln[69] - sd_dln[-1]    # BKZ@70 vs SDBKZ@70
        row["gap_3x"] = bkz_dln[-1] - sd_dln[-1]        # BKZ@210 vs SDBKZ@70
        row["bkz_closed_gap"] = row["gap_normal"] - row["gap_3x"]

        with open(outpath, "w") as f:
            json.dump(row, f, indent=2)
        results.append(row)

        print(f"BKZ@70={bkz_dln[69]:.3f}, BKZ@210={bkz_dln[-1]:.3f}, "
              f"SDBKZ@70={sd_dln[-1]:.3f}")

    # Summary
    if results:
        gaps_normal = [r["gap_normal"] for r in results]
        gaps_3x = [r["gap_3x"] for r in results]
        closed = [r["bkz_closed_gap"] for r in results]

        print()
        print("=" * 70)
        print("3x TOUR COUNT RESULTS")
        print("=" * 70)
        print(f"  BKZ@70 vs SDBKZ@70:   mean gap = {np.mean(gaps_normal):.4f} nats (SDBKZ wins)")
        print(f"  BKZ@210 vs SDBKZ@70:  mean gap = {np.mean(gaps_3x):.4f} nats", end="")
        if np.mean(gaps_3x) > 0:
            print(" (SDBKZ STILL wins at 1/3 the runtime)")
        else:
            print(" (BKZ closed the gap)")
        print(f"  Gap closed by 3x:     {np.mean(closed):.4f} nats "
              f"({np.mean(closed)/np.mean(gaps_normal)*100:.0f}% of original gap)")
        print(f"  Seeds where BKZ@210 beats SDBKZ@70: "
              f"{sum(1 for g in gaps_3x if g < 0)}/{len(gaps_3x)}")
        print()

        # The key question
        if all(g > 0 for g in gaps_3x):
            print("  >>> DEFINITIVE: BKZ at 3x tours CANNOT match SDBKZ at 1x.")
            print("  >>> Section 5.3 upgrades to 'A Capability Difference.'")
        elif np.mean(gaps_3x) > 0:
            print("  >>> MOSTLY HOLDS: BKZ at 3x tours still behind in most seeds.")
        else:
            print("  >>> BKZ CAN close the gap. This is a speed difference, not capability.")

        summary = {
            "experiment": "3x_tour_count",
            "n": N, "beta": BETA,
            "bkz_tours": BKZ_TOURS, "sdbkz_tours": SDBKZ_TOURS,
            "seeds": len(results),
            "mean_gap_normal": float(np.mean(gaps_normal)),
            "mean_gap_3x": float(np.mean(gaps_3x)),
            "mean_gap_closed": float(np.mean(closed)),
            "pct_closed": float(np.mean(closed)/np.mean(gaps_normal)*100),
            "sdbkz_still_wins": sum(1 for g in gaps_3x if g > 0),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        with open(os.path.join(out_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
        print(f"  Saved: {out_dir}/summary.json")


# ═════════════════════════════════════════════════════════════════════════
# EXPERIMENT 2: Profile-Position Decomposition
# ═════════════════════════════════════════════════════════════════════════

def run_profile_decomposition():
    """For each completed seed, decompose where in the Rankin profile SD-BKZ improves."""
    print()
    print("=" * 70)
    print("EXPERIMENT 2: Profile-Position Decomposition (all seeds)")
    print("=" * 70)

    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "n*_beta*_seed*.json")))
    if not raw_files:
        print("No raw results found.")
        return

    group_results = {}

    for fp in raw_files:
        with open(fp) as f:
            try:
                d = json.load(f)
            except json.JSONDecodeError:
                continue

        if d.get("status") != "completed":
            continue
        if "rankin_profile_bkz" not in d or "rankin_profile_sdbkz" not in d:
            continue

        n, beta = d["n"], d["beta"]
        key = f"n={n}_beta={beta}"

        rp_bkz = np.array(d["rankin_profile_bkz"])
        rp_sd = np.array(d["rankin_profile_sdbkz"])

        size = len(rp_bkz)
        if size != len(rp_sd):
            continue

        third = size // 3

        # Per-position absolute difference: negative means SD-BKZ closer to 0
        # But profiles aren't centered at 0 — we need the fixed point.
        # Compute |rp_bkz - fp| - |rp_sd - fp| at each position
        # = where SD-BKZ is closer to the fixed point
        ln_p = ln_fixed_point(n + 1, beta)
        if len(ln_p) != size:
            continue

        fp_arr = np.array(ln_p)
        bkz_dist = np.abs(rp_bkz - fp_arr)
        sd_dist = np.abs(rp_sd - fp_arr)
        improvement = bkz_dist - sd_dist  # positive = SD-BKZ closer

        head_imp = float(np.mean(improvement[:third]))
        mid_imp = float(np.mean(improvement[third:2*third]))
        tail_imp = float(np.mean(improvement[2*third:]))

        head_win = float(np.mean(improvement[:third] > 0))
        mid_win = float(np.mean(improvement[third:2*third] > 0))
        tail_win = float(np.mean(improvement[2*third:] > 0))

        if key not in group_results:
            group_results[key] = {"n": n, "beta": beta, "seeds": [],
                                  "head": [], "mid": [], "tail": [],
                                  "head_wr": [], "mid_wr": [], "tail_wr": []}

        group_results[key]["seeds"].append(d["seed"])
        group_results[key]["head"].append(head_imp)
        group_results[key]["mid"].append(mid_imp)
        group_results[key]["tail"].append(tail_imp)
        group_results[key]["head_wr"].append(head_win)
        group_results[key]["mid_wr"].append(mid_win)
        group_results[key]["tail_wr"].append(tail_win)

    print(f"\nAnalysed {sum(len(g['seeds']) for g in group_results.values())} seeds "
          f"across {len(group_results)} groups\n")

    print(f"{'Group':<16} {'Seeds':>5}  {'Head':>7} {'Mid':>7} {'Tail':>7}  "
          f"{'Head%':>6} {'Mid%':>6} {'Tail%':>6}  {'Largest':>8}")
    print("-" * 85)

    summary = {}
    for key in sorted(group_results.keys()):
        g = group_results[key]
        n_seeds = len(g["seeds"])
        h = np.mean(g["head"])
        m = np.mean(g["mid"])
        t = np.mean(g["tail"])
        total = h + m + t
        h_pct = h / total * 100 if total > 0 else 0
        m_pct = m / total * 100 if total > 0 else 0
        t_pct = t / total * 100 if total > 0 else 0

        h_wr = np.mean(g["head_wr"]) * 100
        m_wr = np.mean(g["mid_wr"]) * 100
        t_wr = np.mean(g["tail_wr"]) * 100

        largest = "HEAD" if h >= m and h >= t else "MID" if m >= t else "TAIL"

        print(f"{key:<16} {n_seeds:>5}  {h:>7.3f} {m:>7.3f} {t:>7.3f}  "
              f"{h_pct:>5.0f}% {m_pct:>5.0f}% {t_pct:>5.0f}%  {largest:>8}")

        summary[key] = {
            "n": g["n"], "beta": g["beta"], "num_seeds": n_seeds,
            "mean_head_improvement": float(h),
            "mean_mid_improvement": float(m),
            "mean_tail_improvement": float(t),
            "pct_head": float(h_pct),
            "pct_mid": float(m_pct),
            "pct_tail": float(t_pct),
            "head_position_win_rate": float(h_wr),
            "mid_position_win_rate": float(m_wr),
            "tail_position_win_rate": float(t_wr),
            "largest_region": largest,
        }

    print()

    outpath = os.path.join(BASE, "results", "profile_decomposition.json")
    with open(outpath, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved: {outpath}")


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    three_x = "--3x-only" in sys.argv or "--3x" in sys.argv
    profile = "--profile-only" in sys.argv or "--profile" in sys.argv
    both = not three_x and not profile

    PIPELINE.info(
        "overnight start",
        cat="sweep",
        run_3x=bool(both or three_x),
        run_profile=bool(both or profile),
    )
    t_start = time.time()

    if both or profile:
        # Profile decomposition is fast (just reads existing JSONs)
        run_profile_decomposition()

    if both or three_x:
        # 3x tour test takes ~30 min (10 seeds × ~3 min each)
        run_3x_tour_test()

    PIPELINE.info(
        "overnight complete",
        cat="sweep",
        elapsed_s=int(time.time() - t_start),
    )
