#!/usr/bin/env python3
"""
Parallel multi-seed BKZ vs SDBKZ dimension sweep.

Experiment: 11 dimensions x 3 block sizes x 100 seeds = 3300 runs
Fully resumable — scans results/seeds/main/q97/ at startup and skips completed work.

Usage:
    python3 sweep_parallel.py              # run full sweep
    python3 sweep_parallel.py --migrate    # only migrate old sweep_seed files
    python3 sweep_parallel.py --summary    # only regenerate summary.json
"""
from __future__ import annotations

import datetime
import glob
import json
import logging
import math
import os
import signal
import subprocess
import sys
import time
import traceback as tb
from multiprocessing import Pool
from typing import Any

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _math_core import (
    build_lwe_kannan,
    ln_fixed_point,
    log_clamp,
    metrics_from_gso,
)
from _seed_paths import seed_path_for
from _signal_utils import managed_pool
from log import get_logger, get_run_id, new_run_id

PIPELINE = get_logger("sweep_parallel")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NS = [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150]
BETAS = [20, 30, 40]
SEEDS = list(range(1, 101))
TOURS_BY_BETA = {20: 50, 30: 70, 40: 100}
TIMEOUT_BY_BETA = {20: 7200, 30: 14400, 40: 28800}  # 2h, 4h, 8h
Q = 97
PRECISION = 250
NUM_WORKERS = 22
SUMMARY_INTERVAL = 10       # regenerate summary every N completions

# BASE is the repo root. The script lives at scripts/sweep_parallel.py,
# so we need TWO dirname() calls — the first goes from sweep_parallel.py
# up to scripts/, the second goes from scripts/ up to the repo root.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# RAW_DIR kept as a read-side shim for legacy callers + back-compat
# symlinks left by the v1.3 migration (ac52379). Writes go via
# _seed_paths.seed_path_for("main", ...) below.
RAW_DIR = os.path.join(BASE, "results", "raw")
RESULTS_DIR = os.path.join(BASE, "results")
# v1.3: main-campaign writes land under results/seeds/main/q97/...
MAIN_SEEDS_DIR = os.path.join(BASE, "results", "seeds", "main", "q97")
FAILED_FILE = os.path.join(RESULTS_DIR, "failed.json")
SUMMARY_FILE = os.path.join(RESULTS_DIR, "summary.json")
CLAMP_LOG_FILE = os.path.join(RESULTS_DIR, "clamp_events.jsonl")


def _log_clamp(ctx: str, position: int, raw_value: float) -> None:
    log_clamp(ctx, position, raw_value,
              script_name="sweep_parallel", log_path=CLAMP_LOG_FILE)

# ---------------------------------------------------------------------------
# Install deps (idempotent)
# ---------------------------------------------------------------------------
def install_deps() -> None:
    reqs = os.path.join(BASE, "requirements.txt")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", reqs, "-q",
             "--break-system-packages"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

# ---------------------------------------------------------------------------
# Core lattice helpers (self-contained for multiprocessing workers)
# ---------------------------------------------------------------------------
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix


def _metrics_from_gso(
    M: Any, dim: int, m: int, ln_profile: list[float],
    full: bool = False, clamp_ctx: str = "",
) -> dict[str, Any]:
    return metrics_from_gso(
        M, dim, m, ln_profile, full=full, clamp_ctx=clamp_ctx,
        log_clamp_fn=_log_clamp,
    )


# ---------------------------------------------------------------------------
# File path helpers
# ---------------------------------------------------------------------------
def result_path(n: int, beta: int, seed: int) -> str:
    return seed_path_for("main", n=n, beta=beta, seed=seed, base=BASE)


