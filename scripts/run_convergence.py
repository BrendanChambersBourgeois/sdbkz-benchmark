#!/usr/bin/env python3
"""
Generic convergence-test runner with configurable (n, β, max_tours, seeds, workers).

Replaces the per-configuration launchers
`run_convergence_n{90,140}_mt1000.py` (which remain in place as
thin historical wrappers) with a single argparse-driven entry point.
The legacy scripts predate this generic runner and are kept so the
`v1.5.0` commits that cite them by name still resolve.

Underlying logic lives in `run_convergence_test` (q=97, 250-bit
MPFR, restart-safe, pipeline-logged). This script monkey-patches its
module-level knobs and calls its `main()`.

Usage examples:
    # n=150 β=30 1000-tour, 20 seeds, 22 workers (defaults match paper §5.3)
    nohup python3 scripts/run_convergence.py --n 150 --max-tours 1000 \\
        > logs/convergence_n150_mt1000_stdout.log 2>&1 &

    # custom block size + seed count
    nohup python3 scripts/run_convergence.py --n 120 --max-tours 500 \\
        --beta 40 --seeds 40 \\
        > logs/convergence_n120_beta40_mt500_stdout.log 2>&1 &

Output path (inherited from run_convergence_test._seed_paths):
    results/seeds/convergence/q97/n{n:03d}_beta{beta:02d}_mt{max_tours}/

Canonical paper-cited paths use mt500 / mt1000 suffix; the generic
runner preserves that via the max_tours override.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger, new_run_id, get_run_id

PIPELINE = get_logger("run_convergence")


def main():
    ap = argparse.ArgumentParser(
        description="Generic convergence-test runner (configurable n / β / max_tours / seeds / workers)",
    )
    ap.add_argument("--n", type=int, required=True,
                    help="lattice dimension (required)")
    ap.add_argument("--max-tours", type=int, required=True, dest="max_tours",
                    help="tour budget (required; 500 and 1000 are paper-cited)")
    ap.add_argument("--beta", type=int, default=30,
                    help="block size (default: 30)")
    ap.add_argument("--seeds", type=int, default=None,
                    help="number of seeds (default: inherit from run_convergence_test)")
    ap.add_argument("--workers", type=int, default=None,
                    help="pool size (default: inherit from run_convergence_test)")
    args = ap.parse_args()

    if not get_run_id():
        new_run_id()

    PIPELINE.info(
        "dispatch",
        cat="sweep",
        n=args.n, beta=args.beta, max_tours=args.max_tours,
        seeds=args.seeds, workers=args.workers,
    )

    import run_convergence_test

    run_convergence_test.N = args.n
    run_convergence_test.BETA = args.beta
    run_convergence_test.MAX_TOURS = args.max_tours
    if args.seeds is not None:
        run_convergence_test.NUM_SEEDS = args.seeds
    if args.workers is not None:
        run_convergence_test.NUM_WORKERS = args.workers

    run_convergence_test.main()


if __name__ == "__main__":
    main()
