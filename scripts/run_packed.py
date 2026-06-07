#!/usr/bin/env python3
"""Pool seed-tasks across MANY cells into one worker pool for max core use.

Per-cell serial runs (one run_campaign per cell) waste cores: each cell's last
wave is < workers, and small filler cells (delta +4) use only a few cores while
the rest idle. This flattens every (cell, missing-seed) into ONE mp.Pool, sorted
longest-first (precision, then n, then q) so the slow seeds start early and the
tiny ones fill gaps -- cores stay saturated until a single final partial wave.

Byte-identical to per-cell: each seed is independent + deterministic by its
seed value + params. Reuses run_campaign._ntru_seed_worker (so atomic write +
per-seed try/except isolation + the get_r clamp logger all apply).

Cells are NTRU β=20 (generator=ntru, seed_tag=ntru, mt=50) given as
n:q:precision:target tokens. Resume-safe (skips existing).

Usage (inside sdbkz-benchmark:ci):
  python3 scripts/run_packed.py --workers 22 --beta 20 --mt 50 \
      113:701:500:100 89:223:250:100 67:167:250:100 ...
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seed_paths import seed_path_for  # noqa: E402
from log import get_logger, new_run_id  # noqa: E402
from run_campaign import _ntru_seed_worker  # noqa: E402

PIPELINE = get_logger("run_packed")


def build_tasks(cells, beta, mt, generator, seed_tag, backend):
    """Flatten (n,q,prec,target) cells -> one task list, skipping existing."""
    tasks = []
    for (n, q, prec, target) in cells:
        for seed in range(1, target + 1):
            out = seed_path_for(seed_tag, n=n, beta=beta, seed=seed, q=q,
                                precision=prec, max_tours=mt)
            if os.path.exists(out):
                continue
            tasks.append((n, beta, seed, q, prec, mt, generator, seed_tag,
                          backend))
    # longest-first: precision, then n, then q (slow seeds start early so none
    # is left running alone at the tail).
    tasks.sort(key=lambda t: (t[4], t[0], t[3]), reverse=True)
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-cell pooled NTRU seed runner.")
    ap.add_argument("--workers", type=int, default=22)
    ap.add_argument("--beta", type=int, default=20)
    ap.add_argument("--mt", type=int, default=50)
    ap.add_argument("--generator", default="ntru")
    ap.add_argument("--seed-tag", default="ntru")
    ap.add_argument("--backend", default="fplll")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("cells", nargs="+", help="n:q:precision:target tokens")
    args = ap.parse_args()

    cells = []
    for tok in args.cells:
        n, q, p, t = (int(x) for x in tok.split(":"))
        cells.append((n, q, p, t))
    tasks = build_tasks(cells, args.beta, args.mt, args.generator,
                        args.seed_tag, args.backend)
    new_run_id()
    PIPELINE.info("packed run", cat="sweep", cells=len(cells), tasks=len(tasks),
                  workers=args.workers, beta=args.beta, mt=args.mt)
    print(f"packed: {len(cells)} cells -> {len(tasks)} missing seeds, "
          f"{args.workers} workers, longest-first")
    if args.dry_run:
        for t in tasks[:5]:
            print(f"  [dry] n{t[0]} q{t[3]} p{t[4]} seed{t[2]}")
        print(f"  ... ({len(tasks)} total)")
        return 0
    if not tasks:
        print("nothing to do (all seeds exist)")
        return 0

    import multiprocessing as mp
    nproc = max(1, min(args.workers, (os.cpu_count() or 2), len(tasks)))
    done = written = 0
    total = len(tasks)
    with mp.Pool(nproc) as pool:
        for n, beta, seed, adv, status in pool.imap_unordered(
                _ntru_seed_worker, tasks):
            done += 1
            if status == "ok":
                written += 1
            if done % 10 == 0 or done == total:
                print(f"  [{done}/{total}] written={written} "
                      f"(last n{n} seed{seed}: {status})", flush=True)
    PIPELINE.info("packed run done", cat="sweep", done=done, written=written)
    print(f"DONE: {done} tasks, {written} written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
