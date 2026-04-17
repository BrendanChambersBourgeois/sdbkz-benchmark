#!/usr/bin/env python3
"""
n=100 β=30 q=3329 1000-bit MPFR — local parallel run extending the
existing 10-seed cloud dataset to 100 seeds.

The 50% degeneracy rate observed in the first 10 seeds is the headline
q=3329 finding (and a candidate Section 8 / Future Work item in the
paper). This run takes the sample size to 100 so the rate has a tight
confidence interval (~10% half-width at 95% vs ~31% at 10 seeds).

Schema parity is guaranteed by importing run_single() from
scripts/q3329_verify.py — the same code path that produced the existing
10 cloud seeds, so the resulting JSONs slot directly into the dataset.

Per-seed cost (measured on AWS, 10/10 seeds):
    BKZ    ~2.32 h
    SD-BKZ ~6.77 h
    total  ~9.09 h on a single core.
With 22 workers and 90 new seeds, the wall-clock estimate is ~37 h IF
the local CPU matches AWS per-core speed. Recalibrate by timing the
first completed seed against the AWS baseline (32,716 s total).

File layout:
    Existing seeds 1-10:  results/cloud/n100_beta30_q3329_seed*.json
                          (already done — skipped here)
    New seeds 11-100:     results/q3329/n100_beta30_q3329_seed*.json

The analysis package aggregates BOTH directories into the same (n, β)
group at load time, so no post-run merge is needed.

Usage:
    nohup python3 scripts/run_q3329_n100_local.py \
        > logs/q3329_n100_local.log 2>&1 &

DO NOT launch while the n=140 β=30 convergence test (or any other
heavy job) is still using the workers. Check first:
    pgrep -af run_convergence
"""
import os, sys, json, time, datetime, argparse
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from log import get_logger
PIPELINE = get_logger("run_q3329_n100_local")

# Parse our own args before mocking sys.argv for q3329_verify import.
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--start", type=int, default=1,
                     help="first seed (inclusive), default 1")
_parser.add_argument("--end", type=int, default=100,
                     help="last seed (inclusive), default 100")
_parser.add_argument("--workers", type=int, default=22,
                     help="parallel workers, default 22")
_cli_args, _ = _parser.parse_known_args()

# q3329_verify parses argparse at import time. Mock argv so it picks up
# the right N/BETA/PRECISION before we import the module.
_saved_argv = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", "100",
    "--beta", "30",
    "--seeds", "100",
    "--precision", "1000",
]
import q3329_verify  # noqa: E402
sys.argv = _saved_argv

# q3329_verify.main()'s OUTPUT_DIR is created at import time inside scripts/.
# We don't use main() — clean up the empty stale dir if we just created it.
try:
    _stale = os.path.join(SCRIPT_DIR, "results_q3329")
    if os.path.isdir(_stale) and not os.listdir(_stale):
        os.rmdir(_stale)
except OSError:
    pass

# Sanity-check the imported module state matches the run plan
assert q3329_verify.Q == 3329, q3329_verify.Q
assert q3329_verify.PRECISION == 1000, q3329_verify.PRECISION
assert q3329_verify.MAX_TOURS == 70, q3329_verify.MAX_TOURS

# -- Run config ---------------------------------------------------------------

N = 100
BETA = 30
Q = 3329
NUM_WORKERS = _cli_args.workers
SEEDS = list(range(_cli_args.start, _cli_args.end + 1))

OUTPUT_DIR = os.path.join(REPO_ROOT, "results", "q3329")
CLOUD_DIR = os.path.join(REPO_ROOT, "results", "cloud")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out_path(seed):
    return os.path.join(OUTPUT_DIR, f"n{N}_beta{BETA}_q{Q}_seed{seed}.json")


def cloud_path(seed):
    return os.path.join(CLOUD_DIR, f"n{N}_beta{BETA}_q{Q}_seed{seed}.json")


