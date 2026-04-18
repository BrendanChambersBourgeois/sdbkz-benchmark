"""Shared runner skeleton for one-off BKZ/SD-BKZ sweep wrappers.

Factors out the ~80-line boilerplate that every `scripts/run_*.py`
wrapper duplicates today (argparse, Pool.imap_unordered, per-seed
status printing, PIPELINE.info start/complete). Wrappers pass their
config + a `run_single` callable; this module handles the rest.

This is the v1.2 consolidation pre-work: extracting the *wrapper*
layer (which is paper-numerical-neutral shell code) ahead of the
eventual `run_single` extraction (which needs a verify.sh
SHA-256 reproducibility gate to prove bit-identical output).

Not yet used by the existing in-tree wrappers — they keep their
inlined versions until the v1.2 consolidation lands and we can run
verify.sh against the conversion. New wrappers should import and
use `run_pool` directly.

Note on process start method: ``_worker`` receives the ``run_single``
callable inside the args tuple. Works under Linux's default ``fork``
start method (the forked child inherits the parent's module state and
the function reference). Would break under ``spawn`` (macOS, Windows)
because spawn re-pickles args and bare functions aren't always
pickleable. This repo runs Linux-only end-to-end so this is fine;
ports to other platforms would need to pass a module + function name
pair and re-import inside the worker.

Example:

    from _runner_core import run_pool
    from log import get_logger
    import sweep_parallel  # or q3329_verify, with argv mocking

    run_pool(
        label="fplll54 sensitivity",
        run_single=sweep_parallel.run_single,
        n=100, beta=30, q=97, precision=250,
        seeds=list(range(1, 6)),
        workers=5,
        output_dir="results/fplll54_sensitivity",
        out_name_pattern="n{n}_beta{beta}_q{q}_seed{seed}.json",
        logger=get_logger("run_fplll54"),
        extra_banner={"fplll_backend": "/usr/local/lib/libfplll.so.8"},
    )
"""
from __future__ import annotations

import os
import json
import time
import datetime
import traceback
from multiprocessing import Pool
from typing import Callable, Iterable


def _worker(args):
    run_single, n, beta, seed, out_path, store_per_tour = args
    t0 = time.time()
    try:
        result = run_single(n, beta, seed, store_per_tour=store_per_tour)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        return {
            "seed": seed,
            "status": "ok",
            "advantage": result["advantage"],
            "bkz_time": result.get("bkz_time"),
            "sdbkz_time": result.get("sdbkz_time"),
            "wall": time.time() - t0,
        }
    except Exception as e:
        return {
            "seed": seed,
            "status": "fail",
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(),
            "wall": time.time() - t0,
        }


def run_pool(
    *,
    label: str,
    run_single: Callable,
    n: int,
    beta: int,
    seeds: Iterable[int],
    workers: int,
    output_dir: str,
    out_name_pattern: str,
    q: int = 97,
    precision: int = 250,
    store_per_tour: bool = False,
    alt_done_dir: str | None = None,
    extra_banner: dict | None = None,
    logger=None,
) -> None:
    """Run ``run_single`` over ``seeds`` in parallel workers.

    Parameters:
        label: Human-readable name for pipeline log events and banner.
        run_single: Callable ``run_single(n, beta, seed, store_per_tour=...)``
            returning a dict with an ``"advantage"`` key.
        n, beta, q, precision: Numerical config (shown in banner; q and
            precision are informational — the actual numerical behavior
            is governed by the imported module's globals).
        seeds: Iterable of integer seeds to run.
        workers: Pool size.
        output_dir: Directory where per-seed JSONs land.
        out_name_pattern: Format string with ``{n} {beta} {q} {seed}``
            placeholders (e.g. ``"n{n}_beta{beta}_q{q}_seed{seed}.json"``).
        store_per_tour: Passed through to ``run_single``. True = fat seeds.
        alt_done_dir: Optional second directory checked for existing
            per-seed files, to avoid re-running seeds already done
            elsewhere (e.g. ``results/cloud/`` for q=3329 100-seed).
        extra_banner: Extra key-value pairs printed in the startup banner
            (e.g. fplll backend path, precision level).
        logger: Optional ``get_logger()`` instance for pipeline events.
    """
    os.makedirs(output_dir, exist_ok=True)
    seeds = list(seeds)

    def _path(d, seed):
        return os.path.join(
            d, out_name_pattern.format(n=n, beta=beta, q=q, seed=seed)
        )

    def _already_done(seed):
        if os.path.exists(_path(output_dir, seed)):
            return True
        if alt_done_dir and os.path.exists(_path(alt_done_dir, seed)):
            return True
        return False

    todo = [s for s in seeds if not _already_done(s)]
    done_count = len(seeds) - len(todo)

    print("=" * 70)
    print(f"{label}  —  n={n} β={beta} q={q} {precision}-bit MPFR")
    print(f"  Plan:           {len(seeds)} seeds")
    print(f"  Already done:   {done_count}")
    print(f"  To run:         {len(todo)}")
    print(f"  Workers:        {workers}")
    print(f"  Output dir:     {output_dir}")
    if alt_done_dir:
        print(f"  Alt done dir:   {alt_done_dir}")
    if extra_banner:
        for k, v in extra_banner.items():
            print(f"  {k + ':':<16}{v}")
    print(f"  Started:        {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70, flush=True)

    if not todo:
        print("Nothing to do.")
        return

    if logger is not None:
        logger.info(
            f"{label} start",
            cat="sweep",
            n=n, beta=beta, q=q, precision=precision,
            to_run=len(todo), already_done=done_count, workers=workers,
        )

    t_start = time.time()
    completed = 0
    args = [(run_single, n, beta, s, _path(output_dir, s), store_per_tour)
            for s in todo]

    with Pool(processes=workers, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(_worker, args):
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed > 0 else 0.0
            eta_sec = (len(todo) - completed) / rate if rate > 0 else 0
            eta = datetime.timedelta(seconds=int(eta_sec))

            if r["status"] == "ok":
                bkz = r.get("bkz_time") or 0
                sdbkz = r.get("sdbkz_time") or 0
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"adv={r['advantage']:+.4f}  "
                      f"BKZ={bkz/3600:.2f}h  SDBKZ={sdbkz/3600:.2f}h  "
                      f"wall={r['wall']/3600:.2f}h  ETA={eta}",
                      flush=True)
            else:
                print(f"  [{completed:>3}/{len(todo)}] seed {r['seed']:>3}: "
                      f"FAILED — {r['error']}", flush=True)
                print(r.get("trace", ""), flush=True)

    elapsed = time.time() - t_start
    print(f"\nDone. {completed} seeds in {elapsed/3600:.2f} h.")

    if logger is not None:
        logger.info(
            f"{label} complete",
            cat="sweep",
            n=n, beta=beta, q=q, precision=precision,
            completed=completed, elapsed_s=int(elapsed),
        )
