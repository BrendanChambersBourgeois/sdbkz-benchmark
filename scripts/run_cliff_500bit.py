#!/usr/bin/env python3
"""
β=40 cliff precision test: n=130, β=40, q=97 at 500-bit MPFR, 20 seeds.

Paper §6.3 reports an abrupt "cliff" in the SD-BKZ advantage at β=40
between n=110 (+1.158 nats) and n=130 (-1.334 nats, 0% win). The
hypothesis the reviewer will ask: is this cliff structural, or does
the 250-bit MPFR precision used in the main sweep (sweep_parallel.py)
lose too many bits somewhere in the Cholesky-style squared-form GSO
recurrence for this combination of parameters, and a higher
precision would soften the cliff?

This run repeats the n=130 β=40 group at 500-bit MPFR. If the
mean advantage stays around −1.334 nats and win rate stays at 0%,
the cliff is structural and the paper claim is hardened. If the
advantage softens meaningfully (e.g. above −0.5 nats or any
non-zero win rate), §6.3 needs a precision caveat for camera-ready.

Reuses q3329_verify.run_single() after overriding its module-level
Q/PRECISION/MAX_TOURS constants — q3329_verify was written as a
q=3329 helper but its run_single() is generic in (n, β, seed) and
reads Q/PRECISION/MAX_TOURS from module scope, so a pre-import
patch lets us reuse the well-tested single-seed driver for a
q=97 / 500-bit configuration without duplicating 400 lines.

Usage:
    nohup python3 scripts/run_cliff_500bit.py \
        > logs/cliff_500bit_n130_b40.out 2>&1 &
    echo $! > logs/cliff_500bit.pid

    # Dry-run (prints plan, touches no seeds):
    python3 scripts/run_cliff_500bit.py --dry-run

Output: results/cliff_500bit/n130_beta40_q97_seed{1..20}.json (fat
seeds — includes per-tour trajectories so per-position analysis can
compare against the 250-bit baseline without a re-run).
"""
import os, sys, json, time, datetime, argparse
from multiprocessing import Pool  # noqa: F401  (kept for API compat)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from log import get_logger, new_run_id, get_run_id
from _signal_utils import managed_pool
PIPELINE = get_logger("run_cliff_500bit")

# -- CLI ---------------------------------------------------------------------

_parser = argparse.ArgumentParser(add_help=False,
    description="β=40 cliff precision test at n=130, 500-bit MPFR")
_parser.add_argument("--workers", type=int, default=22,
                     help="parallel workers, default 22 (leave headroom on 32-core host)")
_parser.add_argument("--seeds", type=int, default=20,
                     help="number of seeds, default 20")
_parser.add_argument("--dry-run", action="store_true",
                     help="print plan, do not launch any workers")
_cli_args, _ = _parser.parse_known_args()

# -- Import q3329_verify with argv mocking + mutate module globals ----------

# q3329_verify parses argparse at import time to set N/BETA/PRECISION/SEEDS
# globals. We mock argv so its parse_args() succeeds, then override the
# bits that differ from its default assumption of q=3329.
_saved_argv = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", "130",
    "--beta", "40",
    "--seeds", str(_cli_args.seeds),
    "--precision", "500",
]
import q3329_verify  # noqa: E402
sys.argv = _saved_argv

# Override the q=3329-specific module constants to q=97 for this run.
# q3329_verify.run_single() reads these from module scope, so mutating
# them here affects every subsequent worker invocation.
q3329_verify.Q = 97

# Sanity-check the rest of the imported module state matches the plan
assert q3329_verify.N == 130, q3329_verify.N
assert q3329_verify.BETA == 40, q3329_verify.BETA
assert q3329_verify.PRECISION == 500, q3329_verify.PRECISION
assert q3329_verify.MAX_TOURS == 100, q3329_verify.MAX_TOURS

# -- Run config --------------------------------------------------------------

N = 130
BETA = 40
Q = 97
PRECISION = 500
NUM_WORKERS = _cli_args.workers
SEEDS = list(range(1, _cli_args.seeds + 1))

OUTPUT_DIR = os.path.join(REPO_ROOT, "results", "cliff_500bit")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out_path(seed):
    return os.path.join(OUTPUT_DIR, f"n{N}_beta{BETA}_q{Q}_seed{seed}.json")


def already_done(seed):
    return os.path.exists(out_path(seed))


# -- Worker ------------------------------------------------------------------

def worker(seed):
    """Run one seed via q3329_verify.run_single with store_per_tour=True."""
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
        PIPELINE.error("cliff worker failed", cat="sweep",
                       n=N, beta=BETA, seed=seed,
                       exc_type=type(e).__name__, exc_msg=str(e),
                       traceback=traceback.format_exc())
        return {
            "seed": seed,
            "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(),
            "wall": time.time() - t0,
        }


# -- Main --------------------------------------------------------------------

def main():
    if not get_run_id():
        new_run_id()
    todo = [s for s in SEEDS if not already_done(s)]
    done_count = len(SEEDS) - len(todo)

    print("=" * 70)
    print(f"β=40 CLIFF PRECISION TEST (camera-ready §6.3 robustness)")
    print(f"  n={N} β={BETA} q={Q} precision={PRECISION}-bit MPFR")
    print(f"  Plan:           seeds 1..{len(SEEDS)} ({len(SEEDS)} total)")
    print(f"  Already done:   {done_count}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {NUM_WORKERS}")
    print(f"  Output dir:     {OUTPUT_DIR}")
    print(f"  Per-seed est:   ~70 ks wall (27 ks @ 250-bit × ~2.5× penalty)")
    if todo:
        est_h = len(todo) * 70000 / NUM_WORKERS / 3600
        print(f"  Wall-clock est: ~{est_h:.1f} h")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if _cli_args.dry_run:
        print("DRY-RUN — no workers launched. Re-run without --dry-run to start.",
              flush=True)
        return

    if not todo:
        print("Nothing to do.")
        return

    PIPELINE.info(
        "cliff 500bit start",
        cat="sweep",
        n=N, beta=BETA, q=Q, precision=PRECISION,
        to_run=len(todo), already_done=done_count,
        workers=NUM_WORKERS,
    )
    t_start = time.time()
    completed = 0

    with managed_pool(processes=NUM_WORKERS, maxtasksperchild=1,
                      label="run_cliff_500bit") as pool:
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
                print(r.get("trace", ""), flush=True)

    elapsed = time.time() - t_start
    print(f"\nDone. {completed} seeds in {elapsed/3600:.2f} h.")
    PIPELINE.info(
        "cliff 500bit complete",
        cat="sweep",
        n=N, beta=BETA, q=Q, precision=PRECISION,
        completed=completed,
        elapsed_s=int(elapsed),
    )


if __name__ == "__main__":
    main()
