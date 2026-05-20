#!/usr/bin/env python3
"""Single-entry-point campaign dispatcher driven by ``config/sweep.toml``.

Replaces the per-cell launcher scripts (`run_cliff_500bit.py`,
`run_n100_beta40.py`, `run_q3329_n90.py`, `run_q3329_n100_local.py`,
`run_overnight_q3329_intermediate_1000bit.py`,
`run_fplll54_sensitivity.py`, ...) with one parametrised driver.

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
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved dispatch invocation; do not run")
    args = ap.parse_args()

    try:
        campaign = load_campaign(args.campaign)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

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
        dry_run=args.dry_run,
    )

    role = _select_runner(args.campaign)
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
