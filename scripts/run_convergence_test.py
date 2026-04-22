#!/usr/bin/env python3
"""
High tour count convergence test — n=90, β=30, 500 tours, 20 seeds.

Shows both BKZ and SD-BKZ d(LN) trajectories converge toward the same
fixed-point profile shape. Addresses reviewer concern that SD-BKZ may
converge to a different fixed point than the Li-Nguyen BKZ fixed point.

Usage:
    nohup python3 scripts/run_convergence_test.py > logs/convergence_stdout.log 2>&1 &

Output: results/convergence/
"""
import os, sys, json, math, time, datetime
import numpy as np
from multiprocessing import Pool
from fpylll import IntegerMatrix, LLL, BKZ, FPLLL, GSO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger, new_run_id, get_run_id
from _math_core import build_lwe_kannan, log_clamp, ln_fixed_point
from _seed_paths import seed_path_for, seed_dir_for
PIPELINE = get_logger("run_convergence_test")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Legacy dir preserved for summary JSON writes; per-seed writes are
# redirected below to seed_path_for("convergence", ...) once N/BETA/
# MAX_TOURS are known.
OUTPUT_DIR = os.path.join(REPO_ROOT, "results", "convergence")
os.makedirs(OUTPUT_DIR, exist_ok=True)
CLAMP_LOG_FILE = os.path.join(REPO_ROOT, "results", "clamp_events.jsonl")


def _log_clamp(ctx, position, raw_value):
    log_clamp(ctx, position, raw_value,
              script_name="run_convergence_test", log_path=CLAMP_LOG_FILE)

Q = 97
PRECISION = 250
NUM_WORKERS = 22
N = 90
BETA = 30
MAX_TOURS = 500
NUM_SEEDS = 20


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


def run_seed(seed):
    FPLLL.set_precision(PRECISION)
    FPLLL.set_random_seed(seed)

    n, beta = N, BETA
    m = n * 2
    dim = m + n + 1
    L, _, _ = build_lwe_kannan(n, m, Q, seed=seed)
    ln_p = ln_fixed_point(n + 1, beta)

    B_init = IntegerMatrix.from_matrix(L)
    LLL.reduction(B_init)

    result = {
        "experiment": "convergence_test",
        "n": n, "beta": beta, "seed": seed, "q": Q,
        "max_tours": MAX_TOURS, "precision": PRECISION,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # BKZ at 500 tours
    B = IntegerMatrix(B_init)
    bkz_dln = []
    t0 = time.time()
    for t in range(1, MAX_TOURS + 1):
        param = BKZ.Param(beta, max_loops=1, flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT)
        BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)
        M = GSO.Mat(B)
        M.update_gso()
        bkz_dln.append(_dln_from_gso(M, dim, m, ln_p))
    result["bkz_time"] = time.time() - t0
    result["bkz_dln_per_tour"] = bkz_dln

    # SD-BKZ at 500 tours
    B2 = IntegerMatrix(B_init)
    sd_dln = []
    t0 = time.time()
    for t in range(1, MAX_TOURS + 1):
        param = BKZ.Param(beta, max_loops=1,
                          flags=BKZ.MAX_LOOPS | BKZ.AUTO_ABORT | BKZ.SD_VARIANT)
        BKZ.reduction(B2, param, float_type="mpfr", precision=PRECISION)
        M2 = GSO.Mat(B2)
        M2.update_gso()
        sd_dln.append(_dln_from_gso(M2, dim, m, ln_p))
    result["sdbkz_time"] = time.time() - t0
    result["sdbkz_dln_per_tour"] = sd_dln

    # Final values
    result["bkz_final_dln"] = bkz_dln[-1]
    result["sdbkz_final_dln"] = sd_dln[-1]
    result["advantage"] = bkz_dln[-1] - sd_dln[-1]

    # Convergence: d(LN) at tour 70 vs 500
    result["bkz_dln_at_70"] = bkz_dln[69]
    result["sdbkz_dln_at_70"] = sd_dln[69]
    result["bkz_improvement_70_to_500"] = bkz_dln[69] - bkz_dln[-1]
    result["sdbkz_improvement_70_to_500"] = sd_dln[69] - sd_dln[-1]

    return result


