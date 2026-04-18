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
from _math_core import (
    ln_fixed_point, build_lwe_kannan, log_clamp, metrics_from_gso,
)
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
    log_clamp(ctx, position, raw_value,
              script_name="q3329_verify", log_path=CLAMP_LOG_FILE)


# -- Copied verbatim from sweep_parallel.py -----------------------------------

def _metrics_from_gso(M, dim, m, ln_profile, full=False, clamp_ctx=""):
    # warn_on_clamp=True preserves the q=3329 legacy behaviour of
    # printing a progress-log line on active-block clamp events.
    return metrics_from_gso(
        M, dim, m, ln_profile, full=full, clamp_ctx=clamp_ctx,
        log_clamp_fn=_log_clamp, warn_on_clamp=True,
    )


# -- Run logic (single-threaded, no timeout) ----------------------------------

from _bkz_core import run_single as _bkz_core_run_single


def run_single(n, beta, seed, store_per_tour=False):
    """Thin wrapper: feeds the canonical BKZ driver with q3329_verify
    conventions (Q=3329 default, MAX_TOURS captured at import time,
    warn_on_clamp=True for the q=3329 fast-signal, store_per_tour key
    always emitted at position 10 for legacy schema parity)."""
    return _bkz_core_run_single(
        n=n, beta=beta, seed=seed,
        q=Q, precision=PRECISION,
        max_tours=MAX_TOURS,
        log_clamp_fn=_log_clamp,
        warn_on_clamp=True,
        store_per_tour=store_per_tour,
        floor_mode="safe",
        always_emit_store_per_tour=True,
    )


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
            print("  q=97 baseline:  could not load")
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
