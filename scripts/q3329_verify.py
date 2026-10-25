#!/usr/bin/env python3
"""q=3329 verification runner — q-aware sweep workhorse.

Generic over (q, precision, max_tours): handles the q=3329 ML-KEM
characterisation (default), q=97 cliff500 precision robustness, and
q=97 main-grid cells when called by `scripts/run_campaign.py`.
Same `_bkz_core.run_single` chain as `sweep_parallel.py`; differs only
in defaults + per-seed output dir resolution.

Run direct (uses the script's defaults: q=3329, n=50, β=30, seeds=20):
    nice -n 19 python3 scripts/q3329_verify.py &

Override via argparse:
    python3 scripts/q3329_verify.py --n 100 --beta 30 \\
        --seeds 100 --precision 1000 --q 3329

Safe to run alongside the main sweep. Single-threaded by default;
the dispatcher path may run multiple instances in parallel.

Output path (resolved via `_seed_paths.seed_dir_for`):
    results/seeds/q3329/p{PRECISION}_mt{MAX_TOURS}/n{N:03d}_beta{BETA:02d}/seed{seed:04d}.json
    results/seeds/main/q97/n{N:03d}_beta{BETA:02d}/seed{seed:04d}.json   (with --q 97)
"""
import datetime
import json
import math
import os
import sys
import time

import fpylll
import numpy as np
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _math_core import (
    ln_fixed_point,
    log_clamp,
    metrics_from_gso,
)
from _seed_paths import seed_dir_for, seed_path_for
from generators import get_generator, get_metric_span
from log import get_logger

PIPELINE = get_logger("q3329_verify")

# -- Config -------------------------------------------------------------------
import argparse


def parse_args():
    parser = argparse.ArgumentParser(description="q=3329 verification run")
    parser.add_argument("--n", type=int, default=50, help="Secret dimension (default: 50)")
    parser.add_argument("--beta", type=int, default=30, help="Block size (default: 30)")
    parser.add_argument("--seeds", type=int, default=20, help="Number of seeds (default: 20)")
    parser.add_argument("--start", type=int, default=1,
                        help="first seed (default: 1); runs start..start+seeds-1")
    parser.add_argument("--precision", type=int, default=None,
                        help="MPFR precision in bits (default: 500 for q=3329)")
    # `--q` lets scripts/run_campaign.py route main / cliff500 (q=97)
    # campaigns through this runner without monkey-patching the module
    # global post-import. Default = 3329 preserves the historical CLI
    # behaviour for anyone calling q3329_verify.py standalone.
    parser.add_argument("--q", type=int, default=3329,
                        help="LWE modulus (default: 3329; pass 97 for main/cliff500)")
    # Lattice generator by name (see generators.GENERATORS). Default keeps
    # the historical LWE-Kannan construction; run_campaign passes the
    # campaign's generator field through here.
    parser.add_argument("--generator", type=str, default="lwe_kannan",
                        help="Lattice generator name (default: lwe_kannan)")
    # Override the per-beta tour count. Default None keeps the historical
    # TOURS_BY_BETA mapping (so existing main/cliff500/q3329 runs are
    # byte-unchanged); run_campaign passes the campaign's tours_by_beta value
    # so e.g. the estimator_probe can request mt=500.
    parser.add_argument("--max-tours", type=int, default=None,
                        help="override tours (default: TOURS_BY_BETA[beta])")
    # Output tree override (default "q3329", the canonical tree). The §8
    # rerun arms (run_campaign q3329_kahan / q3329_control) pass their own
    # seed_tag so a rebuilt engine can never write into the SHA-locked
    # canonical seeds. Must be a _seed_paths known tree.
    parser.add_argument("--seed-tag", type=str, default="q3329",
                        help="output tree under results/seeds/ (default: q3329)")
    # Worker pool width. 1 = the historical in-process seed loop; >1 forks a
    # pool (per-seed numerical output identical either way; only the wall-time
    # fields differ).
    parser.add_argument("--workers", type=int, default=1,
                        help="parallel seed workers (default: 1, in-process)")
    # Campaign knobs run_campaign forwards (both were dropped before
    # 2026-10-11). mpfr gates the MEASUREMENT GSO only; the
    # reduction is mpfr either way. Defaults keep existing seeds byte-identical.
    parser.add_argument("--metric-float-type", choices=("double", "mpfr"),
                        default="double",
                        help="measurement GSO float type (default: double)")
    parser.add_argument("--store-per-tour", action="store_true",
                        help="store per-tour rankin / gs_lognorms / rhf")
    parser.add_argument("--store-bases", action="store_true",
                        help="save every tour's integer basis per seed to "
                             "$BKZ_BASES_DIR (default ~/lattice-bases), outside git")
    return parser.parse_args()

