#!/usr/bin/env python3
"""fplll 5.4.5 vs 5.5.0 sensitivity — 5-seed defense-in-depth check.

Reviewer pre-emption for paper §8 + §9: the paper's contemporary Docker
build pins fpylll 0.6.4 which bundles fplll 5.5.0 (libfplll.so.9.0.0).
This script runs 5 seeds of the main-sweep canonical point (n=100,
β=30, q=97, 250-bit MPFR) against fplll 5.4.5 (the last 5.4 release,
libfplll.so.8.0.1) via the Dockerfile.fplll54 image, and compares the
resulting per-seed advantages against the matching seeds from the
paper's main sweep (`results/seeds/main/q97/n100_beta30/seed000{1..5}.json`
produced under fplll 5.5.0; post-v2.0.0 layout).

If the mean advantage and per-seed signs agree within statistical
noise, paper results are fplll-version-robust. If they disagree, the
paper needs a pin-to-5.5.0 caveat.

Usage:
    # Inside the bkz-fplll54 docker image only — fails on the main
    # image because it imports sweep_parallel.run_single which assumes
    # Q=97 / PRECISION=250 / MAX_TOURS=100.
    python3 scripts/run_fplll54_sensitivity.py

Output: results/seeds/fplll_sensitivity/v5_4_5/q97/n100_beta30/seed000{1..5}.json
        (resolved via `_seed_paths.seed_dir_for("fplll_sensitivity", ...)`)
"""
import datetime
import json
import os
import sys
import time
from multiprocessing import Pool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

# Mock argv so sweep_parallel's import-time argparse doesn't choke
_saved_argv = sys.argv
sys.argv = ["sweep_parallel.py"]
import sweep_parallel  # noqa: E402

sys.argv = _saved_argv

from _seed_paths import seed_dir_for, seed_path_for
from log import get_logger

PIPELINE = get_logger("run_fplll54_sensitivity")

# Sanity — should match main-sweep canonical config
assert sweep_parallel.Q == 97, sweep_parallel.Q
assert sweep_parallel.PRECISION == 250, sweep_parallel.PRECISION

# -- Config ------------------------------------------------------------------

N = 100
BETA = 30
SEEDS = list(range(1, 6))
NUM_WORKERS = 5

# FPLLL_LABEL still drives the Docker build variant; FPLLL_VERSION
# drives the v1.3 seed_path_for() slug. Legacy labels map as:
#   fplll543 → 5.4.3  (libfplll.so.7.1.0)
#   fplll544 → 5.4.4  (libfplll.so.8.0.0)
#   fplll54  → 5.4.5  (libfplll.so.8.0.1)
_LABEL_TO_VERSION = {"fplll543": "5.4.3", "fplll544": "5.4.4", "fplll54": "5.4.5"}
_label = os.environ.get("FPLLL_LABEL", "fplll54")
_version = os.environ.get("FPLLL_VERSION", _LABEL_TO_VERSION.get(_label))
if _version is None:
    raise SystemExit(
        f"FPLLL_VERSION not set and label {_label!r} has no default mapping. "
        "Set FPLLL_VERSION=<x.y.z> explicitly."
    )
OUTPUT_DIR = seed_dir_for(
    "fplll_sensitivity", n=N, beta=BETA,
    fplll_version=_version, base=REPO_ROOT,
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out_path(seed):
    return seed_path_for(
        "fplll_sensitivity", n=N, beta=BETA, seed=seed,
        fplll_version=_version, base=REPO_ROOT,
    )


def already_done(seed):
    return os.path.exists(out_path(seed))


def worker(seed):
    t0 = time.time()
    try:
        result = sweep_parallel.run_single(N, BETA, seed, store_per_tour=False)
        with open(out_path(seed), "w") as f:
            json.dump(result, f, indent=2)
        return {
            "seed": seed,
            "status": "ok",
            "advantage": result["advantage"],
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


def _detect_fplll_backend():
    """Return the most-versioned libfplll.so.* path on the build paths.

    Globs both /usr/local/lib (source-built) and the Debian multiarch
    path. Sorts by string length so the symlink ``libfplll.so`` loses
    to the SONAME ``libfplll.so.8`` which loses to the full
    ``libfplll.so.8.0.1`` — the most informative path wins.
    """
    import glob
    libs = glob.glob("/usr/local/lib/libfplll.so.*") + \
           glob.glob("/usr/lib/x86_64-linux-gnu/libfplll.so.*")
    return max(libs, key=len) if libs else "unknown"


def _detect_fpylll_version():
    try:
        import fpylll
        return getattr(fpylll, "__version__", "unknown")
    except ImportError:
        return "unknown"


def main():
    todo = [s for s in SEEDS if not already_done(s)]
    done_count = len(SEEDS) - len(todo)

    fplll_backend = _detect_fplll_backend()
    fpylll_version = _detect_fpylll_version()

    print("=" * 70)
    print(f"{_label} sensitivity — n={N} β={BETA} q=97 250-bit MPFR")
    print(f"  fpylll version: {fpylll_version}")
    print(f"  fplll backend:  {fplll_backend}")
    print(f"  Plan:           {len(SEEDS)} seeds")
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
        f"{_label} sensitivity start",
        cat="sweep", n=N, beta=BETA, to_run=len(todo),
        already_done=done_count, workers=NUM_WORKERS,
        fplll_backend=fplll_backend, fpylll_version=fpylll_version,
    )
    t_start = time.time()
    completed = 0

    with Pool(processes=NUM_WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(worker, todo):
            completed += 1
            if r["status"] == "ok":
                print(f"  [{completed:>2}/{len(todo)}] seed {r['seed']:>2}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"wall={r['wall']/60:.1f}m", flush=True)
            else:
                print(f"  [{completed:>2}/{len(todo)}] seed {r['seed']:>2}: "
                      f"FAILED — {r['error']}", flush=True)
                print(r.get("trace", ""), flush=True)

    elapsed = time.time() - t_start
    print(f"\nDone. {completed} seeds in {elapsed/60:.1f} min.")
    PIPELINE.info(
        f"{_label} sensitivity complete",
        cat="sweep", completed=completed, elapsed_s=int(elapsed),
    )


if __name__ == "__main__":
    main()