def scan_completed() -> set[tuple[int, int, int]]:
    """Return set of (n, beta, seed) tuples already completed.

    Walks the v1.3 layout (results/seeds/main/q97/...). The legacy
    results/raw/ glob fallback was retired at v2.0.0 alongside the
    symlink drop; the back-compat tree no longer exists. Seeds under
    `_cloud` suffixes are treated as the same (n, β, seed) triple —
    the paper §3.7 dual-copy preservation means one completion is
    enough to skip re-running.
    """
    done = set()
    # v1.3 layout: results/seeds/main/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}[_cloud].json
    for fp in glob.glob(os.path.join(
            MAIN_SEEDS_DIR, "n*_beta*", "seed*.json")):
        leaf = os.path.basename(fp)
        parent = os.path.basename(os.path.dirname(fp))
        try:
            n = int(parent.split("_")[0][1:])
            beta = int(parent.split("_")[1][4:])
            seed_digits = leaf.replace(".json", "").replace("_cloud", "")
            seed = int(seed_digits[4:])  # drop "seed" prefix
            done.add((n, beta, seed))
        except (IndexError, ValueError):
            continue
    return done


# ---------------------------------------------------------------------------
# Migrate old sweep_seed*.json files
# ---------------------------------------------------------------------------
def migrate_old_results() -> int:
    """Convert old sweep_seed{N}.json -> individual results/raw/ files."""
    old_files = sorted(glob.glob(os.path.join(BASE, "sweep_seed*.json")))
    if not old_files:
        print("No old sweep_seed files found to migrate.")
        return 0

    migrated = 0
    for fp in old_files:
        fname = os.path.basename(fp)
        try:
            seed = int(fname.replace("sweep_seed", "").replace(".json", ""))
        except ValueError:
            continue

        with open(fp) as f:
            data = json.load(f)

        for row in data.get("results", []):
            n = row.get("n")
            if n is None or "advantage" not in row:
                continue

            # Old data was generated with BETA=20
            out = result_path(n, 20, seed)
            if os.path.exists(out):
                continue

            migrated_row = {
                "n": n,
                "beta": 20,
                "seed": seed,
                "q": Q,
                "max_tours": 30,
                "precision": PRECISION,
                "dim": n * 2 + n + 1,
                "m": n * 2,
                "status": "migrated",
                "migrated_from": fname,
                "bkz_final_dln": row["bkz_final_dln"],
                "sdbkz_final_dln": row["sdbkz_final_dln"],
                "advantage": row["advantage"],
                "bkz_floor": row["bkz_floor"],
                "sdbkz_floor": row["sdbkz_floor"],
                "bkz_time": row["bkz_time"],
                "sdbkz_time": row["sdbkz_time"],
            }
            with open(out, "w") as f:
                json.dump(migrated_row, f, indent=2)
            migrated += 1

    print(f"Migrated {migrated} results from {len(old_files)} old files.")
    return migrated


# ---------------------------------------------------------------------------
# Single run: one (n, beta, seed) comparison
# ---------------------------------------------------------------------------
# Fat-log toggle: when True, run_single additionally records the full
# per-tour Rankin profile, Gram–Schmidt log-norms, and RHF for every tour
# of each variant (~10x JSON size, ~0.1% extra compute). Off by default so
# the v1.0 dataset schema stays lean and SHA-256 reproducibility holds.
# Flip via --store-per-tour at the command line or by editing this default.
STORE_PER_TOUR = False


from _bkz_core import run_single as _bkz_core_run_single


def run_single(
    n: int, beta: int, seed: int, store_per_tour: bool = False,
) -> dict[str, Any]:
    """Thin wrapper: feeds the canonical BKZ driver with sweep_parallel
    conventions (Q=97, PRECISION=250, TOURS_BY_BETA, plain floor metric)."""
    return _bkz_core_run_single(
        n=n, beta=beta, seed=seed,
        q=Q, precision=PRECISION,
        max_tours=TOURS_BY_BETA[beta],
        log_clamp_fn=_log_clamp,
        store_per_tour=store_per_tour,
        floor_mode="plain",
    )


# ---------------------------------------------------------------------------
# Worker with timeout and error handling
# ---------------------------------------------------------------------------
class _Timeout(Exception):
    pass


def _alarm_handler(signum: int, frame: Any) -> None:
    raise _Timeout()


