#!/usr/bin/env python3
"""
Cloud-native BKZ vs SDBKZ benchmark runner.

Runs ONE (n, beta) group (100 seeds), writes results to S3.
Designed for AWS Batch / Fargate. Fully resumable — checks S3 for
completed seeds before starting.

Usage:
    python3 sweep_cloud.py --n 100 --beta 30 --bucket bkz-benchmark-results
    python3 sweep_cloud.py --n 100 --beta 30 --bucket my-bucket --seeds 1-50
    python3 sweep_cloud.py --n 100 --beta 30 --output ./local_results/  # local mode

Environment variables (set by AWS Batch automatically):
    AWS_DEFAULT_REGION    (or pass --region)
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import signal
import sys
import threading
import time
import traceback as tb
from multiprocessing import Pool, cpu_count
from typing import Any

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _math_core import (
    ln_fixed_point,
    log_clamp,
    metrics_from_gso,
)
from generators import build_lwe_kannan
from log import get_logger, get_run_id, new_run_id

PIPELINE = get_logger("sweep_cloud")

# ---------------------------------------------------------------------------
# Configuration (matches sweep_parallel.py exactly)
# ---------------------------------------------------------------------------
TOURS_BY_BETA = {20: 50, 30: 70, 40: 100}
Q = 97
PRECISION = 250

# Max expected per-seed runtime in seconds, by beta.
# Watchdog triggers at 2x this if no seed completes.
# Note: q=3329 at 500-bit precision takes ~5-6h per seed at β=30.
# These values must cover the slowest expected seed for any q/precision.
# Cross-ref: cloud_watchdog.sh has its own external idle timeouts.
# NOTE: q=3329 at 1000-bit precision may take 10-15h per seed at β=30.
# Timeout is scaled up below when q > 97 to avoid watchdog kills.
MAX_SEED_TIME = {20: 3600, 30: 21600, 40: 43200}  # 1h, 6h, 12h
MAX_SEED_TIME_Q3329 = {20: 7200, 30: 57600, 40: 86400}  # 2h, 16h, 24h


# ---------------------------------------------------------------------------
# SIGTERM handler: clean exit on Batch termination / spot reclaim
# ---------------------------------------------------------------------------
def _sigterm_handler(signum: int, frame: Any) -> None:
    print("\nSIGTERM received. Flushing and exiting.", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)

signal.signal(signal.SIGTERM, _sigterm_handler)


# ---------------------------------------------------------------------------
# Watchdog: force exit if no progress for 2x max seed time
# Note: in-process watchdog timeout is 2x MAX_SEED_TIME.
# External cloud_watchdog.sh has its own timeout (2h/4h/24h by beta).
# If tuning one, check the other to avoid conflicts.
# ---------------------------------------------------------------------------
_watchdog_lock = threading.Lock()
_last_completion = time.time()


def watchdog_ping() -> None:
    """Call after each seed completion to reset the watchdog timer."""
    global _last_completion
    with _watchdog_lock:
        _last_completion = time.time()


def _watchdog_thread(timeout: float) -> None:
    """Background thread that force-exits if no seed completes within timeout."""
    while True:
        time.sleep(60)
        with _watchdog_lock:
            idle = time.time() - _last_completion
        if idle > timeout:
            print(f"\nWATCHDOG: No seed completed in {idle:.0f}s (limit {timeout}s). "
                  f"Force exiting to prevent fpylll hang.", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(42)  # Distinct from clean exit (0) — visible in Batch dashboard

# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------
def s3_key(n: int, beta: int, seed: int, q: int = 97) -> str:
    # v2.0.0: canonical seed paths come from `_seed_paths.seed_path_for`.
    # Cloud campaign was decommissioned 2026-04-10; this function is
    # dead code until a future cloud restart, at which point the new
    # S3 prefix tree will match the on-disk `results/seeds/<campaign>/`
    # layout (no symlink fallback exists post-v2).
    from _seed_paths import seed_path_for
    campaign = "main" if q == 97 else "q3329"
    return seed_path_for(campaign, n, beta, seed, q=q, cloud=True)


def s3_upload(local_path: str, bucket: str, key: str) -> None:
    """Upload a file to S3."""
    import boto3
    s3 = boto3.client("s3")
    s3.upload_file(local_path, bucket, key)


def s3_validate(
    bucket: str, key: str,
    expected_keys: tuple[str, ...] = ("n", "beta", "seed", "advantage"),
) -> bool:
    """Read back an S3 object and validate it's valid JSON with expected keys.
    Returns True if valid, False if corrupt. Deletes corrupt files."""
    import boto3
    s3 = boto3.client("s3")
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        for k in expected_keys:
            if k not in data:
                print(f"  S3 VALIDATION FAILED: {key} missing key '{k}'. Deleting.", flush=True)
                s3.delete_object(Bucket=bucket, Key=key)
                return False
        return True
    except Exception as e:
        print(f"  S3 VALIDATION FAILED: {key} — {e}. Deleting.", flush=True)
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except Exception:
            pass
        return False


def s3_list_completed(
    bucket: str, n: int, beta: int, q: int = 97,
) -> set[int]:
    """Check S3 for already-completed seeds. Returns set of seed numbers."""
    import re

    import boto3
    s3 = boto3.client("s3")
    # v2.0.0: S3 prefix tracks the v1.3 on-disk layout. The cloud
    # campaign is decommissioned; this path is exercised only by a
    # future restart, which would land seeds under
    # `results/seeds/<campaign>/q97/n{n}_beta{beta}/seed{seed:04d}_cloud.json`
    # — matching the on-disk tree exactly.
    from _seed_paths import seed_dir_for
    campaign = "main" if q == 97 else "q3329"
    prefix = seed_dir_for(campaign, n, beta, q=q) + "/seed"
    pattern = re.compile(r"^seed(\d{4})_cloud\.json$")
    done = set()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                fname = obj["Key"].split("/")[-1]
                m = pattern.match(fname)
                if m:
                    done.add(int(m.group(1)))
    except Exception as e:
        print(f"Warning: could not list S3 objects: {e}")
    return done


def local_list_completed(output_dir: str, n: int, beta: int) -> set[int]:
    """Check local dir for completed seeds."""
    import glob
    import re
    pattern = re.compile(rf"^n{n}_beta{beta}_seed(\d+)\.json$")
    done = set()
    for fp in glob.glob(os.path.join(output_dir, f"n{n}_beta{beta}_seed*.json")):
        m = pattern.match(os.path.basename(fp))
        if m:
            done.add(int(m.group(1)))
    return done


# ---------------------------------------------------------------------------
# Core lattice helpers (copied verbatim from sweep_parallel.py)
# ---------------------------------------------------------------------------
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix


def _log_clamp_cloud(ctx: str, position: int, raw_value: float) -> None:
    """Cloud-container wrapper — writes to /tmp/clamp_events.jsonl
    inside the AWS Batch Docker container; the entrypoint uploads it
    alongside each per-seed result."""
    log_clamp(ctx, position, raw_value,
              script_name="sweep_cloud", log_path="/tmp/clamp_events.jsonl")


def _metrics_from_gso(
    M: Any, dim: int, m: int, ln_profile: list[float],
    full: bool = False, clamp_ctx: str = "",
) -> dict[str, Any]:
    return metrics_from_gso(
        M, dim, m, ln_profile, full=full, clamp_ctx=clamp_ctx,
        log_clamp_fn=_log_clamp_cloud,
    )


# ---------------------------------------------------------------------------
# Single run (copied from sweep_parallel.py with minimal changes)
# ---------------------------------------------------------------------------
# Fat-log toggle: see sweep_parallel.py for full commentary. Off by default
# so the v1.0 dataset schema stays lean and SHA-256 reproducibility holds.
STORE_PER_TOUR = False


from _bkz_core import run_single as _bkz_core_run_single


def run_single(
    n: int, beta: int, seed: int,
    q: int | None = None, precision: int | None = None,
    store_per_tour: bool = False,
) -> dict[str, Any]:
    """Thin wrapper: feeds the canonical BKZ driver with sweep_cloud
    conventions (q/precision overridable, TOURS_BY_BETA, safe floor)."""
    return _bkz_core_run_single(
        n=n, beta=beta, seed=seed,
        q=q if q is not None else Q,
        precision=precision if precision is not None else PRECISION,
        max_tours=TOURS_BY_BETA[beta],
        log_clamp_fn=_log_clamp_cloud,
        store_per_tour=store_per_tour,
        floor_mode="safe",
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def worker(
    args: tuple[int, int, int, str | None, str | None, int, int, bool],
) -> tuple[tuple[int, int, int], str, Any]:
    n, beta, seed, bucket, output_dir, q, precision, store_per_tour = args
    key = (n, beta, seed)

    try:
        result = run_single(n, beta, seed, q=q, precision=precision,
                            store_per_tour=store_per_tour)

        # Write locally first
        local_path = f"/tmp/n{n}_beta{beta}_seed{seed}.json"
        with open(local_path, "w") as f:
            json.dump(result, f, indent=2)

        # Upload to S3 and validate
        if bucket:
            s3_k = s3_key(n, beta, seed, q=q)
            s3_upload(local_path, bucket, s3_k)
            if not s3_validate(bucket, s3_k):
                # Retry once
                s3_upload(local_path, bucket, s3_k)
                if not s3_validate(bucket, s3_k):
                    os.remove(local_path)
                    return (key, "failed", "S3 validation failed after retry")

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            import shutil
            shutil.copy2(local_path, os.path.join(output_dir, f"n{n}_beta{beta}_seed{seed}.json"))

        os.remove(local_path)
        return (key, "completed", result.get("advantage", 0))

    except Exception as exc:
        PIPELINE.error("worker failed", cat="sweep",
                       n=n, beta=beta, seed=seed,
                       exc_type=type(exc).__name__, exc_msg=str(exc),
                       traceback=tb.format_exc())
        return (key, "failed", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not get_run_id():
        new_run_id()
    parser = argparse.ArgumentParser(description="Cloud BKZ benchmark runner")
    parser.add_argument("--n", type=int, required=True, help="LWE dimension")
    parser.add_argument("--beta", type=int, required=True, help="Block size")
    parser.add_argument("--bucket", type=str, default=None, help="S3 bucket name")
    parser.add_argument("--output", type=str, default=None, help="Local output directory")
    parser.add_argument("--seeds", type=str, default=None, help="Seed range, e.g. 1-100")
    parser.add_argument("--seed-start", type=int, default=None, help="Start seed (alternative to --seeds)")
    parser.add_argument("--seed-end", type=int, default=None, help="End seed (alternative to --seeds)")
    parser.add_argument("--workers", type=int, default=None, help="Number of workers (default: CPU count - 2)")
    parser.add_argument("--q", type=int, default=97, help="LWE modulus (default: 97)")
    parser.add_argument("--precision", type=int, default=None,
                        help="MPFR precision in bits (default: 250 for q<=97, 500 for larger q)")
    parser.add_argument("--store-per-tour", action="store_true",
                        help="Record full per-tour Rankin/GS/RHF (fat-log schema, ~10x JSON). Off by default.")
    args = parser.parse_args()
    store_per_tour = args.store_per_tour or STORE_PER_TOUR

    if not args.bucket and not args.output:
        print("ERROR: specify --bucket (S3) and/or --output (local directory)")
        sys.exit(1)

    # Parse seed range
    global Q, PRECISION
    Q = args.q
    PRECISION = args.precision if args.precision else (250 if Q <= 97 else 500)

    if args.seed_start is not None and args.seed_end is not None:
        seed_start, seed_end = args.seed_start, args.seed_end
    elif args.seeds:
        parts = args.seeds.split("-")
        seed_start, seed_end = int(parts[0]), int(parts[1])
    else:
        seed_start, seed_end = 1, 100
    all_seeds = list(range(seed_start, seed_end + 1))

    # Determine workers
    num_workers = args.workers or max(1, cpu_count() - 2)

    # Check what's already done
    completed = set()
    if args.bucket:
        completed = s3_list_completed(args.bucket, args.n, args.beta, q=Q)
    if args.output:
        completed |= local_list_completed(args.output, args.n, args.beta)

    pending_seeds = [s for s in all_seeds if s not in completed]

    print("=" * 70)
    print("BKZ Benchmark — Cloud Runner")
    print(f"  n={args.n}, beta={args.beta}, q={Q}, precision={PRECISION}")
    print(f"  Seeds: {seed_start}-{seed_end} ({len(all_seeds)} total)")
    print(f"  Already completed: {len(completed)}")
    print(f"  Pending: {len(pending_seeds)}")
    print(f"  Workers: {num_workers}")
    print(f"  Output: {args.bucket or ''} {args.output or ''}")
    print("=" * 70)

    PIPELINE.info(
        "sweep start",
        cat="sweep",
        n=args.n, beta=args.beta, q=Q, precision=PRECISION,
        seeds_pending=len(pending_seeds),
        seeds_completed=len(completed),
        workers=num_workers,
        output_bucket=args.bucket, output_dir=args.output,
        store_per_tour=store_per_tour,
    )

    if not pending_seeds:
        print("All seeds already completed.")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    # Start watchdog thread (longer timeout for q=3329 high-precision runs)
    seed_times = MAX_SEED_TIME_Q3329 if Q > 97 else MAX_SEED_TIME
    wd_timeout = seed_times.get(args.beta, 14400) * 2
    print(f"  Watchdog: {wd_timeout}s timeout (2x max seed time for β={args.beta})")
    wd = threading.Thread(target=_watchdog_thread, args=(wd_timeout,), daemon=True)
    wd.start()
    watchdog_ping()

    # Build task list
    tasks = [(args.n, args.beta, seed, args.bucket, args.output, Q, PRECISION, store_per_tour) for seed in pending_seeds]

    n_done = 0
    n_failed = 0
    wins = 0
    t_start = time.time()

    with Pool(processes=num_workers, maxtasksperchild=5) as pool:
        for key, status, detail in pool.imap_unordered(worker, tasks):
            n_done += 1
            watchdog_ping()
            n_val, beta_val, seed_val = key
            elapsed = time.time() - t_start
            rate = n_done / elapsed if elapsed > 0 else 0
            eta_s = (len(pending_seeds) - n_done) / rate if rate > 0 else 0

            if status == "completed":
                adv = detail
                if adv > 0:
                    wins += 1
                wr = wins / n_done * 100
                print(f"[{n_done}/{len(pending_seeds)}] seed={seed_val} "
                      f"adv={adv:.4f} win_rate={wr:.0f}% "
                      f"ETA={datetime.timedelta(seconds=int(eta_s))}")
            else:
                n_failed += 1
                print(f"[{n_done}/{len(pending_seeds)}] seed={seed_val} "
                      f"FAILED: {detail}")

    elapsed = time.time() - t_start
    print(f"\nDone: {n_done} processed ({n_failed} failed) in {elapsed:.0f}s")
    PIPELINE.info(
        "sweep complete",
        cat="sweep",
        n=args.n, beta=args.beta,
        processed=n_done, failed=n_failed, wins=wins,
        win_rate_pct=(wins / n_done * 100) if n_done else 0,
        elapsed_s=int(elapsed),
    )
    n_success = n_done - n_failed
    if n_success > 0:
        print(f"Win rate: {wins}/{n_success} = {wins/n_success*100:.0f}%")
    else:
        print("Win rate: N/A (all seeds failed)")

    # Force exit to prevent fpylll C library cleanup deadlock
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