def main():
    if not get_run_id():
        new_run_id()

    PIPELINE.info(
        "convergence start",
        cat="sweep",
        n=N, beta=BETA, tours=MAX_TOURS, n_seeds=NUM_SEEDS,
        workers=NUM_WORKERS, q=Q, precision=PRECISION,
        output_dir=OUTPUT_DIR,
    )
    _t_start = time.time()

    # Check completed
    completed = {}
    for seed in range(1, NUM_SEEDS + 1):
        outpath = seed_path_for(
            "convergence", n=N, beta=BETA, seed=seed,
            max_tours=MAX_TOURS, base=REPO_ROOT,
        )
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        if os.path.exists(outpath):
            with open(outpath) as f:
                completed[seed] = json.load(f)

    pending = [s for s in range(1, NUM_SEEDS + 1) if s not in completed]
    PIPELINE.info(
        "seed scan",
        cat="sweep",
        completed=len(completed), pending=len(pending),
    )

    if not pending:
        PIPELINE.info("all seeds done", cat="sweep", seeds=len(completed))
        all_results = [completed[s] for s in sorted(completed)]
    else:
        all_results = list(completed.values())
        t_start = time.time()
        done_count = len(completed)

        with Pool(processes=NUM_WORKERS, maxtasksperchild=5) as pool:
            for result in pool.imap_unordered(run_seed, pending):
                seed = result["seed"]
                outpath = seed_path_for(
                    "convergence", n=N, beta=BETA, seed=seed,
                    max_tours=MAX_TOURS, base=REPO_ROOT,
                )
                os.makedirs(os.path.dirname(outpath), exist_ok=True)
                with open(outpath, "w") as f:
                    json.dump(result, f, indent=2)
                all_results.append(result)
                done_count += 1

                elapsed = time.time() - t_start
                rate = (done_count - len(completed)) / elapsed if elapsed > 0 else 0
                eta_s = int((NUM_SEEDS - done_count) / rate) if rate > 0 else 0

                PIPELINE.info(
                    "seed done",
                    cat="sweep",
                    done=done_count, total=NUM_SEEDS, seed=seed,
                    bkz_final=round(result["bkz_final_dln"], 4),
                    sdbkz_final=round(result["sdbkz_final_dln"], 4),
                    advantage=round(result["advantage"], 4),
                    bkz_improvement_70_to_final=round(result["bkz_improvement_70_to_500"], 4),
                    sdbkz_improvement_70_to_final=round(result["sdbkz_improvement_70_to_500"], 4),
                    eta_s=eta_s,
                )

    bkz_final = np.array([r["bkz_final_dln"] for r in all_results])
    sd_final = np.array([r["sdbkz_final_dln"] for r in all_results])
    bkz_70 = np.array([r["bkz_dln_at_70"] for r in all_results])
    sd_70 = np.array([r["sdbkz_dln_at_70"] for r in all_results])
    advs = np.array([r["advantage"] for r in all_results])

    summary = {
        "experiment": "convergence_test",
        "n": N, "beta": BETA, "max_tours": MAX_TOURS,
        "seeds": len(all_results),
        "bkz_mean_dln_70": float(np.mean(bkz_70)),
        "bkz_mean_dln_500": float(np.mean(bkz_final)),
        "sdbkz_mean_dln_70": float(np.mean(sd_70)),
        "sdbkz_mean_dln_500": float(np.mean(sd_final)),
        "mean_advantage_500": float(np.mean(advs)),
        "win_rate_500": float(np.mean(advs > 0)),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(os.path.join(OUTPUT_DIR, "summary_convergence.json"), "w") as f:
        json.dump(summary, f, indent=2)

    PIPELINE.info(
        "convergence summary",
        cat="sweep",
        n=N, beta=BETA, tours=MAX_TOURS, seeds=len(all_results),
        bkz_mean_dln_70=round(float(np.mean(bkz_70)), 4),
        bkz_std_dln_70=round(float(np.std(bkz_70, ddof=1)), 4),
        bkz_mean_dln_final=round(float(np.mean(bkz_final)), 4),
        bkz_std_dln_final=round(float(np.std(bkz_final, ddof=1)), 4),
        bkz_improvement_70_to_final=round(float(np.mean(bkz_70) - np.mean(bkz_final)), 4),
        sdbkz_mean_dln_70=round(float(np.mean(sd_70)), 4),
        sdbkz_std_dln_70=round(float(np.std(sd_70, ddof=1)), 4),
        sdbkz_mean_dln_final=round(float(np.mean(sd_final)), 4),
        sdbkz_std_dln_final=round(float(np.std(sd_final, ddof=1)), 4),
        sdbkz_improvement_70_to_final=round(float(np.mean(sd_70) - np.mean(sd_final)), 4),
        mean_advantage=round(float(np.mean(advs)), 4),
        win_rate=round(float(np.mean(advs > 0)), 4),
    )

    PIPELINE.info(
        "convergence complete",
        cat="sweep",
        n=N, beta=BETA, tours=MAX_TOURS,
        elapsed_s=int(time.time() - _t_start),
    )

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
