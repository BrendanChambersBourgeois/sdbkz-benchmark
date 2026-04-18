#!/usr/bin/env python3
"""
Parallel multi-seed BKZ vs SDBKZ dimension sweep.

Experiment: 11 dimensions x 3 block sizes x 100 seeds = 3300 runs
Fully resumable — scans results/raw/ at startup and skips completed work.

Usage:
    python3 sweep_parallel.py              # run full sweep
    python3 sweep_parallel.py --migrate    # only migrate old sweep_seed files
    python3 sweep_parallel.py --summary    # only regenerate summary.json
"""
import subprocess, sys, os, json, math, time, glob, signal, logging, datetime
import traceback as tb
import numpy as np
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger
from _math_core import ln_fixed_point
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
RAW_DIR = os.path.join(BASE, "results", "raw")
RESULTS_DIR = os.path.join(BASE, "results")
FAILED_FILE = os.path.join(RESULTS_DIR, "failed.json")
SUMMARY_FILE = os.path.join(RESULTS_DIR, "summary.json")
LOG_FILE = os.path.join(RESULTS_DIR, "progress.log")
CLAMP_LOG_FILE = os.path.join(RESULTS_DIR, "clamp_events.jsonl")


def _log_clamp(ctx, position, raw_value):
    """Append one defensive-clamp event to the side log. Never raises.

    Defensive clamps on get_r must log the raw value before substituting.
    This writes a JSONL side file instead of mutating the per-seed JSON
    schema, so SHA-256 reproducibility is preserved. POSIX atomic-append
    semantics (writes < PIPE_BUF) make this safe under multiprocessing
    workers.

    The `ctx` string should carry enough identifiers to correlate with
    the per-seed JSON (e.g. "n100_beta30_seed42 active_block"); the
    timestamp + progress.log give coarse correlation too.
    """
    import datetime
    try:
        os.makedirs(os.path.dirname(CLAMP_LOG_FILE), exist_ok=True)
        with open(CLAMP_LOG_FILE, "a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "script": "sweep_parallel",
                "ctx": ctx,
                "position": int(position),
                "raw_value": float(raw_value),
            }) + "\n")
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Install deps (idempotent)
# ---------------------------------------------------------------------------
def install_deps():
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
from fpylll import IntegerMatrix, LLL, BKZ, FPLLL, GSO


def build_lwe_kannan(n, m, q, seed=123):
    rng = np.random.RandomState(seed)
    s = rng.randint(0, 2, n).astype(int)
    e = rng.choice([-1, 0, 1], m).astype(int)
    A = rng.randint(0, q, (m, n)).astype(int)
    b = (A @ s + e) % q
    dim = m + n + 1
    L = [[0] * dim for _ in range(dim)]
    for i in range(m):
        L[i][i] = q
    for j in range(n):
        for i in range(m):
            L[m + j][i] = int(A[i][j])
    for j in range(n):
        L[m + j][m + j] = 1
    for i in range(m):
        L[m + n][i] = int(b[i])
    L[m + n][m + n] = 1
    return L, s, e


def _metrics_from_gso(M, dim, m, ln_profile, full=False, clamp_ctx=""):
    """Extract metrics from an already-updated GSO object.

    Always returns rankin profile (active block) and d(LN).
    If full=True, also returns gs_lognorms (full basis) and RHF.

    When fpylll's `get_r(i, i)` returns a non-positive value (the
    Cholesky-style GS cancellation at q=3329 n>=100, documented in
    paper §8), the raw value is logged to `results/clamp_events.jsonl`
    via `_log_clamp` before the 1e-300 substitution fires. Clamps are
    recorded in a side file instead of the per-seed JSON so SHA-256
    reproducibility is preserved.
    """
    start, size = m, dim - m

    def _safe_log_r(i, ctx_tag):
        r = M.get_r(i, i)
        if r > 0:
            return 0.5 * math.log(r)
        _log_clamp(f"{clamp_ctx} {ctx_tag}".strip(), i, r)
        return 0.5 * math.log(1e-300)

    # GS log-norms for active block (always needed for rankin)
    gs_log_active = [_safe_log_r(i, "active") for i in range(start, dim)]
    log_vol = sum(gs_log_active)
    rankin, cum = [], 0.0
    for idx, val in enumerate(gs_log_active):
        cum += val
        rankin.append(cum - ((idx + 1) / size) * log_vol)

    dln = float(np.mean(np.abs(np.array(rankin) - np.array(ln_profile))))
    result = {"rankin": rankin, "dln": dln}

    if full:
        gs_all = [_safe_log_r(i, "full") for i in range(dim)]
        log_b1 = gs_all[0]
        log_det_over_dim = sum(gs_all) / dim
        result["gs_lognorms"] = gs_all
        result["rhf"] = math.exp(log_b1 - log_det_over_dim)

    return result


