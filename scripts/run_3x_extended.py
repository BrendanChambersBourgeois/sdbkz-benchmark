#!/usr/bin/env python3
"""
Extended 3x tour count experiments — 100 seeds each, 22 workers.

Tests whether BKZ at 3x the tour budget can match SD-BKZ at 1x.
4 groups run sequentially, seeds within each group run in parallel.

Usage:
    nohup python3 scripts/run_3x_extended.py > logs/3x_extended_stdout.log 2>&1 &

Output: results/3x_tours_extended/
"""
import datetime
import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _math_core import ln_fixed_point, log_clamp
from _seed_paths import seed_dir_for, seed_path_for
from generators import build_lwe_kannan, kannan_m
from log import get_logger

PIPELINE = get_logger("run_3x_extended")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# v1.3: tours3x seeds land at results/seeds/tours3x/q97/n{n}_beta{beta}/.
# The 3x_tours_extended/ legacy dir is kept for summary JSON writes.
OUTPUT_DIR = os.path.join(REPO_ROOT, "results", "3x_tours_extended")
os.makedirs(OUTPUT_DIR, exist_ok=True)
CLAMP_LOG_FILE = os.path.join(REPO_ROOT, "results", "clamp_events.jsonl")


def _log_clamp(ctx, position, raw_value):
    log_clamp(ctx, position, raw_value,
              script_name="run_3x_extended", log_path=CLAMP_LOG_FILE)

Q = 97
PRECISION = 250
NUM_WORKERS = 22

GROUPS = [
    {"n": 50, "beta": 30, "normal_tours": 70,  "triple_tours": 210},
    {"n": 60, "beta": 20, "normal_tours": 50,  "triple_tours": 150},
    {"n": 60, "beta": 30, "normal_tours": 70,  "triple_tours": 210},
    {"n": 70, "beta": 30, "normal_tours": 70,  "triple_tours": 210},
]


def _dln_from_gso(M, dim, m, ln_profile, clamp_ctx=""):
    start, size = m, dim - m

    def _safe_log_r(i):
        r = M.get_r(i, i)
        if r > 0:
            return 0.5 * math.log(r)
        _log_clamp(f"{clamp_ctx} active".strip(), i, r)
        return 0.5 * math.log(1e-300)

    gs_log_active = [_safe_log_r(i) for i in range(start, dim)]
    log_vol = sum(gs_log_active)
    rankin, cum = [], 0.0
    for idx, val in enumerate(gs_log_active):
        cum += val
        rankin.append(cum - ((idx + 1) / size) * log_vol)
    return float(np.mean(np.abs(np.array(rankin) - np.array(ln_profile))))


# -- Worker ------------------------------------------------------------------

def run_seed(args):
    n, beta, normal_tours, triple_tours, seed = args

    FPLLL.set_precision(PRECISION)
    FPLLL.set_random_seed(seed)

    m = kannan_m(n)
    dim = m + n + 1
    L, _, _ = build_lwe_kannan(n, m, Q, seed=seed)
    ln_p = ln_fixed_point(n + 1, beta)

    B_init = IntegerMatrix.from_matrix(L)
    LLL.reduction(B_init)

    result = {
        "n": n, "beta": beta, "seed": seed, "q": Q,
        "normal_tours": normal_tours, "triple_tours": triple_tours,
        "precision": PRECISION,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    # BKZ at 3x tours (record d(LN) at both 1x and 3x checkpoints)
    B = IntegerMatrix(B_init)
    bkz_dln = []
    t0 = time.time()
    for t in range(1, triple_tours + 1):
        param = BKZ.Param(beta, max_loops=1, flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT)
        BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)
        M = GSO.Mat(B)
        M.update_gso()
        bkz_dln.append(_dln_from_gso(M, dim, m, ln_p))
    result["bkz_time"] = time.time() - t0
    result["bkz_dln_per_tour"] = bkz_dln
    result["bkz_dln_at_normal_tours"] = bkz_dln[normal_tours - 1]
    result["bkz_dln_at_3x_tours"] = bkz_dln[-1]

    # SD-BKZ at normal tours
    B2 = IntegerMatrix(B_init)
    sd_dln = []
    t0 = time.time()
    for t in range(1, normal_tours + 1):
        param = BKZ.Param(beta, max_loops=1,
                          flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT | BKZ.SD_VARIANT)
        BKZ.reduction(B2, param, float_type="mpfr", precision=PRECISION)
        M2 = GSO.Mat(B2)
        M2.update_gso()
        sd_dln.append(_dln_from_gso(M2, dim, m, ln_p))
    result["sdbkz_time"] = time.time() - t0
    result["sdbkz_dln_per_tour"] = sd_dln
    result["sdbkz_dln_at_normal_tours"] = sd_dln[-1]

    # Comparisons
    result["advantage_equal_tours"] = result["bkz_dln_at_normal_tours"] - result["sdbkz_dln_at_normal_tours"]
    result["advantage_3x"] = result["bkz_dln_at_3x_tours"] - result["sdbkz_dln_at_normal_tours"]
    result["gap_closed"] = result["advantage_3x"] <= 0

    return result


# -- Main --------------------------------------------------------------------