_args = parse_args()

Q = _args.q          # ML-KEM modulus (main sweep uses 97; default 3329)
N = _args.n
BETA = _args.beta
# Resolve the generator name -> uniform (n, q, seed) -> L callable once,
# plus its metric active-block span (n, dim) -> (start, end).
GENERATOR = get_generator(_args.generator)
METRIC_SPAN_FN = get_metric_span(_args.generator)
TOURS_BY_BETA = {20: 50, 30: 70, 40: 100}
MAX_TOURS = _args.max_tours if _args.max_tours else TOURS_BY_BETA.get(BETA, 70)
PRECISION = _args.precision if _args.precision else 500
SEEDS = list(range(_args.start, _args.start + _args.seeds))
TAG = _args.seed_tag
WORKERS = max(1, int(_args.workers))
METRIC_FLOAT_TYPE = _args.metric_float_type
STORE_PER_TOUR = _args.store_per_tour
STORE_BASES = _args.store_bases
# Per-seed .npz of every tour's basis, mirroring the seed tree.
# Outside git (GBs per campaign) and regenerable by replay; never the seed JSON.
BASES_ROOT = (os.environ.get("BKZ_BASES_DIR")
              or os.path.expanduser("~/lattice-bases"))
# Trees this runner writes are double-measured, except *_mpfr trees; mpfr
# seeds go only to a tree named *_mpfr, never mixed into a double cell.
if METRIC_FLOAT_TYPE != "double" and not TAG.endswith("_mpfr"):
    PIPELINE.error("mpfr measurement refused for a double tree", cat="sweep",
                   seed_tag=TAG, metric_float_type=METRIC_FLOAT_TYPE)
    sys.exit(f"--metric-float-type {METRIC_FLOAT_TYPE} needs a *_mpfr "
             f"--seed-tag, got {TAG!r}")

# BASE is the repo root. Two dirname() calls because this script lives
# at scripts/q3329_verify.py — the first goes to scripts/, the second
# to the repo root.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# v1.3: q3329 seeds land at results/seeds/q3329/p{precision}_mt{max_tours}/n{n}_beta{beta}/.
# OUTPUT_DIR kept for legacy callers reading q3329 summary JSONs; the
# per-seed JSONs now land under the seed_path_for() tree.
OUTPUT_DIR = seed_dir_for(
    TAG, n=N, beta=BETA,
    precision=PRECISION, max_tours=MAX_TOURS, base=BASE,
)
os.makedirs(OUTPUT_DIR, exist_ok=True)
# Summary lands under the canonical campaign tree (post-v2.0.0 the
# legacy results/q3329/ dir does not exist; this script's own
# campaign root is the correct write target).
SUMMARY_DIR = os.path.join(BASE, "results", "seeds", TAG, "summary")
os.makedirs(SUMMARY_DIR, exist_ok=True)
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
    L = GENERATOR(n, Q, seed)
    m_start, m_end = METRIC_SPAN_FN(n, len(L))
    bases = {"init": [], "bkz": [], "sdbkz": []}

    def _keep(leg, tour, B):
        A = np.zeros((B.nrows, B.ncols), dtype=np.int64)
        B.to_matrix(A)  # OverflowError, never a silent wrap
        bases[leg].append(A)

    result = _bkz_core_run_single(
        L=L,
        n=n, active_block_start=m_start, active_block_end=m_end,
        beta=beta, seed=seed,
        q=Q, precision=PRECISION,
        max_tours=MAX_TOURS,
        log_clamp_fn=_log_clamp,
        warn_on_clamp=True,
        store_per_tour=store_per_tour,
        floor_mode="safe",
        always_emit_store_per_tour=True,
        metric_float_type=METRIC_FLOAT_TYPE,
        basis_cb=_keep if STORE_BASES else None,
    )
    if STORE_BASES:
        _write_bases(n, beta, seed, L, bases)
    # Self-describing seed: the key appears only off the default, so every
    # double-measured seed keeps its bytes (and SHA-256).
    if METRIC_FLOAT_TYPE != "double":
        result["metric_float_type"] = METRIC_FLOAT_TYPE
    return result


