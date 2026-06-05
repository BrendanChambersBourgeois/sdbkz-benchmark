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


def _campaign_seed_glob(name: str, beta: int) -> tuple[str, ...]:
    """Glob patterns for a campaign's OWN completed seed cells (the #1
    self-anchor). Scopes to the campaign's tree (= engine+generator regime,
    #4) and its (β, mt), across whatever q/precision/n cells have run.

    Returns several layout candidates so it works for both the q/p_mt trees
    (ntru, ntru_g6k, q3329, …) and the q97 trees (main, convergence, …); the
    non-matching patterns simply glob to nothing.
    """
    from _config import load_campaign
    c = load_campaign(name)
    tree = c.seed_tag or ("ntru" if c.generator == "ntru" else "main")
    b = beta if beta in c.tours_by_beta else c.beta_grid[0]
    mt = c.tours_by_beta.get(b) or c.tours_by_beta[c.beta_grid[0]]
    bt = f"n*_beta{b:02d}"
    return (
        f"results/seeds/{tree}/q*/p*_mt{mt}/{bt}/seed*.json",  # ntru/q3329/g6k
        f"results/seeds/{tree}/q97/{bt}/seed*.json",           # main/tours3x
        f"results/seeds/{tree}/q97/{bt}_mt{mt}/seed*.json",    # convergence
    )


def _format_hours(h):
    """Render hours as either '12.3 h' or '2.5 d' depending on magnitude."""
    if h is None:
        return "—"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} d ({h:.0f} h)"


def _print_report(est, *, stream=sys.stderr, scoped=0):
    """Human-readable summary of a SweepEstimate, written to stderr.

    ``scoped`` is the number of the run's own cell-seeds the anchor was
    scoped to (--from-campaign / --seed-glob); >0 means the naive figure is
    built from fresh, same-regime data and IS the estimate, even if the
    banded "anchored" method (which needs ≥500-tour data) is unavailable.
    """
    print(file=stream)
    print(f"Sweep estimate — n={est.n}, β={est.beta}, max_tours={est.max_tours}", file=stream)
    print(f"  pool: {est.num_seeds} seeds × {est.num_workers} workers", file=stream)
    print(f"  recommendation: {est.method_recommended}", file=stream)
    print(file=stream)
    # #1/#4: say which corpus the figure rests on. Scoped to the run's own
    # cells -> the naive figure is fresh + same-regime (accurate). Unscoped
    # naive -> interpolated from the distant/wrong-regime global corpus, so
    # flag it as a rough estimate rather than hand it back silently.
    if scoped:
        print(f"  >>> SELF-ANCHORED on {scoped} of this run's own cell-seeds "
              f"(fresh, same regime) — "
              f"{_format_hours(est.predicted_wall_h_naive)} is the estimate.",
              file=stream)
        print("      (The banded p95 method needs ≥500-tour data; the "
              "naive-from-own-cells figure is the accurate one here.)", file=stream)
        print(file=stream)
    elif est.method_recommended == "naive":
        print(f"  >>> NO VALID ANCHOR — {_format_hours(est.predicted_wall_h_naive)} "
              f"is a ROUGH naive estimate (no fresh same-regime data).", file=stream)
        print("      For a new experiment type, anchor on its own cells once one "
              "has run:\n        estimate_sweep_time … --from-campaign <name>",
              file=stream)
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
    # #1 self-anchor: scope the anchor to a RUNNING experiment's own completed
    # cells instead of the global (LWE q=97) corpus. The run's own seeds are
    # by construction fresh AND in the exact (engine, generator, β, mt) regime,
    # so after one cell the estimate for the rest is near-exact. This is the
    # fix for "naive on every new experiment type": once a cell has run,
    # estimate from it. --from-campaign derives the glob from sweep.toml;
    # --seed-glob takes an explicit pattern (non-campaign trees / power user).
    ap.add_argument("--from-campaign", default=None, dest="from_campaign",
                    help="anchor on this campaign's own completed cells — a "
                         "fresh, same-regime self-anchor (forces --no-cache)")
    ap.add_argument("--seed-glob", default=None, dest="seed_glob",
                    help="explicit seed-glob to anchor on (overrides the default corpus)")
    args = ap.parse_args(argv)

    cache_path = None if args.no_cache else args.cache_path

    # Resolve the anchor seed glob (#1/#4). When scoped to a run's own tree we
    # force a fresh table (no stale global cache).
    seed_glob_patterns = None
    if args.seed_glob:
        seed_glob_patterns = (args.seed_glob,)
        cache_path = None
    elif args.from_campaign:
        seed_glob_patterns = _campaign_seed_glob(args.from_campaign, args.beta)
        cache_path = None

    est = seed_timing.estimate_sweep_wall(
        n=args.n,
        beta=args.beta,
        max_tours=args.max_tours,
        num_seeds=args.seeds,
        num_workers=args.workers,
        cache_path=cache_path,
        anchor_age_warn_days=args.anchor_age_warn_days,
        seed_glob_patterns=seed_glob_patterns,
    )

    PIPELINE.info(
        "estimate",
        cat="estimator",
        **_estimate_to_log_ctx(est),
    )

    scoped_n = (len(seed_timing._expand_globs(seed_glob_patterns))
                if seed_glob_patterns else 0)
    _print_report(est, scoped=scoped_n)

    return 0


if __name__ == "__main__":
    sys.exit(main())
