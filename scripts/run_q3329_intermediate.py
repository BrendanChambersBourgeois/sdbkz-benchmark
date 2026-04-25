#!/usr/bin/env python3
"""[DEPRECATED] q=3329 verification at intermediate dimensions n=70 and n=80, β=30.

**Status:** dormant. This script pre-dates the v1.3 physical-layout
migration (commit ``adf280b``) and writes seed JSONs to **pre-v1.3
paths** (``results/q3329_n70_beta30/`` + ``results/q3329_n80_beta30/``)
that are no longer the canonical destination — the v1.3 manifest
walker treats files written by this script as orphans until they are
either symlinked into the new tree or migrated.

**Use the supersession path instead:**

- For 1000-bit MPFR runs at intermediate q=3329 dimensions, use
  ``scripts/run_overnight_q3329_intermediate_1000bit.py``, which
  writes via ``_seed_paths.seed_path_for(...)`` and lands in the
  canonical ``results/seeds/q3329/...`` tree.

- For 250-bit MPFR runs (the original use case here) the q=3329
  intermediate-dimension data was already collected and committed
  pre-v1.3. Re-running this script today is not recommended — it
  produces orphan seeds the manifest walker will not pick up.

This module is kept in the tree because the v1.4.0 audit (item §1.5)
deprecate-vs-migrate decision landed on **deprecate**: no live caller,
no paper-extension need for the 250-bit q=3329 path that justified the
migration cost. If a future paper extension does need it, see
``Research/backlog/2026-04-25_q3329_intermediate_runner_migration.md``
option A (migrate to ``seed_path_for``) for the design notes.

The original docstring follows for historical reference — but the
``Usage`` block has been removed so a copy-paste reader does not
accidentally launch the deprecated path.

Original configuration:
    Dimensions:  n=70, n=80
    Block size:  β=30
    Modulus:     q=3329 (Kyber's ML-KEM modulus)
    Precision:   250-bit MPFR (sufficient for n ≤ 90 at q=3329)
    Tours:       70 (standard budget)
    Seeds:       20 per dimension
    Original output (NON-CANONICAL post-v1.3):
                 results/q3329_n70_beta30/
                 results/q3329_n80_beta30/
"""
import os
import sys
import json
import time
import datetime
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from log import get_logger
PIPELINE = get_logger("run_q3329_intermediate")

# q3329_verify parses argparse at import time. Mock argv so it picks up
# Q=3329 / PRECISION=250 / β=30 / 70 tours before we import the module.
# The --n value here is irrelevant — run_single() takes n as a parameter,
# so we can call it with both 70 and 80 from the same import.
_saved_argv = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", "70",
    "--beta", "30",
    "--seeds", "20",
    "--precision", "250",
]
import q3329_verify  # noqa: E402
sys.argv = _saved_argv

# q3329_verify creates an OUTPUT_DIR at import time inside scripts/ which
# we don't use. Clean it up if empty.
try:
    _stale = os.path.join(SCRIPT_DIR, "results_q3329")
    if os.path.isdir(_stale) and not os.listdir(_stale):
        os.rmdir(_stale)
except OSError:
    pass

# Sanity-check the imported module state
assert q3329_verify.Q == 3329, q3329_verify.Q
assert q3329_verify.PRECISION == 250, q3329_verify.PRECISION
assert q3329_verify.MAX_TOURS == 70, q3329_verify.MAX_TOURS

# -- Run config ---------------------------------------------------------------

BETA = 30
NUM_WORKERS = 20      # one worker per seed; we have 20 seeds × 2 groups
SEEDS_PER_GROUP = 20

GROUPS = [
    {
        "n": 70,
        "output_subdir": "q3329_n70_beta30",
    },
    {
        "n": 80,
        "output_subdir": "q3329_n80_beta30",
    },
]


def _output_path(out_dir, n, beta, seed):
    return os.path.join(out_dir, f"n{n}_beta{beta}_q3329_seed{seed}.json")


def _already_done(out_dir, n, beta, seed):
    return os.path.exists(_output_path(out_dir, n, beta, seed))


# -- Worker ----------------------------------------------------------------