def _write_bases(n, beta, seed, L, bases):
    """One compressed .npz per seed: L (generator output, d x d); init (after
    LLL, 1 x d x d); bkz / sdbkz (tours x d x d, index t-1); meta (JSON
    string). Written atomically; a rerun of the seed replaces it."""
    seed_json = seed_path_for(TAG, n=n, beta=beta, seed=seed, q=Q,
                              precision=PRECISION, max_tours=MAX_TOURS, base=BASE)
    rel = os.path.relpath(seed_json, os.path.join(BASE, "results", "seeds"))
    out = os.path.join(BASES_ROOT, os.path.splitext(rel)[0] + ".npz")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    arrays = {"L": np.array(L, dtype=np.int64),
              **{leg: np.stack(v) for leg, v in bases.items()}}
    if max(int(np.abs(a).max()) for a in arrays.values()) < 2**31:
        arrays = {k: a.astype(np.int32) for k, a in arrays.items()}
    meta = {"n": n, "beta": beta, "seed": seed, "q": Q, "precision": PRECISION,
            "max_tours": MAX_TOURS, "seed_tag": TAG, "generator": _args.generator,
            "metric_float_type": METRIC_FLOAT_TYPE,
            "bkz_delta": BKZ.Param(beta).delta, "lll_delta": LLL.DEFAULT_DELTA,
            "lll_eta": LLL.DEFAULT_ETA, "fpylll": fpylll.__version__}
    tmp = out + ".tmp.npz"
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta)), **arrays)
    os.replace(tmp, out)
    PIPELINE.info("bases saved", cat="seed", n=n, beta=beta, seed=seed, q=Q,
                  seed_tag=TAG, path=out, bytes=os.path.getsize(out),
                  tours_bkz=len(bases["bkz"]), tours_sdbkz=len(bases["sdbkz"]))


def _pool_seed(seed):
    """Fork-pool worker: (seed, result, None) or (seed, None, error text).
    The exception is reported, never allowed to take the pool down."""
    try:
        return seed, run_single(N, BETA, seed, STORE_PER_TOUR), None
    except Exception as e:  # noqa: BLE001
        import traceback
        return seed, None, f"{e!r}\n{traceback.format_exc()[-1500:]}"


# -- Main ---------------------------------------------------------------------

