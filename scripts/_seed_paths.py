"""Canonical seed-write paths under the v1.3 results/seeds/<campaign>/ tree.

Single source of truth for runner-side writes; mirrors the logic in
`migrate_seeds_to_new_layout.new_path_for()` so ongoing writes land in
exactly the same location a one-shot re-migration would produce.

Design reference: Research/backlog/2026-04-18_seed_consolidation.md
§Proposed structure. Schema invariants (keys per entry, per-campaign
layout rules) live in `scripts/build_seed_manifest.py`; this module is
*path-only* so it can be imported from runners at the hot-path layer
without dragging in the manifest-walking dependencies.
"""

from __future__ import annotations

import os
from typing import Optional

NEW_LAYOUT_ROOT = os.path.join("results", "seeds")

_KNOWN_CAMPAIGNS = frozenset({
    "main", "q3329", "cliff500", "fplll_sensitivity",
    "tours3x", "convergence", "ntru", "ntru_patched", "ntru_g6k",
    "ntru_xarch", "estimator_probe",
    # forever-runner idle-filler tree (never-idle seed-topup). SEPARATE by
    # design so the filler can NEVER touch/re-open a published cell (the B2
    # review's core integrity fix); excluded from the canonical fplll manifest
    # below, like ntru_patched/ntru_g6k.
    "ntru_b2",
})


def _leaf_name(seed: int, *, is_fat: bool, cloud: bool, campaign: str) -> str:
    """Filename at the leaf: seedNNNN[_cloud][_fat].json.

    `_cloud` is used only on the `main` campaign, because paper §3.7's
    cross-environment verification produced two byte-distinct copies of
    every main-sweep seed (results/raw/ local + results/cloud/ AWS).
    """
    suffix = ""
    if campaign == "main" and cloud:
        suffix += "_cloud"
    if is_fat:
        suffix += "_fat"
    return f"seed{seed:04d}{suffix}.json"


def _require(value: object, name: str, campaign: str) -> object:
    if value is None:
        raise ValueError(
            f"{campaign} campaign requires {name}; got None"
        )
    return value


def seed_dir_for(
    campaign: str,
    n: int,
    beta: int,
    *,
    q: int = 97,
    precision: Optional[int] = None,
    max_tours: Optional[int] = None,
    fplll_version: Optional[str] = None,
    base: str = ".",
) -> str:
    """Return the directory that holds seed files for a (campaign, n, β, ...)
    combination. Mirrors the dir-level half of `new_path_for()`."""
    if campaign not in _KNOWN_CAMPAIGNS:
        raise ValueError(
            f"unknown campaign: {campaign!r}. "
            f"Expected one of {sorted(_KNOWN_CAMPAIGNS)}."
        )

    n_beta = f"n{n:03d}_beta{beta:02d}"

    if campaign == "main":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "main", "q97", n_beta)
    elif campaign == "q3329":
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "q3329", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "cliff500":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "cliff500", "q97", n_beta)
    elif campaign == "fplll_sensitivity":
        ver = _require(fplll_version, "fplll_version", campaign)
        ver_slug = "v" + str(ver).replace(".", "_")
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "fplll_sensitivity", ver_slug, "q97", n_beta
        )
    elif campaign == "tours3x":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "tours3x", "q97", n_beta)
    elif campaign == "convergence":
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "convergence", "q97", f"{n_beta}_mt{mt}"
        )
    elif campaign == "ntru":
        # NTRU sweeps q (fatigue study), so q is keyed in the path:
        # seeds/ntru/q{q}/p{prec}_mt{mt}/n{n}_beta{b}/. Mirrors the
        # q3329 layout with an extra q segment.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "ntru", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "ntru_patched":
        # Same layout as ntru, separate root: a Kahan-patched-fplll rerun of
        # contaminated NTRU seeds (paper §8 validation). Kept apart from the
        # canonical ntru/ tree so the patched engine's output never overwrites
        # or is confused with the as-published seeds.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "ntru_patched", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "ntru_g6k":
        # g6k-engine NTRU seeds (backend="g6k"); same layout as ntru, separate
        # root so the sieve-engine output never mixes with the fplll ntru/
        # tree. precision keys the path but the g6k sieve ignores MPFR bits.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "ntru_g6k", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "ntru_xarch":
        # Cross-architecture capability test: same layout as ntru, separate
        # root so externally-regenerated seeds never mix with the canonical
        # fplll ntru/ tree. Compared to ntru/ by science-field hash.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "ntru_xarch", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "estimator_probe":
        # Paper-3 feasibility: higher-tours LWE reruns to disambiguate the
        # d(real,CN11) dim-growth. q+precision+max_tours all keyed so a
        # higher-mt rerun never collides with the published main/ tree (or
        # with another mt in this tree). Separate root from main by design.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "estimator_probe", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    elif campaign == "ntru_b2":
        # forever-runner idle-filler: same layout as ntru, separate root so the
        # extra-power seeds never touch or re-open a published cell's N.
        p = int(_require(precision, "precision", campaign))
        mt = int(_require(max_tours, "max_tours", campaign))
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "ntru_b2", f"q{q}", f"p{p}_mt{mt}", n_beta
        )
    else:
        raise AssertionError("unreachable")  # pragma: no cover

    return os.path.join(base, leaf_dir) if base != "." else leaf_dir


def seed_path_for(
    campaign: str,
    n: int,
    beta: int,
    seed: int,
    *,
    q: int = 97,
    precision: Optional[int] = None,
    max_tours: Optional[int] = None,
    fplll_version: Optional[str] = None,
    is_fat: bool = False,
    cloud: bool = False,
    base: str = ".",
) -> str:
    """Canonical file path where a runner should write this seed.

    Example:
        >>> seed_path_for("main", n=100, beta=30, seed=1)
        'results/seeds/main/q97/n100_beta30/seed0001.json'

        >>> seed_path_for(
        ...     "q3329", n=100, beta=30, seed=11,
        ...     precision=1000, max_tours=70,
        ... )
        'results/seeds/q3329/p1000_mt70/n100_beta30/seed0011.json'

    Callers are expected to `os.makedirs(os.path.dirname(path),
    exist_ok=True)` before writing; this module avoids side-effects
    on import.
    """
    leaf_dir = seed_dir_for(
        campaign, n, beta,
        q=q, precision=precision, max_tours=max_tours,
        fplll_version=fplll_version, base=base,
    )
    return os.path.join(
        leaf_dir,
        _leaf_name(seed, is_fat=is_fat, cloud=cloud, campaign=campaign),
    )
