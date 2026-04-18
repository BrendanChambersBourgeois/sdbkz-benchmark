#!/usr/bin/env python3
"""
General-purpose gap-filler for the main q=97 sweep grid.

Runs any (n, β) group that sweep_parallel supports, for any seed range.
Replaces per-group one-off scripts (run_n100_beta40.py etc.).

Uses sweep_parallel.run_single() directly — output JSONs are
schema-identical to results/raw/.

Usage examples:
    # Fill n=120 β=40 seeds 76-100, 22 workers
    python3 scripts/run_sweep_fill.py --n 120 --beta 40 --start 76 --end 100

    # Fill n=140 β=40 full range, 16 workers (Dylan)
    python3 scripts/run_sweep_fill.py --n 140 --beta 40 --start 26 --end 100 --workers 16

    # Dry-run to see what's missing without running anything
    python3 scripts/run_sweep_fill.py --n 150 --beta 40 --dry-run

    # Via Docker
    docker compose run --rm sweep python3 scripts/run_sweep_fill.py \
        --n 120 --beta 40 --start 76 --end 100 --workers 16
"""
import os
import sys
import json
import time
import datetime
import argparse
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

try:
    from log import get_logger  # noqa: E402
    slog = get_logger("run_sweep_fill")
except Exception:
    class _Noop:
        def __getattr__(self, _): return lambda *a, **k: None
    slog = _Noop()

# -- Args ----------------------------------------------------------------------

parser = argparse.ArgumentParser(
    description="Fill missing seeds for any (n, β) group in the main sweep grid")
parser.add_argument("--n", type=int, required=True,
                    help="lattice dimension (50-150)")
parser.add_argument("--beta", type=int, required=True,
                    help="block size (20, 30, or 40)")
parser.add_argument("--start", type=int, default=1,
                    help="first seed inclusive (default: 1)")
parser.add_argument("--end", type=int, default=100,
                    help="last seed inclusive (default: 100)")
parser.add_argument("--workers", type=int, default=0,
                    help="parallel workers (default: auto-detect physical cores)")
parser.add_argument("--dry-run", action="store_true",
                    help="list missing seeds and exit without running")
args = parser.parse_args()

import sweep_parallel  # noqa: E402

# -- Auto-detect workers -------------------------------------------------------

if args.workers <= 0:
    # Use physical core count, not logical (SMT hurts fpylll).
    # /sys/devices is Linux-only but that's all we run on.
    try:
        # Count unique physical core IDs across all packages
        import glob as _glob
        core_ids = set()
        for path in _glob.glob("/sys/devices/system/cpu/cpu[0-9]*/topology/core_id"):
            pkg = open(path.replace("core_id", "physical_package_id")).read().strip()
            cid = open(path).read().strip()
            core_ids.add((pkg, cid))
        physical = len(core_ids)
    except (OSError, ValueError):
        physical = 0
    args.workers = physical if physical > 0 else (os.cpu_count() or 4)
    # Never exceed logical count (Docker may limit visible CPUs)
    args.workers = min(args.workers, os.cpu_count() or args.workers)

# -- Validate ------------------------------------------------------------------

if args.n not in sweep_parallel.NS:
    parser.error(f"n={args.n} not in grid {sweep_parallel.NS}")
if args.beta not in sweep_parallel.BETAS:
    parser.error(f"β={args.beta} not in grid {sweep_parallel.BETAS}")

N = args.n
BETA = args.beta
SEEDS = list(range(args.start, args.end + 1))

# Check both raw/ and cloud/ for existing seeds (cloud campaign wrote to cloud/)
CLOUD_DIR = os.path.join(sweep_parallel.RESULTS_DIR, "cloud")
os.makedirs(sweep_parallel.RAW_DIR, exist_ok=True)


def out_path(seed):
    return sweep_parallel.result_path(N, BETA, seed)


def seed_exists(seed):
    """Check if seed result exists in raw/ or cloud/."""
    fname = f"n{N}_beta{BETA}_seed{seed}.json"
    return (os.path.exists(os.path.join(sweep_parallel.RAW_DIR, fname))
            or os.path.exists(os.path.join(CLOUD_DIR, fname)))


# -- Worker --------------------------------------------------------------------

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


# -- Main ----------------------------------------------------------------------

def main():
    todo = [s for s in SEEDS if not seed_exists(s)]
    tours = sweep_parallel.TOURS_BY_BETA[BETA]

    slog.info("sweep gap-fill starting", cat="sweep",
              n=N, beta=BETA, q=sweep_parallel.Q,
              range=f"{args.start}-{args.end}", total=len(SEEDS),
              todo=len(todo), workers=args.workers, tours=tours)

    print("=" * 70)
    print(f"n={N} β={BETA} q={sweep_parallel.Q} "
          f"{sweep_parallel.PRECISION}-bit MPFR — sweep gap-fill")
    print(f"  Seed range:     {args.start}..{args.end} ({len(SEEDS)} seeds)")
    print(f"  Already done:   {len(SEEDS) - len(todo)}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {args.workers}")
    print(f"  Tours:          {tours}")
    print(f"  Output dir:     {sweep_parallel.RAW_DIR}")
    if todo and not args.dry_run:
        est_h = len(todo) * (tours * 0.14) / args.workers
        print(f"  Wall-clock est: order of ~{est_h:.0f}h (very rough)")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if args.dry_run:
        if todo:
            print(f"\nMissing seeds: {todo}")
        else:
            print("\nAll seeds present.")
        return

    if not todo:
        slog.info("nothing to do — all seeds exist", cat="sweep", n=N, beta=BETA)
        print("Nothing to do — all seeds already exist.")
        return

    completed = 0
    failed = 0
    t_start = time.time()

    with Pool(processes=args.workers, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (len(todo) - completed) / rate if rate > 0 else 0

            if r["status"] == "ok":
                slog.info(f"seed {r['seed']} completed", cat="sweep",
                          n=N, beta=BETA, seed=r["seed"],
                          advantage=round(r["advantage"], 6),
                          wall_h=round(r["wall"]/3600, 2))
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={r['bkz_time']/3600:.2f}h  "
                      f"SDBKZ={r['sdbkz_time']/3600:.2f}h  "
                      f"wall={r['wall']/3600:.2f}h  "
                      f"ETA={datetime.timedelta(seconds=int(eta))}",
                      flush=True)
            else:
                failed += 1
                slog.error(f"seed {r['seed']} failed: {r['error']}", cat="sweep",
                           n=N, beta=BETA, seed=r["seed"])
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"FAILED — {r['error']}", flush=True)

    total_h = (time.time() - t_start) / 3600
    slog.info("sweep gap-fill done", cat="sweep",
              n=N, beta=BETA, succeeded=completed-failed,
              failed=failed, wall_h=round(total_h, 2))
    print(f"\nDone in {total_h:.2f}h. "
          f"{completed - failed} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
