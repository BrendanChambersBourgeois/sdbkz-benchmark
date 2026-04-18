#!/usr/bin/env python3
"""
q=3329 verification run — matches sweep_parallel.py exactly.

Run with:
    nice -n 19 python3 scripts/q3329_verify.py &

Safe to run alongside the main sweep. Single-threaded, lowest priority.
Outputs to <repo_root>/results/q3329/.
"""
import os, sys, json, math, time, datetime
import numpy as np

from fpylll import IntegerMatrix, LLL, BKZ, FPLLL, GSO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger
from _math_core import ln_fixed_point
PIPELINE = get_logger("q3329_verify")

# -- Config -------------------------------------------------------------------
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="q=3329 verification run")
    parser.add_argument("--n", type=int, default=50, help="Secret dimension (default: 50)")
    parser.add_argument("--beta", type=int, default=30, help="Block size (default: 30)")
    parser.add_argument("--seeds", type=int, default=20, help="Number of seeds (default: 20)")
    parser.add_argument("--precision", type=int, default=None,
                        help="MPFR precision in bits (default: 500 for q=3329)")
    return parser.parse_args()

_args = parse_args()

Q = 3329          # ML-KEM modulus (main sweep uses 97)
N = _args.n
BETA = _args.beta
TOURS_BY_BETA = {20: 50, 30: 70, 40: 100}
MAX_TOURS = TOURS_BY_BETA.get(BETA, 70)
PRECISION = _args.precision if _args.precision else 500
SEEDS = list(range(1, _args.seeds + 1))

# BASE is the repo root. Two dirname() calls because this script lives
# at scripts/q3329_verify.py — the first goes to scripts/, the second
# to the repo root.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE, "results", "q3329")
os.makedirs(OUTPUT_DIR, exist_ok=True)
CLAMP_LOG_FILE = os.path.join(BASE, "results", "clamp_events.jsonl")


def _log_clamp(ctx, position, raw_value):
    """Append one defensive-clamp event to the side log. Never raises.

    Defensive clamps on get_r log the raw value to a JSONL side file
    before the 1e-300 substitution fires, so SHA-256 reproducibility
    of the per-seed JSON schema is preserved and the raw non-positive
    value stays auditable for paper §8 analyses.
    """
    import datetime
    try:
        os.makedirs(os.path.dirname(CLAMP_LOG_FILE), exist_ok=True)
        with open(CLAMP_LOG_FILE, "a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "script": "q3329_verify",
                "ctx": ctx,
                "position": int(position),
                "raw_value": float(raw_value),
            }) + "\n")
    except OSError:
        pass


# -- Copied verbatim from sweep_parallel.py -----------------------------------

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
    start, size = m, dim - m
    n_clamped = 0

    def _safe_log_r(i, ctx_tag):
        nonlocal n_clamped
        r_val = M.get_r(i, i)
        if r_val > 0:
            return 0.5 * math.log(r_val)
        n_clamped += 1
        _log_clamp(f"{clamp_ctx} {ctx_tag}".strip(), i, r_val)
        return 0.5 * math.log(1e-300)

    gs_log_active = [_safe_log_r(i, "active") for i in range(start, dim)]
    if n_clamped > 0:
        # Keep the legacy warning print — it's visible in the progress log
        # and gives a fast signal that a clamp fired. Raw values are
        # preserved in results/clamp_events.jsonl for post-mortem.
        print(f"  WARNING: {n_clamped} get_r values <= 0 "
              f"(logged to results/clamp_events.jsonl)")
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


# -- Run logic (single-threaded, no timeout) ----------------------------------

def run_single(n, beta, seed, store_per_tour=False):
    """Run one (n, β, seed) BKZ + SD-BKZ comparison at q=3329.

    Args:
        n, beta, seed: lattice parameters
        store_per_tour: when True, also stores the full per-tour Rankin
            profile, Gram-Schmidt log-norms, and RHF for each tour of
            each variant. Roughly 10x larger output JSON, ~0.1% extra
            compute. Off by default for backward compatibility with the
            existing dataset; the n=70/n=80 intermediate verification
            wrapper opts in so future investigations don't require
            re-running BKZ from scratch.
    """
    FPLLL.set_precision(PRECISION)
    FPLLL.set_random_seed(seed)

    m = n * 2
    dim = m + n + 1
    L, _, _ = build_lwe_kannan(n, m, Q, seed=seed)
    ln_p = ln_fixed_point(n + 1, beta)

    result = {
        "n": n, "beta": beta, "seed": seed, "q": Q, "max_tours": MAX_TOURS,
        "precision": PRECISION, "dim": dim, "m": m, "status": "completed",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "store_per_tour": store_per_tour,
    }

    # Initial quality
    B_init = IntegerMatrix.from_matrix(L)
    LLL.reduction(B_init)
    M_init = GSO.Mat(B_init)
    M_init.update_gso()
    init = _metrics_from_gso(M_init, dim, m, ln_p, full=True)
    result["initial_dln"] = init["dln"]
    result["initial_rhf"] = init["rhf"]
    result["initial_rankin_profile"] = [float(x) for x in init["rankin"]]
    result["initial_gs_lognorms"] = [float(x) for x in init["gs_lognorms"]]

    # Run both variants (reuse LLL-reduced basis — LLL is deterministic)
    for variant in ("bkz", "sdbkz"):
        B = IntegerMatrix(B_init)  # copy already-LLL-reduced basis

        flags = BKZ.MAX_LOOPS | BKZ.AUTO_ABORT
        if variant == "sdbkz":
            flags |= BKZ.SD_VARIANT

        dln_per_tour = []
        deltas = []
        # Per-tour storage (only populated if store_per_tour=True)
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

        for t in range(1, MAX_TOURS + 1):
            param = BKZ.Param(beta, max_loops=1, flags=flags)
            BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)

            M = GSO.Mat(B)
            M.update_gso()
            # Always compute the lean per-tour metrics (dln + rankin) so
            # the stagnation delta check can run. If store_per_tour is
            # enabled, also pull the full state (gs_lognorms + rhf) so
            # the per-tour evolution is captured for later analysis
            # without needing to re-run BKZ.
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

            # Stagnation threshold: matches sweep_parallel.py (1e-6)
            # Paper should mention this value and ideally sensitivity-check at 1e-5/1e-7
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
        # Floor metric: only meaningful if we hit max_tours (not early stagnation)
        if termination == "max_tours_reached" and len(deltas) >= 5:
            result[f"{variant}_floor"] = float(np.mean(deltas[-5:]))
        else:
            result[f"{variant}_floor"] = float(deltas[-1]) if deltas else None
        result[f"{variant}_time"] = elapsed

    # Derived metrics
    result["advantage"] = result["bkz_final_dln"] - result["sdbkz_final_dln"]
    result["rhf_advantage"] = result["rhf_bkz"] - result["rhf_sdbkz"]

    # Crossover tour
    bkz_final = result["bkz_final_dln"]
    crossover = None
    for t_idx, sd_dln in enumerate(result["sdbkz_dln_per_tour"], 1):
        if sd_dln < bkz_final:
            crossover = t_idx
            break
    result["crossover_tour"] = crossover

    return result


