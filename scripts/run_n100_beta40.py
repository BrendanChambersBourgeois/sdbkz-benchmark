#!/usr/bin/env python3
"""
n=100 β=40 q=97 250-bit MPFR — fills the gap in the main sweep grid.

The local campaign ran β=40 for n=50–90 (100 seeds each), the cloud
campaign ran n=110–140, and n=100 was never dispatched. This script
fills that hole so the peak-migration analysis has continuous coverage.

Uses sweep_parallel.run_single() directly — the output JSONs are
schema-identical to the existing results/raw/ files.

Per-seed estimate: ~5.3h (interpolated from n=90 ~4.3h and n=110 ~6.4h).

Usage:
    # Remote half (seeds 51-100, 30 workers, ~9h)
    docker compose run --rm sweep python3 scripts/run_n100_beta40.py \
        --start 51 --end 100 --workers 30

    # Local half (seeds 1-50)
    docker compose run --rm sweep python3 scripts/run_n100_beta40.py \
        --start 1 --end 50 --workers 22
"""
import os
import sys
import json
import time
import datetime
import argparse
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from log import get_logger
PIPELINE = get_logger("run_n100_beta40")

# -- Args (parse before importing sweep_parallel to avoid conflicts) ----------

parser = argparse.ArgumentParser(description="n=100 β=40 q=97 sweep gap-fill")
parser.add_argument("--start", type=int, default=1,
                    help="first seed (inclusive), default 1")
parser.add_argument("--end", type=int, default=100,
                    help="last seed (inclusive), default 100")
parser.add_argument("--workers", type=int, default=22,
                    help="parallel workers, default 22")
args = parser.parse_args()

# sweep_parallel doesn't parse argv at import time (unlike q3329_verify),
# so we can import it directly.
import sweep_parallel  # noqa: E402

# -- Config -------------------------------------------------------------------

N = 100
BETA = 40
SEEDS = list(range(args.start, args.end + 1))
NUM_WORKERS = args.workers

os.makedirs(sweep_parallel.RAW_DIR, exist_ok=True)


def out_path(seed):
    return sweep_parallel.result_path(N, BETA, seed)


def already_done(seed):
    return os.path.exists(out_path(seed))


# -- Worker -------------------------------------------------------------------

def worker(seed):
    t0 = time.time()
    try:
        result = sweep_parallel.run_single(N, BETA, seed)
        with open(out_path(seed), "w") as f:
            json.dump(result, f, indent=2)
        return {
            "seed": seed, "status": "ok",
            "advantage": result["advantage"],
            "bkz_time": result["bkz_time"],
            "sdbkz_time": result["sdbkz_time"],
            "wall": time.time() - t0,
        }
    except Exception as e:
        import traceback
        return {
            "seed": seed, "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(),
            "wall": time.time() - t0,
        }


# -- Main ---------------------------------------------------------------------

def main():
    todo = [s for s in SEEDS if not already_done(s)]

    print("=" * 70)
    print(f"n={N} β={BETA} q={sweep_parallel.Q} "
          f"{sweep_parallel.PRECISION}-bit MPFR — gap-fill (main sweep grid)")
    print(f"  Seed range:     {args.start}..{args.end} ({len(SEEDS)} seeds)")
    print(f"  Already done:   {len(SEEDS) - len(todo)}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {NUM_WORKERS}")
    print(f"  Tours:          {sweep_parallel.TOURS_BY_BETA[BETA]}")
    print(f"  Output dir:     {sweep_parallel.RAW_DIR}")
    print("  Per-seed est:   ~5.3h (interpolated from n=90/n=110 β=40)")
    if todo:
        est_h = len(todo) * 5.3 / NUM_WORKERS
        print(f"  Wall-clock est: ~{est_h:.1f}h")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if not todo:
        print("Nothing to do.")
        return

    PIPELINE.info(
        "n=100 β=40 gap-fill start",
        cat="sweep",
        n=N, beta=BETA, q=sweep_parallel.Q,
        to_run=len(todo), already_done=len(SEEDS) - len(todo),
        workers=NUM_WORKERS,
    )
    completed = 0
    t_start = time.time()

    with Pool(processes=NUM_WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (len(todo) - completed) / rate if rate > 0 else 0

            if r["status"] == "ok":
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={r['bkz_time']/3600:.2f}h  "
                      f"SDBKZ={r['sdbkz_time']/3600:.2f}h  "
                      f"wall={r['wall']/3600:.2f}h  "
                      f"ETA={datetime.timedelta(seconds=int(eta))}",
                      flush=True)
            else:
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"FAILED — {r['error']}", flush=True)

    total_h = (time.time() - t_start) / 3600
    print(f"\nDone in {total_h:.2f}h.")
    PIPELINE.info(
        "n=100 β=40 gap-fill complete",
        cat="sweep",
        n=N, beta=BETA, completed=completed,
        elapsed_s=int(time.time() - t_start),
    )


if __name__ == "__main__":
    main()