def main():
    print("=" * 70)
    print("EXTENDED 3x TOUR COUNT EXPERIMENTS")
    print(f"  Workers: {NUM_WORKERS}")
    print(f"  Groups: {len(GROUPS)}")
    print("  Seeds per group: 100")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 70)
    print()

    PIPELINE.info(
        "3x tour extended start",
        cat="sweep",
        n_groups=len(GROUPS),
        groups=[{"n": g["n"], "beta": g["beta"]} for g in GROUPS],
        workers=NUM_WORKERS,
    )
    _t_start = time.time()

    for group in GROUPS:
        n, beta = group["n"], group["beta"]
        normal_tours = group["normal_tours"]
        triple_tours = group["triple_tours"]
        group_label = f"n={n}_beta={beta}"
        # v1.3: per-seed write dir under results/seeds/tours3x/; the
        # summary JSON still lands at the legacy OUTPUT_DIR so that
        # analysis tooling reading the summary files keeps working.
        group_dir = seed_dir_for("tours3x", n=n, beta=beta, base=REPO_ROOT)
        os.makedirs(group_dir, exist_ok=True)

        print(f"{'='*70}")
        print(f"GROUP: n={n}, β={beta}, BKZ@{triple_tours} vs SD-BKZ@{normal_tours}")
        print(f"{'='*70}")

        # Check what's already done
        completed = {}
        for seed in range(1, 101):
            outpath = seed_path_for(
                "tours3x", n=n, beta=beta, seed=seed, base=REPO_ROOT,
            )
            if os.path.exists(outpath):
                with open(outpath) as f:
                    completed[seed] = json.load(f)

        pending = [s for s in range(1, 101) if s not in completed]
        print(f"  Completed: {len(completed)}, Pending: {len(pending)}")

        if not pending:
            print("  All seeds done, skipping.")
            all_results = [completed[s] for s in sorted(completed)]
        else:
            tasks = [(n, beta, normal_tours, triple_tours, s) for s in pending]
            all_results = list(completed.values())

            t_start = time.time()
            done_count = len(completed)

            with Pool(processes=NUM_WORKERS, maxtasksperchild=5) as pool:
                for result in pool.imap_unordered(run_seed, tasks):
                    seed = result["seed"]
                    outpath = seed_path_for(
                "tours3x", n=n, beta=beta, seed=seed, base=REPO_ROOT,
            )
                    with open(outpath, "w") as f:
                        json.dump(result, f, indent=2)
                    all_results.append(result)
                    done_count += 1

                    closed = "YES" if result["gap_closed"] else "no"
                    elapsed = time.time() - t_start
                    rate = (done_count - len(completed)) / elapsed if elapsed > 0 else 0
                    eta = (100 - done_count) / rate if rate > 0 else 0

                    print(f"  [{done_count}/100] seed={seed:>3}  "
                          f"BKZ@{normal_tours}={result['bkz_dln_at_normal_tours']:.3f}  "
                          f"BKZ@{triple_tours}={result['bkz_dln_at_3x_tours']:.3f}  "
                          f"SDBKZ@{normal_tours}={result['sdbkz_dln_at_normal_tours']:.3f}  "
                          f"gap_closed={closed}  "
                          f"ETA={datetime.timedelta(seconds=int(eta))}", flush=True)

        # Summary
        advs_eq = [r["advantage_equal_tours"] for r in all_results]
        advs_3x = [r["advantage_3x"] for r in all_results]
        gaps_closed = [r["gap_closed"] for r in all_results]

        print()
        print(f"  --- {group_label} SUMMARY ({len(all_results)} seeds) ---")
        print(f"  BKZ@{normal_tours} vs SDBKZ@{normal_tours}: mean gap = {np.mean(advs_eq):.4f} nats")
        print(f"  BKZ@{triple_tours} vs SDBKZ@{normal_tours}: mean gap = {np.mean(advs_3x):.4f} nats")
        if np.mean(advs_eq) > 0:
            pct = (1 - np.mean(advs_3x) / np.mean(advs_eq)) * 100
            print(f"  Gap reduction: {pct:.1f}%")
        print(f"  Seeds where BKZ@{triple_tours} beats SDBKZ@{normal_tours}: "
              f"{sum(gaps_closed)}/{len(gaps_closed)}")

        if sum(gaps_closed) == 0:
            print(f"  >>> BKZ at {triple_tours} tours CANNOT match SDBKZ at {normal_tours}.")
        print()

        summary = {
            "experiment": "3x_tour_count_extended",
            "n": n, "beta": beta,
            "bkz_tours": triple_tours, "sdbkz_tours": normal_tours,
            "seeds": len(all_results),
            "mean_advantage_equal": float(np.mean(advs_eq)),
            "std_advantage_equal": float(np.std(advs_eq, ddof=1)),
            "mean_advantage_3x": float(np.mean(advs_3x)),
            "std_advantage_3x": float(np.std(advs_3x, ddof=1)),
            "gap_closed_count": int(sum(gaps_closed)),
            "win_rate_equal": float(np.mean(np.array(advs_eq) > 0)),
            "win_rate_3x": float(np.mean(np.array(advs_3x) > 0)),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        with open(os.path.join(OUTPUT_DIR, f"summary_n{n}_beta{beta}.json"), "w") as f:
            json.dump(summary, f, indent=2)

    print("=" * 70)
    print("ALL GROUPS COMPLETE")
    print("=" * 70)

    PIPELINE.info(
        "3x tour extended complete",
        cat="sweep",
        elapsed_s=int(time.time() - _t_start),
    )

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
