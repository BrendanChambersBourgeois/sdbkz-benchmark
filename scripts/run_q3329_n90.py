#!/usr/bin/env python3
"""q=3329 verification at n=90, β=30, 1000-bit MPFR.

Fills the gap in the dimension transition data between n=80 (0/20 = 0%
degenerate at 250-bit) and n=100 (38/100 = 38.0% degenerate at 1000-bit).
Uses 1000-bit MPFR to match the n=100 precision — the cancellation is
dimension-dependent not precision-dependent, but using the same precision
keeps the comparison clean and avoids conflating two effects.

v17 feedback item #6: "Run 20 seeds at n=90 beta=30 q=3329 with 1000-bit
MPFR. If 0/20, the transition is between n=90 and n=100."

Configuration:
    Dimension:   n=90
    Block size:  β=30
    Modulus:     q=3329
    Precision:   1000-bit MPFR
    Tours:       70 (standard budget)
    Seeds:       20
    Output:      results/q3329_n90_beta30/

Usage:
    nohup python3 scripts/run_q3329_n90.py > logs/q3329_n90.log 2>&1 &

DO NOT launch while the fplll_patch_test container or another BKZ
wrapper is using the CPU. Check first:
    docker ps
    pgrep -af 'run_q3329|sweep_parallel'
"""
import argparse
import datetime
import json
import os
import sys
import time
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from _seed_paths import seed_dir_for, seed_path_for
from log import get_logger

PIPELINE = get_logger("run_q3329_n90")

_parser = argparse.ArgumentParser(
    description="q=3329 n=90 β=30 1000-bit MPFR verification (20 seeds)")
_parser.add_argument("--workers", type=int, default=20,
                     help="parallel workers (default: 20)")
_parser.add_argument("--seeds", type=int, default=20,
                     help="number of seeds (default: 20)")
_cli_args = _parser.parse_args()

# Mock argv for q3329_verify's import-time argparse
_saved_argv = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", "90",
    "--beta", "30",
    "--seeds", str(_cli_args.seeds),
    "--precision", "1000",
]
import q3329_verify  # noqa: E402

sys.argv = _saved_argv

# Cleanup stale dir from q3329_verify's import side-effect
try:
    _stale = os.path.join(SCRIPT_DIR, "results_q3329")
    if os.path.isdir(_stale) and not os.listdir(_stale):
        os.rmdir(_stale)
except OSError:
    pass

assert q3329_verify.Q == 3329
assert q3329_verify.PRECISION == 1000
assert q3329_verify.MAX_TOURS == 70

# -- Config ----------------------------------------------------------------

N = 90
BETA = 30
NUM_WORKERS = _cli_args.workers
NUM_SEEDS = _cli_args.seeds
OUTPUT_DIR = seed_dir_for(
    "q3329", n=N, beta=BETA,
    precision=q3329_verify.PRECISION, max_tours=q3329_verify.MAX_TOURS,
    base=REPO_ROOT,
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _out_path(seed):
    return seed_path_for(
        "q3329", n=N, beta=BETA, seed=seed,
        q=3329,
        precision=q3329_verify.PRECISION,
        max_tours=q3329_verify.MAX_TOURS,
        base=REPO_ROOT,
    )


def _worker(seed):
    t0 = time.time()
    try:
        result = q3329_verify.run_single(N, BETA, seed, store_per_tour=True)
        with open(_out_path(seed), "w") as f:
            json.dump(result, f, indent=2)
        return {
            "seed": seed, "status": "ok",
            "advantage": result["advantage"],
            "wall": time.time() - t0,
        }
    except Exception as e:
        return {
            "seed": seed, "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "wall": time.time() - t0,
        }


def main():
    todo = [s for s in range(1, NUM_SEEDS + 1) if not os.path.exists(_out_path(s))]
    done_count = NUM_SEEDS - len(todo)

    print("=" * 70)
    print(f"q=3329 n={N} β={BETA} {q3329_verify.PRECISION}-bit MPFR")
    print(f"  Plan:           {NUM_SEEDS} seeds")
    print(f"  Already done:   {done_count}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {NUM_WORKERS}")
    print(f"  Output dir:     {OUTPUT_DIR}")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if not todo:
        print("Nothing to do.")
        return

    PIPELINE.info(
        "q3329 n=90 start",
        cat="sweep",
        n=N, beta=BETA, to_run=len(todo),
        already_done=done_count, workers=NUM_WORKERS,
    )
    t_start = time.time()
    completed = 0

    with Pool(processes=NUM_WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(_worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (len(todo) - completed) / rate if rate > 0 else 0
            status = f"adv={r['advantage']:+.4f}" if r["status"] == "ok" else r["error"]
            print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                  f"{status}  wall={r['wall']/3600:.2f}h  "
                  f"ETA={datetime.timedelta(seconds=int(eta))}",
                  flush=True)

    elapsed = time.time() - t_start
    print(f"\nDone. {completed} seeds in {elapsed/3600:.2f}h")
    PIPELINE.info(
        "q3329 n=90 complete",
        cat="sweep",
        n=N, beta=BETA, completed=completed,
        elapsed_s=int(elapsed),
    )
    os._exit(0)


if __name__ == "__main__":
    main()
