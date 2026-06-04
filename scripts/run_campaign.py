#!/usr/bin/env python3
"""Single-entry-point campaign dispatcher driven by ``config/sweep.toml``.

Replaces the per-cell launcher scripts (`run_cliff_500bit.py`,
`run_n100_beta40.py`, `run_q3329_n90.py`, `run_q3329_n100_local.py`,
`run_overnight_q3329_intermediate_1000bit.py`) with one parametrised
driver. The fplll-sensitivity campaign still lives at
`scripts/run_fplll54_sensitivity.py` because its cross-image
baseline-comparison logic is not parametrically dispatchable; this
dispatcher prints the Docker build + invoke recipe for that
campaign and exits.

Usage examples (every campaign declared in `config/sweep.toml` is
dispatchable):

    # q=97 main sweep, n=100 β=40, seeds 1..50, 22 workers
    python3 scripts/run_campaign.py --campaign main \\
        --n 100 --beta 40 --start 1 --end 50 --workers 22

    # β=40 cliff precision-robustness re-run (n=130 hardcoded in TOML)
    python3 scripts/run_campaign.py --campaign cliff500 --workers 22

    # q=3329 ML-KEM n=100 β=30 at 1000-bit MPFR, 5 seeds
    python3 scripts/run_campaign.py --campaign q3329 \\
        --n 100 --beta 30 --seeds 5 --workers 5

    # n=150 β=40 convergence bracket (1000 tours, 20 seeds)
    python3 scripts/run_campaign.py --campaign convergence_beta40_mt1000 \\
        --n 150 --workers 22

    # Dry-run any campaign — print the resolved invocation, do not launch
    python3 scripts/run_campaign.py --campaign cliff500 --dry-run

Dispatch routing (campaign name → underlying runner):

    main, cliff500             → q3329_verify (q-aware, precision-aware)
    q3329                      → q3329_verify (q=3329, precision from TOML)
    convergence_*              → run_convergence_test (module globals)
    tours3x                    → run_3x_extended (GROUPS override)
    fplll_sensitivity          → out-of-scope here — needs Dockerfile.fplll54
                                 image build; prints instructions and exits.
    ntru_smoke                 → inline NTRU build + structural check + BKZ
                                 over the full-basis [0,2n) metric (R*);
                                 in-memory, writes no per-seed JSONs.
    ntru                       → same, persisted to results/seeds/ntru/
                                 (real NTRU seed generation).

The dispatcher does NOT re-implement the BKZ driver. It builds the
argv that the underlying runner expects, then either subprocess-execs
it (for q3329_verify-class campaigns) or imports + sets module globals
(for run_convergence_test / run_3x_extended which parse no argv).

Output paths land at the canonical `results/seeds/<campaign>/...`
tree via `_seed_paths.seed_path_for`; no per-campaign output-dir
overrides needed because the underlying runners already route through
that helper.

Bit-identity guarantee: argv construction here matches what each
deleted per-cell script passed by hand. verify.sh remains the
authority on numerical reproducibility — running it post-deploy on
a 1-seed sample confirms the dispatcher does not perturb output.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Any, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

from _config import Campaign, ConfigError, load_campaign  # noqa: E402
from log import get_logger, get_run_id, new_run_id  # noqa: E402

PIPELINE = get_logger("run_campaign")


def _select_runner(campaign_name: str) -> str:
    """Resolve a campaign name to the runner role that executes it.

    Roles:
      - `q3329_verify`  — q-aware, precision-aware, multiprocessing pool.
                          Handles main, q3329, cliff500.
      - `convergence`   — run_convergence_test module-global override.
                          Handles convergence_beta{30,40}_mt1000.
      - `tours3x`       — run_3x_extended GROUPS override. Handles tours3x.
      - `fplll_image`   — needs a separate Docker build (Dockerfile.fplll54);
                          this script cannot dispatch it directly.
      - `ntru_smoke`    — inline NTRU build + structural self-check + BKZ
                          over the full-basis [0,2n) metric; in-memory.
      - `ntru`          — same, but persists per-seed JSONs to
                          results/seeds/ntru/ (real seed generation).
    """
    if campaign_name in {"main", "cliff500"}:
        return "q3329_verify"
    if campaign_name == "q3329":
        return "q3329_verify"
    if campaign_name.startswith("convergence_"):
        return "convergence"
    if campaign_name == "tours3x":
        return "tours3x"
    if campaign_name == "fplll_sensitivity":
        return "fplll_image"
    if campaign_name == "ntru_smoke":
        return "ntru_smoke"
    # Any other ntru* campaign (ntru, ntru_qsweep, ntru_n127_patched, future
    # ntru_*) persists per-seed JSONs through the shared NTRU pool worker —
    # the output tree is the campaign's seed_tag, so a new variant needs only
    # a TOML block, not a router edit.
    if campaign_name == "ntru" or campaign_name.startswith("ntru_"):
        return "ntru"
    raise ConfigError(f"no dispatch route registered for campaign '{campaign_name}'")


def _resolve_pool(campaign: Campaign, n: int, beta: int,
                  start: int, end: int,
                  cli_seeds: Optional[int]) -> tuple[int, int]:
    """Pick (effective seed count, range bounds) given TOML defaults
    + CLI overrides. ``--start`` / ``--end`` win over ``--seeds`` when
    both are supplied; ``--seeds`` wins over the TOML ``num_seeds``."""
    if start is not None and end is not None:
        return (end - start + 1, end)
    seed_count = cli_seeds if cli_seeds is not None else campaign.num_seeds
    return (seed_count, seed_count)


def _dispatch_q3329_verify(
    campaign: Campaign, n: int, beta: int, *,
    start: int, end: int, seeds: int, workers: int, dry_run: bool,
) -> int:
    """Hand off to scripts/q3329_verify.py with a fully-resolved argv.

    `q3329_verify` is the canonical generic runner — it accepts every
    (q, precision, max_tours, num_seeds) tuple via argparse and writes
    per-seed JSONs through `_seed_paths.seed_path_for` against the
    `q3329` campaign tree. For q=97 main + cliff500 campaigns we pass
    the q=97 override; for q=3329 we pass the campaign's q.

    Effective seed range follows --start/--end if supplied; otherwise
    the runner generates seeds 1..N. q3329_verify only accepts a seeds
    count (not a range), so we synthesise the range via env var when
    --start is set and let the runner pick it up.
    """
    if beta not in campaign.tours_by_beta:
        raise ConfigError(
            f"campaign {campaign.name!r} has no tours_by_beta entry "
            f"for β={beta}; available: {sorted(campaign.tours_by_beta)}"
        )
    tours = campaign.tours_by_beta[beta]

    argv = [
        sys.executable, os.path.join(SCRIPT_DIR, "q3329_verify.py"),
        "--n", str(n),
        "--beta", str(beta),
        "--seeds", str(seeds),
        "--precision", str(campaign.precision),
        "--generator", campaign.generator,
    ]
    if campaign.q != 3329:
        # q3329_verify defaults to Q=3329; pass --q to override for
        # main + cliff500 campaigns.
        argv.extend(["--q", str(campaign.q)])
    env = dict(os.environ)
    if start != end:
        # Hint the runner about the explicit range so resume logic
        # only checks the requested window.
        env["BKZ_SEED_RANGE"] = f"{start}-{end}"
    env["BKZ_TOURS"] = str(tours)

    if dry_run:
        print("[dry-run]", " ".join(argv))
        return 0
    return subprocess.call(argv, env=env)


def _dispatch_convergence(
    campaign: Campaign, n: int, beta: int, *,
    seeds: int, workers: int, dry_run: bool,
) -> int:
    """Hand off to scripts/run_convergence.py which itself argparse-
    drives `run_convergence_test`.

    `run_convergence.py` is the existing argparse wrapper around the
    module-global pattern in run_convergence_test; we forward through
    it rather than re-implementing the same wrapping logic.
    """
    if beta not in campaign.tours_by_beta:
        raise ConfigError(
            f"campaign {campaign.name!r} has no tours_by_beta entry "
            f"for β={beta}; available: {sorted(campaign.tours_by_beta)}"
        )
    max_tours = campaign.tours_by_beta[beta]
    argv = [
        sys.executable, os.path.join(SCRIPT_DIR, "run_convergence.py"),
        "--n", str(n),
        "--beta", str(beta),
        "--max-tours", str(max_tours),
        "--seeds", str(seeds),
        "--workers", str(workers),
    ]
    if dry_run:
        print("[dry-run]", " ".join(argv))
        return 0
    return subprocess.call(argv)


def _dispatch_tours3x(
    campaign: Campaign, n: int, beta: int, *,
    seeds: int, workers: int, dry_run: bool,
) -> int:
    """Hand off to scripts/run_3x_extended.py via inline GROUPS override.

    run_3x_extended has its own argparse for workers + dry-run but
    expects a `GROUPS` module-level list with (n, beta, normal_tours,
    triple_tours) tuples. We override that list to the single cell
    requested.
    """
    if beta not in campaign.tours_by_beta:
        raise ConfigError(
            f"campaign {campaign.name!r} has no tours_by_beta entry "
            f"for β={beta}; available: {sorted(campaign.tours_by_beta)}"
        )
    triple_tours = campaign.tours_by_beta[beta]
    normal_tours = triple_tours // 3  # 3× convention: 210 vs 70
    if dry_run:
        print(f"[dry-run] run_3x_extended.GROUPS = [{{n={n}, beta={beta}, "
              f"normal_tours={normal_tours}, triple_tours={triple_tours}}}]; "
              f"run_3x_extended.main()  # workers={workers} seeds={seeds}")
        return 0
    import run_3x_extended
    run_3x_extended.GROUPS = [{
        "n": n, "beta": beta,
        "normal_tours": normal_tours, "triple_tours": triple_tours,
    }]
    run_3x_extended.main()
    return 0


def _dispatch_fplll_image(campaign: Campaign, *args: Any, **kwargs: Any) -> int:
    print(
        "fplll_sensitivity dispatch requires a separate Docker image "
        "(Dockerfile.fplll54 or Dockerfile.fplll_legacy) because it uses "
        "a source-built fplll version rather than the wheel-bundled one.\n"
        "Build:\n"
        "  docker build -f Dockerfile.fplll54 -t sdbkz-fplll54 .\n"
        "Run inside container:\n"
        "  docker run --rm -v $PWD:/repo -w /repo sdbkz-fplll54 \\\n"
        "      python3 scripts/run_fplll54_sensitivity.py --seeds 5\n"
    )
    return 2


# Canonical defensive-clamp side log (CLAUDE.md: log the raw get_r before
# the 1e-300 substitution; never mutate the per-seed JSON). Shared with the
# sweep/verify scripts. A module-level wrapper so it pickles for the pool.
_CLAMP_LOG_FILE = os.path.join(REPO_ROOT, "results", "clamp_events.jsonl")


def _ntru_log_clamp(ctx: str, position: int, raw_value: float) -> None:
    from _math_core import log_clamp
    log_clamp(ctx, position, raw_value,
              script_name="run_campaign", log_path=_CLAMP_LOG_FILE)


def _ntru_seed_worker(task: tuple) -> tuple:
    """Pool worker: build + structurally verify + BKZ one NTRU (n, β, seed),
    then write its per-seed JSON. Returns (n, β, seed, advantage|None,
    status). Module-level so it pickles for multiprocessing; each process
    gets its own fpylll global state (precision / RNG), as in sweep_parallel.

    The task tuple's 8th element is the output seed_tag (which results/seeds/
    tree to write under, e.g. "ntru" or "ntru_patched"); the per-tour get_r
    clamp logger is wired so a §8 cancellation is recorded, not silent.
    """
    import json

    import numpy as np
    from _bkz_core import run_single
    from _seed_paths import seed_path_for
    from generators import build_ntru, get_metric_span

    (n, beta, seed, q, precision, max_tours, generator, seed_tag,
     backend) = task
    out = seed_path_for(seed_tag, n=n, beta=beta, seed=seed, q=q,
                        precision=precision, max_tours=max_tours)
    if os.path.exists(out):
        return (n, beta, seed, None, "skip")
    L, f, g = build_ntru(n, q, seed=seed)
    if len(L) != 2 * n:
        return (n, beta, seed, None, "dim_err")
    H = np.array([[L[n + i][j] for j in range(n)] for i in range(n)]).T
    if not np.array_equal((H @ f) % q, g % q):
        return (n, beta, seed, None, "key_err")
    m_start, m_end = get_metric_span(generator)(n, len(L))
    r = run_single(
        L=L, n=n, active_block_start=m_start, active_block_end=m_end,
        beta=beta, seed=seed, q=q, precision=precision,
        max_tours=max_tours, log_clamp_fn=_ntru_log_clamp,
        backend=backend,
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(r, fh, indent=2)
    return (n, beta, seed, r["advantage"], "ok")


def _dispatch_ntru(
    campaign: Campaign, *, dry_run: bool, persist: bool, workers: int = 22,
) -> int:
    """NTRU runner: for each (n ∈ n_grid, β ∈ beta_grid, seed) build the
    NTRU basis, verify its structure (dim=2n, q·I_n, key consistency
    H·f ≡ g mod q), run the BKZ engine over the full-basis [0, 2n) metric
    (R*), and record the BKZ/SD-BKZ advantage.

    ``persist=False`` (ntru_smoke): serial, in-memory only — a fast
    structural+BKZ gate. ``persist=True`` (ntru): writes per-seed JSONs
    (same run_single schema as the LWE seeds) to results/seeds/ntru/q{q}/
    p{p}_mt{mt}/n{n}_beta{b}/seed{s}.json across a multiprocessing pool
    (resumable: existing seeds skipped).
    """
    import numpy as np
    from _bkz_core import run_single
    from _seed_paths import seed_path_for
    from generators import build_ntru, get_generator, get_metric_span

    get_generator(campaign.generator)  # validate the name resolves
    q = campaign.q

    if not persist:
        # Serial in-memory smoke — no writes, no pool.
        span_fn = get_metric_span(campaign.generator)
        done = 0
        for n in campaign.n_grid:
            for beta in campaign.beta_grid:
                max_tours = campaign.tours_by_beta[beta]
                for seed in range(1, campaign.num_seeds + 1):
                    if dry_run:
                        print(f"[dry-run] ntru_smoke n={n} q={q} seed={seed} "
                              f"β={beta} (in-memory)")
                        continue
                    L, f, g = build_ntru(n, q, seed=seed)
                    H = np.array([[L[n + i][j] for j in range(n)]
                                  for i in range(n)]).T
                    if len(L) != 2 * n or not np.array_equal((H @ f) % q,
                                                             g % q):
                        print(f"ERROR: n={n} seed={seed}: bad basis",
                              file=sys.stderr)
                        return 2
                    m_start, m_end = span_fn(n, len(L))
                    r = run_single(
                        L=L, n=n,
                        active_block_start=m_start, active_block_end=m_end,
                        beta=beta, seed=seed, q=q,
                        precision=campaign.precision, max_tours=max_tours,
                        log_clamp_fn=None,
                    )
                    print(f"  n={n:3d} β={beta} seed={seed}: dim={2 * n} "
                          f"verified, advantage={r['advantage']:+.6f}")
                    done += 1
        if not dry_run:
            print(f"NTRU smoke OK: {done} bases verified (dim=2n, q·I_n, "
                  f"H·f≡g mod {q}) + BKZ over [0,2n).")
        return 0

    # persist=True: parallel seed generation. seed_tag routes the output tree
    # (default "ntru"; a campaign may set "ntru_patched" etc. for a separate
    # tree that never overwrites the canonical seeds).
    seed_tag = campaign.seed_tag or "ntru"
    tasks = [
        (n, beta, seed, q, campaign.precision,
         campaign.tours_by_beta[beta], campaign.generator, seed_tag,
         campaign.backend)
        for n in campaign.n_grid
        for beta in campaign.beta_grid
        for seed in range(1, campaign.num_seeds + 1)
    ]
    if dry_run:
        for n, beta, seed, *_ in tasks:
            mt = campaign.tours_by_beta[beta]
            print(f"[dry-run] {seed_tag} n={n} β={beta} seed={seed} -> "
                  + seed_path_for(seed_tag, n=n, beta=beta, seed=seed, q=q,
                                  precision=campaign.precision, max_tours=mt))
        return 0

    import multiprocessing as mp

    nproc = max(1, min(workers, (os.cpu_count() or 2), len(tasks)))
    total = len(tasks)
    print(f"NTRU: {total} tasks across {nproc} workers ...")
    done = written = 0
    advs: dict[int, list] = {}
    with mp.Pool(nproc) as pool:
        for n, beta, seed, adv, status in pool.imap_unordered(
                _ntru_seed_worker, tasks):
            done += 1
            if status == "ok":
                written += 1
                advs.setdefault(n, []).append(adv)
                print(f"  [{done}/{total}] n={n:3d} β={beta} seed={seed}: "
                      f"advantage={adv:+.6f}")
            elif status == "skip":
                print(f"  [{done}/{total}] n={n:3d} β={beta} seed={seed}: skip")
            else:
                print(f"  [{done}/{total}] ERROR n={n} seed={seed}: {status}",
                      file=sys.stderr)
    for n in sorted(advs):
        a = advs[n]
        print(f"  n={n}: mean advantage={sum(a) / len(a):+.4f} "
              f"(min {min(a):+.4f}, max {max(a):+.4f}, {len(a)} new)")
    PIPELINE.info("ntru run ok", cat="sweep",
                  campaign=campaign.name, q=q,
                  n_grid=list(campaign.n_grid), seeds=campaign.num_seeds,
                  tasks=total, written=written)
    print(f"NTRU run OK: {written} seeds written / {total} tasks.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dispatch a campaign declared in config/sweep.toml.",
    )
    ap.add_argument("--campaign", required=True,
                    help="campaign name from config/sweep.toml")
    ap.add_argument("--n", type=int, default=None,
                    help="dimension (defaults to first entry in campaign.n_grid)")
    ap.add_argument("--beta", type=int, default=None,
                    help="block size (defaults to first entry in campaign.beta_grid)")
    ap.add_argument("--start", type=int, default=None,
                    help="seed range start (1-indexed, inclusive)")
    ap.add_argument("--end", type=int, default=None,
                    help="seed range end (1-indexed, inclusive)")
    ap.add_argument("--seeds", type=int, default=None,
                    help="seed count (defaults to campaign.num_seeds)")
    ap.add_argument("--workers", type=int, default=22,
                    help="pool size (default 22)")
    ap.add_argument("--q", type=int, default=None,
                    help="override campaign q (e.g. an NTRU fatigue q-sweep)")
    ap.add_argument("--precision", type=int, default=None,
                    help="override campaign MPFR precision")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved dispatch invocation; do not run")
    args = ap.parse_args()

    try:
        campaign = load_campaign(args.campaign)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # CLI overrides (q / precision) for exploratory sweeps. The seed-path
    # tree keys on q + precision, so overridden runs land in their own dirs.
    import dataclasses
    if args.q is not None:
        campaign = dataclasses.replace(campaign, q=args.q)
    if args.precision is not None:
        campaign = dataclasses.replace(campaign, precision=args.precision)

    n = args.n if args.n is not None else campaign.n_grid[0]
    beta = args.beta if args.beta is not None else campaign.beta_grid[0]
    if n not in campaign.n_grid:
        print(f"WARNING: n={n} not in campaign.n_grid={campaign.n_grid}; "
              f"proceeding anyway (override mode)", file=sys.stderr)
    if beta not in campaign.beta_grid:
        print(f"WARNING: β={beta} not in campaign.beta_grid={campaign.beta_grid}; "
              f"proceeding anyway (override mode)", file=sys.stderr)

    start = args.start
    end = args.end
    if start is not None and end is None:
        end = campaign.num_seeds
    if end is not None and start is None:
        start = 1

    seeds = args.seeds if args.seeds is not None else (
        end - start + 1 if start is not None else campaign.num_seeds
    )

    if not get_run_id():
        new_run_id()

    PIPELINE.info(
        "dispatch", cat="sweep",
        campaign=args.campaign, n=n, beta=beta,
        seeds=seeds, workers=args.workers,
        precision=campaign.precision, q=campaign.q,
        max_tours=campaign.tours_by_beta.get(beta),
        generator=campaign.generator,
        dry_run=args.dry_run,
    )

    role = _select_runner(args.campaign)
    if role == "ntru_smoke":
        return _dispatch_ntru(campaign, dry_run=args.dry_run, persist=False)
    if role == "ntru":
        return _dispatch_ntru(campaign, dry_run=args.dry_run, persist=True,
                              workers=args.workers)
    if role == "q3329_verify":
        return _dispatch_q3329_verify(
            campaign, n, beta,
            start=start or 1, end=end or seeds,
            seeds=seeds, workers=args.workers, dry_run=args.dry_run,
        )
    if role == "convergence":
        return _dispatch_convergence(
            campaign, n, beta,
            seeds=seeds, workers=args.workers, dry_run=args.dry_run,
        )
    if role == "tours3x":
        return _dispatch_tours3x(
            campaign, n, beta,
            seeds=seeds, workers=args.workers, dry_run=args.dry_run,
        )
    if role == "fplll_image":
        return _dispatch_fplll_image(campaign)

    print(f"ERROR: unhandled runner role {role!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