def already_done(seed):
    return os.path.exists(out_path(seed)) or os.path.exists(cloud_path(seed))


# -- Worker -------------------------------------------------------------------

def worker(seed):
    """Run one seed via q3329_verify.run_single. Returns a status dict.

    Calls run_single with store_per_tour=True so the output JSONs
    include per-tour Rankin profile + GS log-norms + RHF for both
    variants. Roughly 10x larger files (~500 KB instead of ~50 KB)
    and ~0.1% extra compute. Trade is worth it for q=3329 because
    the degeneracy is intermittent across tours and future
    investigations should not need to re-run BKZ from scratch
    (lesson from the q=3329 get_r investigation).

    The currently in-flight wrapper run (PID 790458, started before
    this patch) has the OLD version of this file imported and will
    keep producing the lean schema for its 45 seeds. Future
    re-launches of this wrapper will pick up the fat schema.
    """
    t0 = time.time()
    try:
        result = q3329_verify.run_single(N, BETA, seed, store_per_tour=True)
        with open(out_path(seed), "w") as f:
            json.dump(result, f, indent=2)
        return {
            "seed": seed,
            "status": "ok",
            "advantage": result["advantage"],
            "bkz_time": result["bkz_time"],
            "sdbkz_time": result["sdbkz_time"],
            "wall": time.time() - t0,
        }
    except Exception as e:
        import traceback
        return {
            "seed": seed,
            "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(),
            "wall": time.time() - t0,
        }


# -- Main ---------------------------------------------------------------------

def main():
    todo = [s for s in SEEDS if not already_done(s)]

    print("=" * 70)
    print(f"q={Q} n={N} β={BETA} 1000-bit MPFR  —  local extension to 100 seeds")
    print(f"  Plan:           seeds 1..{len(SEEDS)}")
    print(f"  Already done:   {len(SEEDS) - len(todo)}  "
          f"(in results/cloud/ or results/q3329/)")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {NUM_WORKERS}")
    print(f"  Output dir:     {OUTPUT_DIR}")
    print(f"  Per-seed est:   ~9.1 h on a single core (AWS baseline)")
    if todo:
        est_h = len(todo) * 9.1 / NUM_WORKERS
        print(f"  Wall-clock est: ~{est_h:.1f} h "
              f"(if local CPU matches AWS per-core speed)")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if not todo:
        print("Nothing to do.")
        return

    PIPELINE.info(
        "q3329 n=100 local start",
        cat="sweep",
        n=N, beta=BETA, q=Q, to_run=len(todo),
        already_done=len(SEEDS) - len(todo), workers=NUM_WORKERS,
    )
    completed = 0
    t_start = time.time()

    # maxtasksperchild=1: restart worker between seeds. Per-seed cost is ~9 h
    # so the fork overhead is negligible, and it shields against any MPFR
    # state bleed across seeds.
    with Pool(processes=NUM_WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0.0
            eta_sec = (len(todo) - completed) / rate if rate > 0 else 0
            eta = datetime.timedelta(seconds=int(eta_sec))

            if r["status"] == "ok":
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={r['bkz_time']/3600:.2f}h  "
                      f"SDBKZ={r['sdbkz_time']/3600:.2f}h  "
                      f"wall={r['wall']/3600:.2f}h  "
                      f"ETA={eta}", flush=True)
            else:
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"FAILED — {r['error']}", flush=True)
                print(r["trace"], flush=True)

    total_h = (time.time() - t_start) / 3600
    print()
    print(f"Done in {total_h:.2f} h.")
    print("Results written to results/q3329/ — regenerate figures with "
          "`python3 analysis/paper_figures.py`.")
    PIPELINE.info(
        "q3329 n=100 local complete",
        cat="sweep",
        n=N, beta=BETA, q=Q, completed=completed,
        elapsed_s=int(time.time() - t_start),
    )


if __name__ == "__main__":
    main()