def worker(
    args: tuple[int, int, int],
) -> tuple[tuple[int, int, int], str, str]:
    """Process one (n, beta, seed) with timeout. Returns (key, status, path_or_error)."""
    n, beta, seed = args
    key = (n, beta, seed)
    out = result_path(n, beta, seed)

    timeout = TIMEOUT_BY_BETA[beta]
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout)

    try:
        result = run_single(n, beta, seed, store_per_tour=STORE_PER_TOUR)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        return (key, "completed", out)

    except _Timeout:
        PIPELINE.error("worker timed_out", cat="sweep",
                       n=n, beta=beta, seed=seed, timeout_s=timeout)
        return (key, "timed_out", f"Exceeded {timeout}s")

    except Exception as exc:
        PIPELINE.error("worker failed", cat="sweep",
                       n=n, beta=beta, seed=seed,
                       exc_type=type(exc).__name__, exc_msg=str(exc),
                       traceback=tb.format_exc())
        return (key, "failed", f"{type(exc).__name__}: {exc}")

    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


# ---------------------------------------------------------------------------
# Failed results tracker
# ---------------------------------------------------------------------------
def log_failure(key: tuple[int, int, int], reason: str) -> None:
    """Append a failure to results/failed.json."""
    n, beta, seed = key
    entry = {
        "n": n, "beta": beta, "seed": seed, "reason": reason,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    failures = []
    if os.path.exists(FAILED_FILE):
        with open(FAILED_FILE) as f:
            failures = json.load(f)
    failures.append(entry)
    with open(FAILED_FILE, "w") as f:
        json.dump(failures, f, indent=2)


# ---------------------------------------------------------------------------
# Summary generator
# ---------------------------------------------------------------------------
def generate_summary() -> dict[str, Any] | None:
    """Read all raw results, produce results/summary.json."""
    raw_files = glob.glob(os.path.join(RAW_DIR, "n*_beta*_seed*.json"))
    if not raw_files:
        print("No raw results found.")
        return

    # Load all results
    all_results = []
    for fp in raw_files:
        with open(fp) as f:
            try:
                all_results.append(json.load(f))
            except json.JSONDecodeError:
                continue

    # Group by (n, beta)
    groups = {}
    for r in all_results:
        key = (r["n"], r["beta"])
        groups.setdefault(key, []).append(r)

    by_n_beta = {}
    for (n, beta), rows in sorted(groups.items()):
        k = f"{n}_{beta}"
        num = len(rows)

        # Basic metrics (available in all results including migrated)
        advantages = [r["advantage"] for r in rows if "advantage" in r]
        bkz_dlns = [r["bkz_final_dln"] for r in rows if "bkz_final_dln" in r]
        sd_dlns = [r["sdbkz_final_dln"] for r in rows if "sdbkz_final_dln" in r]
        bkz_times = [r["bkz_time"] for r in rows if "bkz_time" in r]
        sd_times = [r["sdbkz_time"] for r in rows if "sdbkz_time" in r]

        entry = {
            "n": n, "beta": beta, "num_seeds": num,
            "mean_advantage": float(np.mean(advantages)) if advantages else None,
            "std_advantage": float(np.std(advantages)) if advantages else None,
            "win_rate": float(np.mean([1 if a > 0 else 0 for a in advantages])) if advantages else None,
            "mean_bkz_dln": float(np.mean(bkz_dlns)) if bkz_dlns else None,
            "mean_sdbkz_dln": float(np.mean(sd_dlns)) if sd_dlns else None,
            "mean_runtime_ratio": float(np.mean([
                s / max(b, 1e-9) for b, s in zip(bkz_times, sd_times, strict=False)
            ])) if bkz_times and sd_times else None,
        }

        # Rich metrics (only from full runs, not migrated)
        full_rows = [r for r in rows if r.get("status") == "completed"]

        # Stagnation tours
        stag_bkz = [r["stagnation_tour_bkz"] for r in full_rows if "stagnation_tour_bkz" in r]
        stag_sd = [r["stagnation_tour_sdbkz"] for r in full_rows if "stagnation_tour_sdbkz" in r]
        entry["mean_stagnation_tour_bkz"] = float(np.mean(stag_bkz)) if stag_bkz else None
        entry["mean_stagnation_tour_sdbkz"] = float(np.mean(stag_sd)) if stag_sd else None

        # Crossover tours
        cross = [r["crossover_tour"] for r in full_rows if r.get("crossover_tour") is not None]
        entry["mean_crossover_tour"] = float(np.mean(cross)) if cross else None
        entry["num_crossover"] = len(cross)

        # RHF advantage
        rhf_adv = [r["rhf_advantage"] for r in full_rows if "rhf_advantage" in r]
        entry["mean_rhf_advantage"] = float(np.mean(rhf_adv)) if rhf_adv else None
        entry["std_rhf_advantage"] = float(np.std(rhf_adv)) if rhf_adv else None

        # Per-tour d(LN) averaged across seeds
        # With early exit, arrays may differ in length — pad shorter ones
        # by repeating their final value (stagnated value) to max_tours
        max_t = TOURS_BY_BETA.get(beta, 30)
        for prefix in ("bkz", "sdbkz"):
            key_name = f"{prefix}_dln_per_tour"
            tours_list = [r[key_name] for r in full_rows if key_name in r]
            if tours_list:
                padded = []
                for tl in tours_list:
                    if len(tl) < max_t:
                        tl = tl + [tl[-1]] * (max_t - len(tl))
                    padded.append(tl[:max_t])
                arr = np.array(padded)
                entry[f"mean_{key_name}"] = arr.mean(axis=0).tolist()
                entry[f"std_{key_name}"] = arr.std(axis=0).tolist()

        # Mean Rankin profiles at stagnation
        rp_bkz = [r["rankin_profile_bkz"] for r in full_rows if "rankin_profile_bkz" in r]
        rp_sd = [r["rankin_profile_sdbkz"] for r in full_rows if "rankin_profile_sdbkz" in r]
        if rp_bkz:
            entry["mean_rankin_profile_bkz"] = np.mean(rp_bkz, axis=0).tolist()
        if rp_sd:
            entry["mean_rankin_profile_sdbkz"] = np.mean(rp_sd, axis=0).tolist()

        # Mean GS log-norm profiles at stagnation
        gs_bkz = [r["gs_lognorms_bkz"] for r in full_rows if "gs_lognorms_bkz" in r]
        gs_sd = [r["gs_lognorms_sdbkz"] for r in full_rows if "gs_lognorms_sdbkz" in r]
        if gs_bkz:
            entry["mean_gs_lognorms_bkz"] = np.mean(gs_bkz, axis=0).tolist()
        if gs_sd:
            entry["mean_gs_lognorms_sdbkz"] = np.mean(gs_sd, axis=0).tolist()

        # Mean initial profiles
        init_rp = [r["initial_rankin_profile"] for r in full_rows if "initial_rankin_profile" in r]
        init_gs = [r["initial_gs_lognorms"] for r in full_rows if "initial_gs_lognorms" in r]
        if init_rp:
            entry["mean_initial_rankin_profile"] = np.mean(init_rp, axis=0).tolist()
        if init_gs:
            entry["mean_initial_gs_lognorms"] = np.mean(init_gs, axis=0).tolist()

        by_n_beta[k] = entry

    total = len(all_results)
    failed_count = 0
    if os.path.exists(FAILED_FILE):
        with open(FAILED_FILE) as f:
            failed_count = len(json.load(f))

    summary = {
        "meta": {
            "total_completed": total,
            "total_failed": failed_count,
            "last_updated": datetime.datetime.now(datetime.UTC).isoformat(),
            "dimensions": NS,
            "betas": BETAS,
            "tours_by_beta": TOURS_BY_BETA,
            "timeout_by_beta": TIMEOUT_BY_BETA,
            "precision": PRECISION,
        },
        "by_n_beta": by_n_beta,
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Summary written: {total} completed, {failed_count} failed → {SUMMARY_FILE}")
    return summary


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    logger = logging.getLogger("sweep")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    summary_only = "--summary" in sys.argv
    if "--store-per-tour" in sys.argv:
        global STORE_PER_TOUR
        STORE_PER_TOUR = True

    # Tag every event from this run with a single correlation id so
    # parent + workers + any subprocess descendants group together
    # in pipeline.jsonl. Inherits via BKZ_RUN_ID env if already set.
    if not get_run_id():
        new_run_id()

    # v1.3: parent for new-layout writes. Leaf dirs (n{n}_beta{beta}/)
    # are created on-demand in worker(). RAW_DIR still exists as a
    # transition shim holding symlinks into the new tree.
    os.makedirs(MAIN_SEEDS_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    if summary_only:
        generate_summary()
        return

    logger = setup_logging()

    # Step 1: Install deps
    install_deps()

    # Step 2: Migration disabled — old sweep_seed files removed
    n_migrated = 0

    # Step 3: Build work list, skipping completed
    completed = scan_completed()
    all_tasks = [
        (n, beta, seed)
        for n in NS for beta in BETAS for seed in SEEDS
    ]
    pending = [t for t in all_tasks if t not in completed]

    total_experiment = len(all_tasks)
    already_done = len(completed)

    logger.info(f"Experiment: {total_experiment} total runs")
    logger.info(f"  Already completed: {already_done} (including {n_migrated} migrated)")
    logger.info(f"  Remaining: {len(pending)}")
    logger.info(f"  Workers: {NUM_WORKERS}, Timeouts: {TIMEOUT_BY_BETA}")

    PIPELINE.info(
        "sweep start",
        cat="sweep",
        total=total_experiment,
        already_done=already_done,
        pending=len(pending),
        workers=NUM_WORKERS,
        q=Q,
        precision=PRECISION,
        store_per_tour=STORE_PER_TOUR,
    )

    if not pending:
        logger.info("Nothing to do — all runs already completed.")
        generate_summary()
        return

    # Step 4: Run with Pool
    n_done = 0
    n_failed = 0
    wins = 0
    total_pending = len(pending)
    t_start = time.time()

    # maxtasksperchild prevents memory leaks in long fpylll sessions
    with managed_pool(processes=NUM_WORKERS, maxtasksperchild=5,
                      label="sweep_parallel") as pool:
        for key, status, detail in pool.imap_unordered(worker, pending):
            n_done += 1
            n_val, beta_val, seed_val = key
            elapsed_total = time.time() - t_start
            rate = n_done / elapsed_total if elapsed_total > 0 else 0
            eta_s = (total_pending - n_done) / rate if rate > 0 else 0
            eta_str = str(datetime.timedelta(seconds=int(eta_s)))

            if status == "completed":
                # Read advantage for win-rate tracking
                try:
                    with open(result_path(*key)) as f:
                        adv = json.load(f).get("advantage", 0)
                    if adv > 0:
                        wins += 1
                except Exception:
                    adv = 0
                wr = wins / n_done * 100
                logger.info(
                    f"[{n_done}/{total_pending}] n={n_val} β={beta_val} seed={seed_val} "
                    f"DONE  adv={adv:.4f}  win_rate={wr:.0f}%  ETA={eta_str}"
                )
            else:
                n_failed += 1
                log_failure(key, detail)
                logger.info(
                    f"[{n_done}/{total_pending}] n={n_val} β={beta_val} seed={seed_val} "
                    f"{status.upper()}: {detail}  ETA={eta_str}"
                )

            # Regenerate summary every SUMMARY_INTERVAL completions
            if n_done % SUMMARY_INTERVAL == 0:
                try:
                    generate_summary()
                except Exception as exc:
                    logger.warning(f"Summary generation failed: {exc}")

    elapsed = time.time() - t_start
    logger.info(f"All done: {n_done} processed ({n_failed} failed) in {elapsed:.0f}s")
    PIPELINE.info(
        "sweep complete",
        cat="sweep",
        processed=n_done,
        failed=n_failed,
        wins=wins,
        win_rate_pct=(wins / n_done * 100) if n_done else 0,
        elapsed_s=int(elapsed),
    )

    # Final summary
    generate_summary()

    # Force exit to prevent fpylll C library cleanup deadlock
    import sys as _sys
    _sys.stdout.flush()
    _sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