# ---------------------------------------------------------------------------
# File path helpers
# ---------------------------------------------------------------------------
def result_path(n, beta, seed):
    return os.path.join(RAW_DIR, f"n{n}_beta{beta}_seed{seed}.json")


def scan_completed():
    """Return set of (n, beta, seed) tuples already completed."""
    done = set()
    for fp in glob.glob(os.path.join(RAW_DIR, "n*_beta*_seed*.json")):
        fname = os.path.basename(fp)
        try:
            parts = fname.replace(".json", "").split("_")
            n = int(parts[0][1:])
            beta = int(parts[1][4:])
            seed = int(parts[2][4:])
            done.add((n, beta, seed))
        except (IndexError, ValueError):
            continue
    return done


# ---------------------------------------------------------------------------
# Migrate old sweep_seed*.json files
# ---------------------------------------------------------------------------
def migrate_old_results():
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


def run_single(n, beta, seed, store_per_tour=False):
    """Run BKZ and SDBKZ on one (n, beta, seed). Returns result dict.

    When ``store_per_tour`` is True, the result additionally contains
    ``{variant}_rankin_per_tour``, ``{variant}_gs_lognorms_per_tour``, and
    ``{variant}_rhf_per_tour`` (one entry per executed tour). Default False
    preserves the lean v1.0 schema.
    """
    FPLLL.set_precision(PRECISION)
    FPLLL.set_random_seed(seed)

    max_tours = TOURS_BY_BETA[beta]
    m = n * 2
    dim = m + n + 1
    L, _, _ = build_lwe_kannan(n, m, Q, seed=seed)
    ln_p = ln_fixed_point(n + 1, beta)

    result = {
        "n": n, "beta": beta, "seed": seed, "q": Q, "max_tours": max_tours,
        "precision": PRECISION, "dim": dim, "m": m, "status": "completed",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    # Only add the key when fat-log mode is ON, so the default-off path
    # emits byte-for-byte the same JSON as the v1.0 dataset (SHA-256
    # reproducibility evidence lives in hash_verification.txt).
    if store_per_tour:
        result["store_per_tour"] = True

    # --- Initial quality (after LLL, before any BKZ) ---
    B_init = IntegerMatrix.from_matrix(L)
    LLL.reduction(B_init)
    M_init = GSO.Mat(B_init)
    M_init.update_gso()
    init = _metrics_from_gso(M_init, dim, m, ln_p, full=True)
    result["initial_dln"] = init["dln"]
    result["initial_rhf"] = init["rhf"]
    result["initial_rankin_profile"] = [float(x) for x in init["rankin"]]
    result["initial_gs_lognorms"] = [float(x) for x in init["gs_lognorms"]]

    # --- Run both variants ---
    for variant in ("bkz", "sdbkz"):
        B = IntegerMatrix.from_matrix(L)
        LLL.reduction(B)

        flags = BKZ.MAX_LOOPS | BKZ.AUTO_ABORT
        if variant == "sdbkz":
            flags |= BKZ.SD_VARIANT

        dln_per_tour = []
        deltas = []
        rankin_per_tour = []
        gs_lognorms_per_tour = []
        rhf_per_tour = []
        stag_tour = None
        stag_rankin = None
        stag_rhf = None
        stag_gs = None
        termination = "max_tours_reached"
        prev_rankin = init["rankin"]
        t0 = time.time()

        for t in range(1, max_tours + 1):
            param = BKZ.Param(beta, max_loops=1, flags=flags)
            BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)

            M = GSO.Mat(B)
            M.update_gso()
            if store_per_tour:
                metrics = _metrics_from_gso(M, dim, m, ln_p, full=True)
                rankin_per_tour.append([float(x) for x in metrics["rankin"]])
                gs_lognorms_per_tour.append(
                    [float(x) for x in metrics["gs_lognorms"]]
                )
                rhf_per_tour.append(float(metrics["rhf"]))
            else:
                metrics = _metrics_from_gso(M, dim, m, ln_p, full=False)
            dln_per_tour.append(metrics["dln"])

            delta = float(np.mean(np.abs(
                np.array(metrics["rankin"]) - np.array(prev_rankin)
            )))
            deltas.append(delta)

            if delta < 1e-6:
                stag_tour = t
                full_m = _metrics_from_gso(M, dim, m, ln_p, full=True)
                stag_rankin = [float(x) for x in full_m["rankin"]]
                stag_rhf = full_m["rhf"]
                stag_gs = [float(x) for x in full_m["gs_lognorms"]]
                termination = "stagnated"
                break

            prev_rankin = metrics["rankin"]

        elapsed = time.time() - t0
        tours_run = len(dln_per_tour)

        # If never stagnated, capture at final tour
        if stag_tour is None:
            stag_tour = tours_run
            M_final = GSO.Mat(B)
            M_final.update_gso()
            full_m = _metrics_from_gso(M_final, dim, m, ln_p, full=True)
            stag_rankin = [float(x) for x in full_m["rankin"]]
            stag_rhf = full_m["rhf"]
            stag_gs = [float(x) for x in full_m["gs_lognorms"]]

        result[f"{variant}_dln_per_tour"] = dln_per_tour
        result[f"{variant}_final_dln"] = dln_per_tour[-1]
        result[f"{variant}_tours_run"] = tours_run
        result[f"{variant}_termination"] = termination
        result[f"stagnation_tour_{variant}"] = stag_tour
        result[f"rankin_profile_{variant}"] = stag_rankin
        result[f"rhf_{variant}"] = stag_rhf
        result[f"gs_lognorms_{variant}"] = stag_gs
        if store_per_tour:
            result[f"{variant}_rankin_per_tour"] = rankin_per_tour
            result[f"{variant}_gs_lognorms_per_tour"] = gs_lognorms_per_tour
            result[f"{variant}_rhf_per_tour"] = rhf_per_tour
        result[f"{variant}_floor"] = float(np.mean(deltas[-5:]))
        result[f"{variant}_time"] = elapsed

    # --- Derived metrics ---
    result["advantage"] = result["bkz_final_dln"] - result["sdbkz_final_dln"]
    result["rhf_advantage"] = result["rhf_bkz"] - result["rhf_sdbkz"]

    # --- Crossover tour ---
    bkz_final = result["bkz_final_dln"]
    crossover = None
    for t_idx, sd_dln in enumerate(result["sdbkz_dln_per_tour"], 1):
        if sd_dln < bkz_final:
            crossover = t_idx
            break
    result["crossover_tour"] = crossover

    return result


