#!/usr/bin/env python3
"""Estimate wall time for a planned convergence sweep.

CLI wrapper around :mod:`seed_timing`. Reads existing seed JSONs (or a
cached per-tour cost table at
``results/paper_claims/per_tour_cost_table.json``) and prints both a
naive and an anchored prediction with a recommendation between them.

Usage examples
--------------

    # Plan an n=130 β=40 1000-tour sweep on the canonical 22-worker pool
    python3 scripts/estimate_sweep_time.py --n 130 --beta 40 --max-tours 1000

    # Override pool shape
    python3 scripts/estimate_sweep_time.py --n 110 --beta 30 --max-tours 500 \\
        --seeds 40 --workers 22

    # Force a fresh-table compute (skip the cache, useful after recent
    # seed additions if the cache hasn't been refreshed yet)
    python3 scripts/estimate_sweep_time.py --n 90 --beta 30 --max-tours 1000 \\
        --no-cache

The estimator is advisory: it always exits 0 and never blocks anything.
A single ``estimate`` event is emitted to ``logs/pipeline.jsonl`` per
invocation under ``cat="estimator"`` for jq filtering.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import seed_timing  # noqa: E402
from log import get_logger  # noqa: E402

PIPELINE = get_logger("estimate_sweep_time")


def _format_hours(h):
    """Render hours as either '12.3 h' or '2.5 d' depending on magnitude."""
    if h is None:
        return "—"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} d ({h:.0f} h)"


def _print_report(est, *, stream=sys.stderr):
    """Human-readable summary of a SweepEstimate, written to stderr."""
    print(file=stream)
    print(f"Sweep estimate — n={est.n}, β={est.beta}, max_tours={est.max_tours}", file=stream)
    print(f"  pool: {est.num_seeds} seeds × {est.num_workers} workers", file=stream)
    print(f"  recommendation: {est.method_recommended}", file=stream)
    print(file=stream)
    print(f"  naive    wall: {_format_hours(est.predicted_wall_h_naive)}", file=stream)
    print(f"  anchored wall: {_format_hours(est.predicted_wall_h_anchored)}"
          f"  (p95 {_format_hours(est.predicted_wall_h_p95)},"
          f" MAD {_format_hours(est.mad_h)})", file=stream)
    print(file=stream)
    if est.anchor_used is not None:
        an_n, an_b, an_mt = est.anchor_used
        age = f"{est.anchor_age_days:.1f} d" if est.anchor_age_days is not None else "—"
        sha = est.last_numerical_commit_sha[:12] if est.last_numerical_commit_sha else "—"
        print(f"  anchor:    n={an_n}, β={an_b}, max_tours={an_mt}", file=stream)
        print(f"  anchor age: {age}  (numerical hotspots last touched: {sha})", file=stream)
        print(f"  anchor source: {len(est.anchor_source_paths)} seed file(s)", file=stream)
        print(file=stream)
    if est.notes:
        print("  notes:", file=stream)
        for note in est.notes:
            print(f"    • {note}", file=stream)
        print(file=stream)


def _estimate_to_log_ctx(est):
    """Flatten SweepEstimate into a log-event ctx dict (JSON-safe primitives only)."""
    return {
        "n": est.n,
        "beta": est.beta,
        "max_tours": est.max_tours,
        "num_seeds": est.num_seeds,
        "num_workers": est.num_workers,
        "predicted_wall_h_naive": est.predicted_wall_h_naive,
        "predicted_wall_h_anchored": est.predicted_wall_h_anchored,
        "predicted_wall_h_p95": est.predicted_wall_h_p95,
        "mad_h": est.mad_h,
        "anchor_used": list(est.anchor_used) if est.anchor_used else None,
        "anchor_age_days": est.anchor_age_days,
        "anchor_source_count": len(est.anchor_source_paths),
        "last_numerical_commit_sha": est.last_numerical_commit_sha,
        "method_recommended": est.method_recommended,
        "notes": list(est.notes),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Estimate wall time for a planned convergence sweep "
                    "(naive + anchored predictions, recommendation between them).",
    )
    ap.add_argument("--n", type=int, required=True,
                    help="lattice dimension (required)")
    ap.add_argument("--beta", type=int, required=True,
                    help="block size (required)")
    ap.add_argument("--max-tours", type=int, required=True, dest="max_tours",
                    help="tour budget for the planned sweep (required)")
    ap.add_argument("--seeds", type=int, default=20,
                    help="number of seeds in the planned sweep (default: 20)")
    ap.add_argument("--workers", type=int, default=22,
                    help="worker pool size (default: 22)")
    ap.add_argument("--cache-path", default=seed_timing.DEFAULT_CACHE_PATH, dest="cache_path",
                    help=f"per-tour-cost cache path "
                         f"(default: {seed_timing.DEFAULT_CACHE_PATH})")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore the cache and compute the table fresh from seed JSONs")
    ap.add_argument("--anchor-age-warn-days", type=float, default=7.0, dest="anchor_age_warn_days",
                    help="if youngest anchor seed is older than this, recommendation flips "
                         "to naive and a warning is emitted (default: 7)")
    args = ap.parse_args(argv)

    cache_path = None if args.no_cache else args.cache_path

    est = seed_timing.estimate_sweep_wall(
        n=args.n,
        beta=args.beta,
        max_tours=args.max_tours,
        num_seeds=args.seeds,
        num_workers=args.workers,
        cache_path=cache_path,
        anchor_age_warn_days=args.anchor_age_warn_days,
    )

    PIPELINE.info(
        "estimate",
        cat="estimator",
        **_estimate_to_log_ctx(est),
    )

    _print_report(est)

    return 0


if __name__ == "__main__":
    sys.exit(main())
