#!/usr/bin/env python3
"""Overnight q=3329 intermediate-dimension fill at 1000-bit MPFR.

Tops up the q=3329 n∈{70, 80} β=30 intermediate groups from 20 seeds
(the original 250-bit dataset) to 50 seeds at the paper's 1000-bit
MPFR precision. Writes under the v1.3 layout via
scripts/_seed_paths.seed_path_for() so the new seeds land at
`results/seeds/q3329/p1000_mt70/n{n:03d}_beta30/seed{seed:04d}.json`
and are picked up cleanly by the next build_seed_manifest pass.

Conservative defaults:
  --start 21  --end 25   (5 new seeds per group; ~5-10 h wall-clock
                          at n=70, ~10-20 h at n=80, on 22 workers).
  --n 70                 (single dimension per invocation; parallel
                          runs across dimensions would compete for
                          the same pool, so keep one queue at a time).

Usage (overnight, nohup-backgrounded):
  nohup python3 scripts/run_overnight_q3329_intermediate_1000bit.py \\
      --n 70 --start 21 --end 25 --workers 22 \\
      > /tmp/overnight_$(date +%%Y%%m%%d)/q3329_n70_1000bit.log 2>&1 &

Restart-safe: already-done seeds are skipped via file-exists probe on
the target v1.3 path. Safe to re-run after a crash — completed work
is preserved, only pending seeds are re-dispatched.
"""

from __future__ import annotations

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

from _seed_paths import seed_dir_for, seed_path_for  # noqa: E402
from log import get_logger  # noqa: E402

PIPELINE = get_logger("run_overnight_q3329_intermediate_1000bit")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, required=True,
                   help="secret dimension (70 or 80)")
    p.add_argument("--beta", type=int, default=30)
    p.add_argument("--precision", type=int, default=1000)
    p.add_argument("--max-tours", type=int, default=70)
    p.add_argument("--start", type=int, default=21,
                   help="first seed (inclusive), default 21")
    p.add_argument("--end", type=int, default=50,
                   help="last seed (inclusive), default 50")
    p.add_argument("--workers", type=int, default=22)
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be done, launch nothing")
    return p.parse_args()


_args = _parse_args()

# Mock argv for q3329_verify's import-time argparse. q3329_verify reads
# N/BETA/PRECISION/MAX_TOURS from module scope so this patch sets up the
# right run configuration before any worker runs.
_saved_argv = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", str(_args.n),
    "--beta", str(_args.beta),
    "--seeds", str(_args.end),
    "--precision", str(_args.precision),
]
import q3329_verify  # noqa: E402

sys.argv = _saved_argv

# Clean up the empty results_q3329 dir q3329_verify creates at import
# time (it runs os.makedirs(OUTPUT_DIR) on import; OUTPUT_DIR is now
# routed through _seed_paths, but q3329_verify still references the
# pre-v1.3 legacy dir name which is harmless but cosmetic to remove
# if empty).
try:
    _stale = os.path.join(SCRIPT_DIR, "results_q3329")
    if os.path.isdir(_stale) and not os.listdir(_stale):
        os.rmdir(_stale)
except OSError:
    pass

assert q3329_verify.Q == 3329, q3329_verify.Q
assert q3329_verify.PRECISION == _args.precision, q3329_verify.PRECISION
assert q3329_verify.MAX_TOURS == _args.max_tours, q3329_verify.MAX_TOURS
assert q3329_verify.N == _args.n, q3329_verify.N
assert q3329_verify.BETA == _args.beta, q3329_verify.BETA


OUTPUT_DIR = seed_dir_for(
    "q3329", n=_args.n, beta=_args.beta,
    precision=_args.precision, max_tours=_args.max_tours,
    base=REPO_ROOT,
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _out_path(seed: int) -> str:
    return seed_path_for(
        "q3329", n=_args.n, beta=_args.beta, seed=seed,
        q=3329,
        precision=_args.precision, max_tours=_args.max_tours,
        base=REPO_ROOT,
    )


def _already_done(seed: int) -> bool:
    return os.path.exists(_out_path(seed))


def _worker(seed: int) -> dict:
    t0 = time.time()
    try:
        result = q3329_verify.run_single(
            _args.n, _args.beta, seed, store_per_tour=True,
        )
        out = _out_path(seed)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
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


def main() -> int:
    plan = list(range(_args.start, _args.end + 1))
    todo = [s for s in plan if not _already_done(s)]
    done_count = len(plan) - len(todo)

    hdr = "=" * 70
    print(hdr)
    print(f"q=3329 overnight fill  —  n={_args.n} β={_args.beta} "
          f"{_args.precision}-bit MPFR  max_tours={_args.max_tours}")
    print(f"  Range:      seeds {_args.start}..{_args.end}")
    print(f"  Already ok: {done_count}")
    print(f"  To run:     {len(todo)}")
    print(f"  Workers:    {_args.workers}")
    print(f"  Output dir: {OUTPUT_DIR}")
    print(f"  Started:    {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(hdr, flush=True)

    if not todo:
        print("Nothing to do.")
        return 0

    if _args.dry_run:
        print("DRY-RUN — no BKZ launched.")
        return 0

    PIPELINE.info(
        "overnight q3329 start",
        cat="sweep",
        n=_args.n, beta=_args.beta, precision=_args.precision,
        max_tours=_args.max_tours,
        to_run=len(todo), workers=_args.workers,
    )
    t_start = time.time()
    completed = 0

    with Pool(processes=_args.workers, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(_worker, todo):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0.0
            eta = (len(todo) - completed) / rate if rate > 0 else 0
            etastr = datetime.timedelta(seconds=int(eta))
            if r["status"] == "ok":
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={r['bkz_time']/3600:.2f}h  "
                      f"SDBKZ={r['sdbkz_time']/3600:.2f}h  "
                      f"wall={r['wall']/3600:.2f}h  "
                      f"ETA={etastr}", flush=True)
            else:
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"FAIL — {r['error']}", flush=True)

    elapsed = time.time() - t_start
    print(f"\nDone. {completed}/{len(todo)} seeds in {elapsed/3600:.2f} h.")
    PIPELINE.info(
        "overnight q3329 done",
        cat="sweep",
        n=_args.n, beta=_args.beta, precision=_args.precision,
        completed=completed, to_run=len(todo),
        elapsed_s=int(elapsed),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