# ---------------------------------------------------------------------------
# Worker with timeout and error handling
# ---------------------------------------------------------------------------
class _Timeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _Timeout()


def worker(args):
    """Process one (n, beta, seed) with timeout. Returns (key, status, path_or_error)."""
    n, beta, seed = args
    key = (n, beta, seed)
    out = result_path(n, beta, seed)

    timeout = TIMEOUT_BY_BETA[beta]
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout)

    try:
        result = run_single(n, beta, seed, store_per_tour=STORE_PER_TOUR)
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        return (key, "completed", out)

    except _Timeout:
        return (key, "timed_out", f"Exceeded {timeout}s")

    except Exception as exc:
        return (key, "failed", f"{type(exc).__name__}: {exc}")

    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


# ---------------------------------------------------------------------------
# Failed results tracker
# ---------------------------------------------------------------------------
def log_failure(key, reason):
    """Append a failure to results/failed.json."""
    n, beta, seed = key
    entry = {
        "n": n, "beta": beta, "seed": seed, "reason": reason,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
def generate_summary():
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
                s / max(b, 1e-9) for b, s in zip(bkz_times, sd_times)
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
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
def setup_logging():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    logger = logging.getLogger("sweep")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    migrate_only = "--migrate" in sys.argv
    summary_only = "--summary" in sys.argv
    if "--store-per-tour" in sys.argv:
        global STORE_PER_TOUR
        STORE_PER_TOUR = True

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
    with Pool(processes=NUM_WORKERS, maxtasksperchild=5) as pool:
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