def _worker(task):
    """Run one (n, seed). Returns a status dict.

    Calls q3329_verify.run_single with store_per_tour=True so the
    output JSONs include per-tour Rankin profile + GS log-norms + RHF.
    Roughly 10x larger files (~500 KB instead of ~50 KB) and ~0.1%
    extra compute, but it means future investigations of these seeds
    can be done from the existing data without re-running BKZ. (The
    original q=3329 get_r investigation needed a full BKZ re-run
    because per-tour state wasn't stored on the initial sweep — this
    wrapper prevents that recurrence.)
    """
    n, beta, seed, out_dir = task
    t0 = time.time()
    try:
        result = q3329_verify.run_single(n, beta, seed, store_per_tour=True)
        with open(_output_path(out_dir, n, beta, seed), "w") as f:
            json.dump(result, f, indent=2)
        return {
            "n": n,
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
            "n": n,
            "seed": seed,
            "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(),
            "wall": time.time() - t0,
        }


# -- Main ------------------------------------------------------------------

def _run_group(n, out_dir, beta=BETA, n_seeds=SEEDS_PER_GROUP):
    """Run all seeds for one (n, beta) group."""
    os.makedirs(out_dir, exist_ok=True)
    todo = [
        (n, beta, seed, out_dir)
        for seed in range(1, n_seeds + 1)
        if not _already_done(out_dir, n, beta, seed)
    ]
    print()
    print("=" * 70)
    print(f"q={q3329_verify.Q} n={n} β={beta} {q3329_verify.PRECISION}-bit MPFR")
    print(f"  Plan:           {n_seeds} seeds")
    print(f"  Already done:   {n_seeds - len(todo)}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {NUM_WORKERS}")
    print(f"  Output dir:     {out_dir}")
    print(f"  Started:        "
          f"{datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if not todo:
        print("Nothing to do.")
        return

    completed = 0
    t_start = time.time()

    # maxtasksperchild=1: restart workers between seeds. Per-seed cost is
    # large enough that fork overhead is negligible, and it shields
    # against any MPFR state bleed across long-running seeds.
    with Pool(processes=NUM_WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(_worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0.0
            eta_sec = (len(todo) - completed) / rate if rate > 0 else 0
            eta = datetime.timedelta(seconds=int(eta_sec))

            if r["status"] == "ok":
                print(f"  [{completed:>3}/{len(todo)}] n={r['n']:>3} "
                      f"seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={r['bkz_time']/60:.1f}m  "
                      f"SDBKZ={r['sdbkz_time']/60:.1f}m  "
                      f"wall={r['wall']/60:.1f}m  "
                      f"ETA={eta}", flush=True)
            else:
                print(f"  [{completed:>3}/{len(todo)}] n={r['n']:>3} "
                      f"seed {r['seed']:>3}: FAILED — {r['error']}",
                      flush=True)
                print(r["trace"], flush=True)

    total_h = (time.time() - t_start) / 3600
    print()
    print(f"Group n={n} β={beta} done in {total_h:.2f} h.")


def main():
    print("q=3329 intermediate dimension verification (n=70, n=80, β=30)")
    print(f"Imported q3329_verify with Q={q3329_verify.Q}, "
          f"PRECISION={q3329_verify.PRECISION}, "
          f"MAX_TOURS={q3329_verify.MAX_TOURS}")

    PIPELINE.info(
        "q3329 intermediate start",
        cat="sweep",
        q=q3329_verify.Q, precision=q3329_verify.PRECISION,
        groups=[{"n": g["n"]} for g in GROUPS],
    )
    overall_start = time.time()

    for group in GROUPS:
        out_dir = os.path.join(REPO_ROOT, "results", group["output_subdir"])
        _run_group(group["n"], out_dir)

    overall_h = (time.time() - overall_start) / 3600
    print()
    print("=" * 70)
    print(f"All groups complete in {overall_h:.2f} h.")
    print("Results written to results/q3329/ — regenerate figures with "
          "`python3 analysis/paper_figures.py`.")
    print("=" * 70)
    PIPELINE.info(
        "q3329 intermediate complete",
        cat="sweep",
        elapsed_s=int(time.time() - overall_start),
    )


if __name__ == "__main__":
    main()