def main():
    print("=" * 70)
    print(f"q={Q} VERIFICATION RUN (matches sweep_parallel.py exactly)")
    print(f"n={N}, beta={BETA}, seeds={SEEDS[0]}-{SEEDS[-1]}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 70)

    PIPELINE.info(
        "q3329 verify start",
        cat="sweep",
        n=N, beta=BETA, q=Q, n_seeds=len(SEEDS), first_seed=SEEDS[0],
        output_dir=OUTPUT_DIR, seed_tag=TAG,
        metric_float_type=METRIC_FLOAT_TYPE, store_per_tour=STORE_PER_TOUR,
        store_bases=STORE_BASES, bases_root=BASES_ROOT if STORE_BASES else None,
        fpylll=f"{fpylll.__version__} {os.path.dirname(fpylll.__file__)}",
    )
    t_start = time.time()

    advantages = []
    completed = 0
    todo = []          # (seed, outpath) not yet on disk, in seed order

    for seed in SEEDS:
        outpath = seed_path_for(
            TAG, n=N, beta=BETA, seed=seed,
            q=Q, precision=PRECISION, max_tours=MAX_TOURS, base=BASE,
        )

        if os.path.exists(outpath):
            print(f"Seed {seed}: already done, skipping.")
            with open(outpath) as f:
                d = json.load(f)
            advantages.append(d["advantage"])
            completed += 1
            continue
        todo.append((seed, outpath))

    def _record(seed, outpath, result, prefix=""):
        nonlocal completed
        with open(outpath, "w") as f:
            json.dump(result, f, indent=2)
        adv = result["advantage"]
        advantages.append(adv)
        completed += 1
        winner = "SDBKZ" if adv > 0 else "BKZ"
        print(f"{prefix}adv={adv:.4f} ({winner})  "
              f"BKZ={result['bkz_time']:.0f}s  SDBKZ={result['sdbkz_time']:.0f}s  "
              f"[{completed}/{len(SEEDS)}]", flush=True)
        PIPELINE.info("seed done", cat="seed", n=N, beta=BETA, seed=seed, q=Q,
                      precision=PRECISION, seed_tag=TAG, advantage=adv)

    def _failed(seed, err, prefix=""):
        print(f"{prefix}FAILED: {err}", flush=True)
        PIPELINE.error("seed failed", cat="seed", n=N, beta=BETA, seed=seed, q=Q,
                       precision=PRECISION, seed_tag=TAG, error=str(err)[:300])

    if WORKERS <= 1:
        # Historical in-process loop (the canonical q3329 / main path).
        for seed, outpath in todo:
            try:
                print(f"Seed {seed}: running...", end=" ", flush=True)
                _record(seed, outpath, run_single(N, BETA, seed, STORE_PER_TOUR))
            except Exception as e:
                _failed(seed, e)
                import traceback
                traceback.print_exc()
    elif todo:
        # Fork pool: each worker computes one seed with its own fpylll state
        # (precision is set inside _bkz_core.run_single); the parent writes
        # the JSON, so per-seed numerical output matches the loop above (only
        # the wall-time fields differ; verified 2026-09-02 on a scratch cell).
        # imap keeps seed order, so `advantages` is ordered as before.
        import multiprocessing as mp
        paths = dict(todo)
        print(f"Running {len(todo)} seed(s) across {WORKERS} workers ...",
              flush=True)
        with mp.get_context("fork").Pool(min(WORKERS, len(todo))) as pool:
            for seed, result, err in pool.imap(_pool_seed, [s for s, _ in todo]):
                if err is None:
                    _record(seed, paths[seed], result, prefix=f"Seed {seed}: ")
                else:
                    _failed(seed, err, prefix=f"Seed {seed}: ")

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
        # Show q=97 baseline for the same (n, beta) if available.
        # v2.0.0: routed through the manifest instead of legacy globs.
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(BASE))
            from analysis._data import load_all_seeds as _las
            _baseline = _las(campaign="main", q=97).get((N, BETA), [])
            if _baseline:
                _base_advs = [s["advantage"] for s in _baseline]
                _ba = np.array(_base_advs)
                print(f"  q=97 baseline (n={N}, beta={BETA}, {len(_ba)} seeds):  "
                      f"mean={np.mean(_ba):.3f}, win={np.mean(_ba > 0)*100:.0f}%")
            else:
                print(f"  q=97 baseline (n={N}, beta={BETA}):  no manifest data")
        except Exception:
            print("  q=97 baseline:  could not load via manifest")
        print(f"  q={Q} result:                   mean={np.mean(adv):.3f}, "
              f"win={np.mean(adv > 0)*100:.0f}%")

        summary = {
            "q": Q, "n": N, "beta": BETA,
            "seeds_completed": len(advantages),
            "mean_advantage": float(np.mean(adv)),
            "std_advantage": float(np.std(adv, ddof=1)),
            "win_rate": float(np.mean(adv > 0)),
            "advantages": [float(a) for a in advantages],
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        if SEEDS[0] != 1:  # a partial window; full-cell summaries keep their shape
            summary["seed_range"] = [SEEDS[0], SEEDS[-1]]
        sumpath = os.path.join(SUMMARY_DIR, f"summary_q{Q}_n{N}_beta{BETA}.json")  # one file per cell
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
