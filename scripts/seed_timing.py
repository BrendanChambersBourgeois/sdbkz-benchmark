"""Sweep wall-time estimator for the SD-BKZ benchmark.

Library-only module — no main entry point. Imported by:
  - scripts/estimate_sweep_time.py  (CLI wrapper, ad-hoc planning)
  - scripts/run_convergence.py      (dispatcher, ETA at sweep launch)

The estimator combines two methods, surfaces both, and recommends one:

  Naive method
      Multiply median per-tour cost (from existing seed JSONs at the
      target ``(n, β)``) by ``max_tours``. Overestimates long runs
      because BKZ AUTO_ABORT and basis stabilisation cause per-tour
      cost to drop in late tours — empirically observed at roughly
      0.6× the naive prediction for ``mt1000`` runs.

  Anchored method
      Scale a *completed* long-run reference (``mt1000`` preferred,
      ``mt500`` fallback) by the ratio of per-tour costs at the target
      ``(n, β)`` versus the anchor's ``(n, β)``. Substantially more
      accurate when an anchor exists and the calling code's per-tour
      cost regime hasn't drifted from the anchor's.

The estimator never crashes on missing data or stale anchors; it
falls back to naive with a note in ``SweepEstimate.notes`` and flips
``method_recommended`` accordingly.

Anchor staleness
----------------
Per-seed JSONs do not embed a git SHA (would break the paper-safety
SHA-256 chain on re-runs). We use seed-file mtime as a proxy for
"how recent was this anchor measured". If the youngest anchor seed is
older than ``anchor_age_warn_days`` (default 7), the estimator logs
a warning, flips ``method_recommended`` to ``"naive"``, and reports
``anchor_age_days`` so the caller can audit. The most recent commit
to the load-bearing numerical files
(``scripts/_bkz_core.py`` / ``scripts/_math_core.py``) is included in
the notes when available.

Cache
-----
Reading 4,500+ seed JSONs takes 3–5 s. ``per_tour_cost_table`` takes
an optional ``cache_path`` argument; when present and fresher than
every seed file the cache covers, the JSON is read in O(ms). Cache
freshness is mtime-based — never trust silently. The cache is written
by ``scripts/build_seed_manifest.py`` after manifest rebuild (see
:func:`per_tour_cost_table_to_dict` / :func:`per_tour_cost_table_from_dict`).
"""
from __future__ import annotations

import dataclasses
import glob
import json
import math
import os
import statistics
import subprocess
import time
from typing import Iterable, Literal, Optional, Sequence


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SEED_GLOBS: tuple[str, ...] = (
    "results/seeds/main/q97/*/seed*.json",
    "results/seeds/convergence/q97/*/seed*.json",
)
DEFAULT_CACHE_PATH = "results/paper_claims/per_tour_cost_table.json"