# -- Main ---------------------------------------------------------------------

def main():
    print("=" * 70)
    print(f"q={Q} VERIFICATION RUN (matches sweep_parallel.py exactly)")
    print(f"n={N}, beta={BETA}, seeds=1-{len(SEEDS)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 70)

    PIPELINE.info(
        "q3329 verify start",
        cat="sweep",
        n=N, beta=BETA, q=Q, n_seeds=len(SEEDS),
        output_dir=OUTPUT_DIR,
    )
    t_start = time.time()

    advantages = []
    completed = 0

    for seed in SEEDS:
        outpath = os.path.join(OUTPUT_DIR, f"n{N}_beta{BETA}_q{Q}_seed{seed}.json")

        if os.path.exists(outpath):
            print(f"Seed {seed}: already done, skipping.")
            with open(outpath) as f:
                d = json.load(f)
            advantages.append(d["advantage"])
            completed += 1
            continue

        try:
            print(f"Seed {seed}: running...", end=" ", flush=True)
            result = run_single(N, BETA, seed)

            with open(outpath, "w") as f:
                json.dump(result, f, indent=2)

            adv = result["advantage"]
            advantages.append(adv)
            completed += 1
            winner = "SDBKZ" if adv > 0 else "BKZ"
            print(f"adv={adv:.4f} ({winner})  "
                  f"BKZ={result['bkz_time']:.0f}s  SDBKZ={result['sdbkz_time']:.0f}s  "
                  f"[{completed}/{len(SEEDS)}]")

        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    if advantages:
        adv = np.array(advantages)
        print()
        print("=" * 70)
        print(f"q={Q} VERIFICATION SUMMARY ({len(advantages)} seeds)")
        print("=" * 70)
        print(f"  Mean advantage:  {np.mean(adv):.4f} nats")
        print(f"  Std:             {np.std(adv, ddof=1):.4f}")
        print(f"  Win rate:        {np.mean(adv > 0)*100:.1f}%")
        print(f"  Min / Max:       {np.min(adv):.4f} / {np.max(adv):.4f}")
        print()
        # Show q=97 baseline for the same (n, beta) if available
        try:
            import glob as _glob
            _base_files = _glob.glob(os.path.join(BASE, "results", "raw", f"n{N}_beta{BETA}_seed*.json"))
            if not _base_files:
                # Post-2026-04-08 restructure: cloud results live at
                # results/cloud/, not the legacy top-level results_cloud/
                _base_files = _glob.glob(os.path.join(BASE, "results", "cloud", f"n{N}_beta{BETA}_seed*.json"))
            if _base_files:
                _base_advs = [json.load(open(f))["advantage"] for f in _base_files]
                _ba = np.array(_base_advs)
                print(f"  q=97 baseline (n={N}, beta={BETA}, {len(_ba)} seeds):  "
                      f"mean={np.mean(_ba):.3f}, win={np.mean(_ba > 0)*100:.0f}%")
            else:
                print(f"  q=97 baseline (n={N}, beta={BETA}):  no local data")
        except Exception:
            print(f"  q=97 baseline:  could not load")
        print(f"  q={Q} result:                   mean={np.mean(adv):.3f}, "
              f"win={np.mean(adv > 0)*100:.0f}%")

        summary = {
            "q": Q, "n": N, "beta": BETA,
            "seeds_completed": len(advantages),
            "mean_advantage": float(np.mean(adv)),
            "std_advantage": float(np.std(adv, ddof=1)),
            "win_rate": float(np.mean(adv > 0)),
            "advantages": [float(a) for a in advantages],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        sumpath = os.path.join(OUTPUT_DIR, "summary_q3329.json")
        with open(sumpath, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n  Saved: {sumpath}")

    PIPELINE.info(
        "q3329 verify complete",
        cat="sweep",
        n=N, beta=BETA, q=Q,
        completed=completed,
        elapsed_s=int(time.time() - t_start),
    )


if __name__ == "__main__":
    main()