# Files whose contents materially affect per-tour cost. Any commit touching
# these invalidates the implicit code-version assumption baked into
# anchored predictions.
NUMERICAL_HOTSPOT_FILES: tuple[str, ...] = (
    "scripts/_bkz_core.py",
    "scripts/_math_core.py",
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class PerTourCost:
    """Median per-tour wall time at a single ``(n, β)`` point.

    Fields
    ------
    n
        Lattice dimension.
    beta
        BKZ block size.
    bkz_seconds_per_tour
        Median across all seeds: ``bkz_time / bkz_tours_run``.
    sdbkz_seconds_per_tour
        Median across all seeds: ``sdbkz_time / sdbkz_tours_run``.
    sample_seeds
        How many seed JSONs contributed to the medians (for confidence).
    """

    n: int
    beta: int
    bkz_seconds_per_tour: float
    sdbkz_seconds_per_tour: float
    sample_seeds: int


@dataclasses.dataclass(frozen=True)
class SweepEstimate:
    """Wall-time estimate for a planned convergence sweep.

    All ``predicted_wall_h_*`` fields are in hours. ``None`` indicates the
    method was inapplicable (e.g., no anchor found).

    The estimator never raises on missing data — degraded estimates carry
    explanatory strings in ``notes``.
    """

    # Inputs
    n: int
    beta: int
    max_tours: int
    num_seeds: int
    num_workers: int

    # Predictions (hours)
    predicted_wall_h_naive: Optional[float]
    predicted_wall_h_anchored: Optional[float]
    predicted_wall_h_p95: Optional[float]
    mad_h: Optional[float]

    # Anchor traceability
    anchor_used: Optional[tuple[int, int, int]]   # (n, β, max_tours)
    anchor_age_days: Optional[float]
    anchor_source_paths: tuple[str, ...]
    last_numerical_commit_sha: Optional[str]

    # Recommendation
    method_recommended: Literal["naive", "anchored", "unknown"]
    notes: tuple[str, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _seconds_to_hours(s: float) -> float:
    return s / 3600.0


def _lookup_cost(
    cost_table: dict[tuple[int, int], PerTourCost],
    n: int,
    beta: int,
) -> tuple[Optional[PerTourCost], Optional[str]]:
    """Look up per-tour cost for ``(n, β)`` with adjacent-dim extrapolation.

    Returns ``(cost, note)`` where ``note`` is ``None`` for exact hits or
    an explanatory string when interpolation / extrapolation kicked in.
    Strategy:

    1. **Exact hit** — return the cached row, no note.
    2. **Interpolate** — same-β rows exist on both sides of the target
       ``n``. Linear interpolate the BKZ and SD-BKZ per-tour costs.
    3. **Extrapolate** — same-β rows exist only on one side. Use the two
       closest points on that side and linearly extrapolate. If only one
       same-β row exists on the relevant side, fall back to that single
       row as a nearest-neighbour estimate (flagged in the note).
    4. **No data** — no same-β row exists. Return ``(None, note)`` so
       the caller can degrade to the unknown path.

    The synthetic :class:`PerTourCost` carries ``sample_seeds=0`` so a
    consumer can distinguish extrapolated rows from observed ones.
    """
    exact = cost_table.get((n, beta))
    if exact is not None:
        return exact, None

    same_beta = sorted(
        ((nk, row) for (nk, b), row in cost_table.items() if b == beta and nk != n),
        key=lambda kv: kv[0],
    )
    if not same_beta:
        return None, (
            f"No per-tour cost rows exist at β={beta}; "
            "extrapolation requires at least one same-β anchor."
        )

    below = [(nk, row) for nk, row in same_beta if nk < n]
    above = [(nk, row) for nk, row in same_beta if nk > n]

    def _blend(p1_n: int, p1: PerTourCost, p2_n: int, p2: PerTourCost) -> PerTourCost:
        # Linear blend; works for both interpolation (n between p1_n,p2_n)
        # and extrapolation (n outside the bracket).
        if p2_n == p1_n:
            t = 0.0
        else:
            t = (n - p1_n) / (p2_n - p1_n)
        bkz = max(0.0, p1.bkz_seconds_per_tour + t * (p2.bkz_seconds_per_tour - p1.bkz_seconds_per_tour))
        sdb = max(0.0, p1.sdbkz_seconds_per_tour + t * (p2.sdbkz_seconds_per_tour - p1.sdbkz_seconds_per_tour))
        return PerTourCost(
            n=n, beta=beta,
            bkz_seconds_per_tour=bkz,
            sdbkz_seconds_per_tour=sdb,
            sample_seeds=0,
        )

    if below and above:
        p1_n, p1 = below[-1]
        p2_n, p2 = above[0]
        cost = _blend(p1_n, p1, p2_n, p2)
        return cost, (
            f"Per-tour cost for (n={n}, β={beta}) linearly interpolated "
            f"from anchors at n={p1_n} and n={p2_n}."
        )

    if len(below) >= 2:
        p1_n, p1 = below[-2]
        p2_n, p2 = below[-1]
        cost = _blend(p1_n, p1, p2_n, p2)
        return cost, (
            f"Per-tour cost for (n={n}, β={beta}) linearly extrapolated "
            f"from anchors at n={p1_n} and n={p2_n} (below-target, "
            "no observed n≥target at this β)."
        )

    if len(above) >= 2:
        p1_n, p1 = above[0]
        p2_n, p2 = above[1]
        cost = _blend(p1_n, p1, p2_n, p2)
        return cost, (
            f"Per-tour cost for (n={n}, β={beta}) linearly extrapolated "
            f"from anchors at n={p1_n} and n={p2_n} (above-target, "
            "no observed n≤target at this β)."
        )

    nk, only_row = same_beta[0]
    nn = PerTourCost(
        n=n, beta=beta,
        bkz_seconds_per_tour=only_row.bkz_seconds_per_tour,
        sdbkz_seconds_per_tour=only_row.sdbkz_seconds_per_tour,
        sample_seeds=0,
    )
    return nn, (
        f"Per-tour cost for (n={n}, β={beta}) approximated from the only "
        f"available same-β anchor (n={nk}); single-point nearest-neighbour "
        "fallback, treat the prediction as a rough lower bound."
    )


def _read_seed_json(path: str) -> Optional[dict]:
    """Read a seed JSON, return None on any read or parse failure.

    Narrow exception list — never swallow numpy / OOM / KeyboardInterrupt.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _per_tour_from_seed(d: dict) -> Optional[tuple[float, float]]:
    """Extract ``(bkz_per_tour, sdbkz_per_tour)`` seconds from one seed dict.

    Returns None if any required field is missing or zero (avoids div-by-zero).
    """
    try:
        bkz_t = float(d["bkz_time"])
        sd_t = float(d["sdbkz_time"])
        bkz_tr = int(d.get("bkz_tours_run") or d.get("max_tours") or 0)
        sd_tr = int(d.get("sdbkz_tours_run") or d.get("max_tours") or 0)
    except (KeyError, ValueError, TypeError):
        return None
    if bkz_tr <= 0 or sd_tr <= 0:
        return None
    return bkz_t / bkz_tr, sd_t / sd_tr


def _expand_globs(patterns: Sequence[str]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        path = pat if os.path.isabs(pat) else os.path.join(REPO_ROOT, pat)
        out.extend(glob.glob(path))
    return out


def _max_mtime(paths: Iterable[str]) -> float:
    """Maximum mtime across paths, or 0.0 if iterable is empty / all missing."""
    best = 0.0
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > best:
            best = m
    return best


def _last_relevant_commit_sha() -> Optional[str]:
    """Return the most recent commit SHA touching any numerical hotspot file.

    Returns None if git is unavailable, repo is shallow, or files don't exist
    in history. Never raises.
    """
    cmd = ["git", "-C", REPO_ROOT, "log", "-1", "--format=%H", "--"] + list(NUMERICAL_HOTSPOT_FILES)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    sha = (result.stdout or "").strip()
    return sha or None


def _median_absolute_deviation(values: Sequence[float]) -> float:
    """MAD: median(|x_i - median(x)|). Robust spread metric.

    Returns 0.0 for samples of size < 2.
    """
    if len(values) < 2:
        return 0.0
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values)


def _percentile(values: Sequence[float], p: float) -> float:
    """Empirical percentile (no interpolation between adjacent ranks).

    p is in [0, 100]. Returns the value at the rounded rank index.
    """
    if not values:
        raise ValueError("percentile of empty sample")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(math.ceil(p / 100.0 * len(s))) - 1))
    return s[k]


# ---------------------------------------------------------------------------
# Public API: per-tour cost table
# ---------------------------------------------------------------------------

def per_tour_cost_table(
    seed_glob_patterns: Optional[Sequence[str]] = None,
    cache_path: Optional[str] = None,
    max_cache_age_seconds: float = 24 * 3600,
) -> dict[tuple[int, int], PerTourCost]:
    """Build the per-(n, β) per-tour cost table from existing seed JSONs.

    Parameters
    ----------
    seed_glob_patterns
        Glob patterns for seed JSON files to scan. Relative paths are
        resolved against the repo root. Defaults to the canonical
        main + convergence trees at q=97.
    cache_path
        Optional path to a cached table JSON (relative to repo root or
        absolute). When supplied AND the cache is fresher than every
        candidate seed file, the cache is loaded in O(ms) instead of
        re-scanning the seed corpus. Stale cache is silently rebuilt.
    max_cache_age_seconds
        Reject the cache outright if it is older than this regardless
        of seed mtimes (defends against clock skew / forgotten manifests).
        Default 24 h.

    Returns
    -------
    dict[(n, β)] -> :class:`PerTourCost`
        Empty dict if no seeds matched.
    """
    patterns = tuple(seed_glob_patterns) if seed_glob_patterns is not None else DEFAULT_SEED_GLOBS
    seed_paths = _expand_globs(patterns)

    if cache_path is not None:
        abs_cache = cache_path if os.path.isabs(cache_path) else os.path.join(REPO_ROOT, cache_path)
        if os.path.exists(abs_cache):
            cache_mtime = os.path.getmtime(abs_cache)
            seed_max_mtime = _max_mtime(seed_paths)
            cache_age_s = time.time() - cache_mtime
            if cache_mtime >= seed_max_mtime and cache_age_s <= max_cache_age_seconds:
                cached = _read_seed_json(abs_cache)
                if cached is not None:
                    table = per_tour_cost_table_from_dict(cached)
                    if table:
                        return table

    table: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for path in seed_paths:
        d = _read_seed_json(path)
        if d is None:
            continue
        try:
            n = int(d["n"])
            beta = int(d["beta"])
        except (KeyError, ValueError, TypeError):
            continue
        per = _per_tour_from_seed(d)
        if per is None:
            continue
        table.setdefault((n, beta), []).append(per)

    out: dict[tuple[int, int], PerTourCost] = {}
    for (n, b), rows in table.items():
        bkz_med = statistics.median(r[0] for r in rows)
        sd_med = statistics.median(r[1] for r in rows)
        out[(n, b)] = PerTourCost(
            n=n, beta=b,
            bkz_seconds_per_tour=bkz_med,
            sdbkz_seconds_per_tour=sd_med,
            sample_seeds=len(rows),
        )
    return out


def per_tour_cost_table_to_dict(table: dict[tuple[int, int], PerTourCost]) -> dict:
    """Serialise a cost table to a JSON-safe dict (for cache write)."""
    return {
        "schema_version": 1,
        "generated_utc_epoch": time.time(),
        "entries": [dataclasses.asdict(v) for v in table.values()],
    }


def per_tour_cost_table_from_dict(payload: dict) -> dict[tuple[int, int], PerTourCost]:
    """Inverse of :func:`per_tour_cost_table_to_dict`. Tolerant of unknown keys."""
    out: dict[tuple[int, int], PerTourCost] = {}
    if not isinstance(payload, dict):
        return out
    for entry in payload.get("entries", []) or []:
        try:
            n = int(entry["n"])
            b = int(entry["beta"])
            out[(n, b)] = PerTourCost(
                n=n, beta=b,
                bkz_seconds_per_tour=float(entry["bkz_seconds_per_tour"]),
                sdbkz_seconds_per_tour=float(entry["sdbkz_seconds_per_tour"]),
                sample_seeds=int(entry.get("sample_seeds", 0)),
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


# ---------------------------------------------------------------------------
# Public API: anchor selection + per-seed wall samples
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _AnchorSample:
    """Internal: per-seed wall-time sample for one anchor configuration."""
    n: int
    beta: int
    max_tours: int
    paths: tuple[str, ...]
    wall_seconds_per_seed: tuple[float, ...]
    youngest_mtime: float


def _gather_anchor_samples(
    seed_glob_patterns: Sequence[str],
    min_max_tours: int = 500,
) -> dict[tuple[int, int, int], _AnchorSample]:
    """Group existing seed JSONs by ``(n, β, max_tours)`` and compute per-seed walls.

    Only configurations with ``max_tours >= min_max_tours`` are returned —
    short-budget runs (e.g., ``mt70``) don't represent the basis-stabilisation
    regime that mt1000 sweeps spend most of their time in.
    """
    paths = _expand_globs(seed_glob_patterns)
    grouped: dict[tuple[int, int, int], dict] = {}
    for p in paths:
        d = _read_seed_json(p)
        if d is None:
            continue
        try:
            n = int(d["n"]); b = int(d["beta"])
            mt = int(d.get("max_tours") or 0)
            bkz_t = float(d["bkz_time"]); sd_t = float(d["sdbkz_time"])
        except (KeyError, ValueError, TypeError):
            continue
        if mt < min_max_tours:
            continue
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        bucket = grouped.setdefault((n, b, mt), {"paths": [], "walls": [], "mtimes": []})
        bucket["paths"].append(p)
        bucket["walls"].append(bkz_t + sd_t)
        bucket["mtimes"].append(mtime)

    out: dict[tuple[int, int, int], _AnchorSample] = {}
    for key, bucket in grouped.items():
        n, b, mt = key
        out[key] = _AnchorSample(
            n=n, beta=b, max_tours=mt,
            paths=tuple(bucket["paths"]),
            wall_seconds_per_seed=tuple(bucket["walls"]),
            youngest_mtime=max(bucket["mtimes"]) if bucket["mtimes"] else 0.0,
        )
    return out


def _select_best_anchor(
    target_n: int,
    target_beta: int,
    target_max_tours: int,
    samples: dict[tuple[int, int, int], _AnchorSample],
) -> Optional[_AnchorSample]:
    """Pick the most representative anchor for the target sweep.

    Preference order:
        1. Same beta + same max_tours, smallest |Δn|
        2. Same beta, smallest |Δmax_tours| then smallest |Δn|
        3. Same dim, same max_tours, different beta (last resort)
        4. None
    """
    if not samples:
        return None

    same_beta = [s for s in samples.values() if s.beta == target_beta]

    same_beta_same_mt = [s for s in same_beta if s.max_tours == target_max_tours]
    if same_beta_same_mt:
        return min(same_beta_same_mt, key=lambda s: abs(s.n - target_n))

    if same_beta:
        return min(same_beta, key=lambda s: (abs(s.max_tours - target_max_tours), abs(s.n - target_n)))

    same_dim_same_mt = [s for s in samples.values()
                        if s.n == target_n and s.max_tours == target_max_tours]
    if same_dim_same_mt:
        return min(same_dim_same_mt, key=lambda s: abs(s.beta - target_beta))

    return None


# ---------------------------------------------------------------------------
# Public API: sweep estimate
# ---------------------------------------------------------------------------

def estimate_sweep_wall(
    n: int,
    beta: int,
    max_tours: int,
    num_seeds: int = 20,
    num_workers: int = 22,
    cost_table: Optional[dict[tuple[int, int], PerTourCost]] = None,
    seed_glob_patterns: Optional[Sequence[str]] = None,
    cache_path: Optional[str] = None,
    anchor_age_warn_days: float = 7.0,
) -> SweepEstimate:
    """Estimate wall time for a planned convergence sweep at ``(n, β, max_tours)``.

    Returns a :class:`SweepEstimate` with both naive and anchored predictions
    and a recommendation between them. The function never raises on missing
    data — degraded estimates carry explanatory strings in ``.notes``.

    Parameters
    ----------
    n, beta, max_tours
        Target sweep configuration.
    num_seeds, num_workers
        Pool shape. With ``num_seeds <= num_workers``, wall ≈ slowest seed
        (no queueing). With ``num_seeds > num_workers``, wall scales by
        ``ceil(num_seeds / num_workers)``.
    cost_table
        Optional pre-computed per-tour cost table. Pass to share work
        across multiple ``estimate_sweep_wall`` calls. If ``None``, the
        table is computed inline (cache-aware).
    seed_glob_patterns, cache_path
        Forwarded to :func:`per_tour_cost_table` if ``cost_table`` is
        not supplied.
    anchor_age_warn_days
        If the youngest seed in the chosen anchor is older than this
        threshold, the estimator flips ``method_recommended`` to
        ``"naive"`` and adds a warning to ``notes`` containing the age
        and the most recent commit SHA touching the numerical hotspot
        files.
    """
    notes: list[str] = []
    patterns = tuple(seed_glob_patterns) if seed_glob_patterns is not None else DEFAULT_SEED_GLOBS

    if cost_table is None:
        cost_table = per_tour_cost_table(
            seed_glob_patterns=patterns,
            cache_path=cache_path,
        )

    parallel_factor = max(1, math.ceil(num_seeds / max(1, num_workers)))

    naive_wall_h: Optional[float]
    target_cost, target_note = _lookup_cost(cost_table, n, beta)
    if target_note is not None:
        notes.append(target_note)
    if target_cost is None:
        naive_wall_h = None
        notes.append(f"No per-tour cost data for (n={n}, β={beta}); naive method unavailable.")
    else:
        per_seed_seconds_naive = max_tours * (
            target_cost.bkz_seconds_per_tour + target_cost.sdbkz_seconds_per_tour
        )
        naive_wall_h = _seconds_to_hours(per_seed_seconds_naive) * parallel_factor

    samples = _gather_anchor_samples(patterns)
    anchor = _select_best_anchor(n, beta, max_tours, samples)

    anchored_wall_h: Optional[float] = None
    p95_wall_h: Optional[float] = None
    mad_wall_h: Optional[float] = None
    anchor_used: Optional[tuple[int, int, int]] = None
    anchor_age_days: Optional[float] = None
    anchor_source_paths: tuple[str, ...] = ()
    method: Literal["naive", "anchored", "unknown"] = "unknown"
    last_sha = _last_relevant_commit_sha()

    if anchor is not None:
        anchor_used = (anchor.n, anchor.beta, anchor.max_tours)
        anchor_source_paths = anchor.paths
        anchor_age_days = (time.time() - anchor.youngest_mtime) / 86400.0

        anchor_cost, anchor_note = _lookup_cost(cost_table, anchor.n, anchor.beta)
        if anchor_note is not None:
            notes.append(anchor_note)
        if anchor_cost is None or target_cost is None:
            notes.append(
                "Anchor selected but per-tour cost lookup failed for either "
                f"target ({n}, {beta}) or anchor ({anchor.n}, {anchor.beta}); "
                "anchored method unavailable."
            )
        else:
            anchor_total_per_tour = (
                anchor_cost.bkz_seconds_per_tour + anchor_cost.sdbkz_seconds_per_tour
            )
            target_total_per_tour = (
                target_cost.bkz_seconds_per_tour + target_cost.sdbkz_seconds_per_tour
            )
            if anchor_total_per_tour <= 0:
                notes.append("Anchor per-tour cost is zero; anchored method unavailable.")
            else:
                cost_ratio = target_total_per_tour / anchor_total_per_tour
                tour_ratio = max_tours / max(1, anchor.max_tours)

                anchor_per_seed_walls = list(anchor.wall_seconds_per_seed)
                scaled_per_seed_walls = [w * cost_ratio * tour_ratio for w in anchor_per_seed_walls]

                p50_per_seed = statistics.median(scaled_per_seed_walls)
                p95_per_seed = _percentile(scaled_per_seed_walls, 95)
                mad_per_seed = _median_absolute_deviation(scaled_per_seed_walls)

                anchored_wall_h = _seconds_to_hours(p50_per_seed) * parallel_factor
                p95_wall_h = _seconds_to_hours(p95_per_seed) * parallel_factor
                mad_wall_h = _seconds_to_hours(mad_per_seed) * parallel_factor

        if anchor_age_days is not None and anchor_age_days > anchor_age_warn_days:
            stamp = (
                f"Anchor age {anchor_age_days:.1f} d exceeds threshold "
                f"{anchor_age_warn_days:.1f} d; falling back to naive."
            )
            if last_sha:
                stamp += f" Last commit touching numerical hotspots: {last_sha[:12]}."
            notes.append(stamp)
            method = "naive" if naive_wall_h is not None else "unknown"
        elif anchored_wall_h is not None:
            method = "anchored"
        elif naive_wall_h is not None:
            method = "naive"
        else:
            method = "unknown"
    else:
        notes.append(
            "No suitable anchor (no completed mt>=500 sweep with same beta found); "
            "anchored method unavailable."
        )
        method = "naive" if naive_wall_h is not None else "unknown"

    if method == "unknown":
        notes.append(
            "Estimator has insufficient data for any prediction. "
            "Run a single seed at the target configuration to bootstrap."
        )

    return SweepEstimate(
        n=n, beta=beta, max_tours=max_tours,
        num_seeds=num_seeds, num_workers=num_workers,
        predicted_wall_h_naive=naive_wall_h,
        predicted_wall_h_anchored=anchored_wall_h,
        predicted_wall_h_p95=p95_wall_h,
        mad_h=mad_wall_h,
        anchor_used=anchor_used,
        anchor_age_days=anchor_age_days,
        anchor_source_paths=anchor_source_paths,
        last_numerical_commit_sha=last_sha,
        method_recommended=method,
        notes=tuple(notes),
    )
