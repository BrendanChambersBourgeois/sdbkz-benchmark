"""Sweep wall-time estimator for the SD-BKZ benchmark.

Library-only module — no main entry point. Imported by:
  - scripts/estimate_sweep_time.py  (CLI wrapper, ad-hoc planning)
  - scripts/run_convergence.py      (dispatcher, ETA at sweep launch)

The estimator computes two methods and recommends naive:

  Naive method
      Median seed wall at the target ``(n, β[, q])``, each leg projected
      to ``max_tours`` (early-stopped legs keep their tours), keyed on
      precision. Recommended.

  Anchored method
      Scale a *completed* long-run reference (``mt1000`` preferred,
      ``mt500`` fallback) by the ratio of per-tour costs at the target
      ``(n, β)`` versus the anchor's ``(n, β)``. Reference only: it lost
      the backtest.

The estimator never crashes on missing data or stale anchors; degraded
estimates carry a note in ``SweepEstimate.notes``.

Anchor staleness
----------------
Per-seed JSONs do not embed a git SHA (would break the paper-safety
SHA-256 chain on re-runs). We use seed-file mtime as a proxy for
"how recent was this anchor measured". If the youngest anchor seed is
older than ``anchor_age_warn_days`` (default 7), the estimator logs
a warning, suppresses the anchored figures, and reports
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
:func:`per_tour_cost_table_to_dict` / :func:`per_tour_cost_table_from_dict`)
and read by the Paper 2 core-hours claim; :func:`estimate_sweep_wall`
does not use it.
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
from collections.abc import Callable, Iterable, Sequence
from operator import attrgetter
from typing import Literal, Optional

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
        ((nk, row) for (nk, b), row in cost_table.items() if b == beta),
        key=lambda kv: kv[0],
    )
    if not same_beta:
        return None, (
            f"No per-tour cost rows exist at β={beta}; "
            "extrapolation requires at least one same-β anchor."
        )

    below = [(nk, row) for nk, row in same_beta if nk < n]
    above = [(nk, row) for nk, row in same_beta if nk > n]

    negative: list[str] = []  # raw values of a blend clamped to 0, for the note

    def _blend(p1_n: int, p1: PerTourCost, p2_n: int, p2: PerTourCost) -> PerTourCost:
        # Linear blend; works for both interpolation (n between p1_n,p2_n)
        # and extrapolation (n outside the bracket).
        if p2_n == p1_n:
            t = 0.0
        else:
            t = (n - p1_n) / (p2_n - p1_n)
        raw_bkz = p1.bkz_seconds_per_tour + t * (p2.bkz_seconds_per_tour - p1.bkz_seconds_per_tour)
        raw_sdb = p1.sdbkz_seconds_per_tour + t * (p2.sdbkz_seconds_per_tour - p1.sdbkz_seconds_per_tour)
        if raw_bkz < 0 or raw_sdb < 0:
            negative.append(f" Linear extrapolation went negative (bkz {raw_bkz:.3g}s, "
                            f"sdbkz {raw_sdb:.3g}s per tour); clamped to 0.")
        bkz = max(0.0, raw_bkz)
        sdb = max(0.0, raw_sdb)
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
        # BKZ per-tour cost is physically monotone-non-decreasing in n
        # at fixed β. Local dips in the anchor curve (sampling noise)
        # can drive linear extrapolation below the last observed
        # anchor; clamp the extrapolated total to be no smaller than
        # the highest-n below-target anchor so the estimator does not
        # under-predict wall time on dimension extensions.
        below_max_total = max(
            r.bkz_seconds_per_tour + r.sdbkz_seconds_per_tour for _, r in below
        )
        target_total = cost.bkz_seconds_per_tour + cost.sdbkz_seconds_per_tour
        clamped = False
        if target_total < below_max_total and below_max_total > 0:
            scale = below_max_total / max(target_total, 1e-12)
            cost = PerTourCost(
                n=n, beta=beta,
                bkz_seconds_per_tour=cost.bkz_seconds_per_tour * scale,
                sdbkz_seconds_per_tour=cost.sdbkz_seconds_per_tour * scale,
                sample_seeds=0,
            )
            clamped = True
        gap = n - p2_n
        note = (
            f"Per-tour cost for (n={n}, β={beta}) linearly extrapolated "
            f"from anchors at n={p1_n} and n={p2_n} ({gap} dim past last "
            "below-target anchor; no observed n≥target at this β)."
        )
        if clamped:
            note += (
                f" Extrapolation produced a total per-tour cost below the "
                f"max observed below-target anchor ({below_max_total:.1f}s); "
                "clamped to that floor on monotone-cost grounds."
            )
        return cost, note + "".join(negative)

    if len(above) >= 2:
        p1_n, p1 = above[0]
        p2_n, p2 = above[1]
        cost = _blend(p1_n, p1, p2_n, p2)
        gap = p1_n - n
        return cost, (
            f"Per-tour cost for (n={n}, β={beta}) linearly extrapolated "
            f"from anchors at n={p1_n} and n={p2_n} ({gap} dim below first "
            "above-target anchor; no observed n≤target at this β)."
        ) + "".join(negative)

    nk, only_row = same_beta[0]
    nn = PerTourCost(
        n=n, beta=beta,
        bkz_seconds_per_tour=only_row.bkz_seconds_per_tour,
        sdbkz_seconds_per_tour=only_row.sdbkz_seconds_per_tour,
        sample_seeds=0,
    )
    direction = "below" if nk < n else "above"
    bound = "lower" if direction == "below" else "upper"
    return nn, (
        f"Per-tour cost for (n={n}, β={beta}) approximated from the only "
        f"available same-β anchor (n={nk}, {direction} target); single-point "
        f"nearest-neighbour fallback, treat the prediction as a rough "
        f"{bound} bound."
    )


def _read_seed_json(path: str) -> Optional[dict]:
    """Read a seed JSON, return None on any read or parse failure.

    Narrow exception list — never swallow numpy / OOM / KeyboardInterrupt.
    Forces UTF-8 because JSON is UTF-8 by spec and the default open mode
    is locale-dependent; defensive against future cross-machine drift.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _seed_tours_run(d: dict, key: str, array_key: str) -> int:
    """Resolve the actual tours-run count for one algorithm side.

    Preference order (most accurate first):
      1. Explicit ``bkz_tours_run`` / ``sdbkz_tours_run`` field (main-sweep
         schema; reflects AUTO_ABORT termination).
      2. Length of ``bkz_dln_per_tour`` / ``sdbkz_dln_per_tour`` array
         (convergence schema; reflects actual tours executed).
      3. ``max_tours`` field (last-resort fallback for legacy schemas).

    Returns 0 on missing data so the caller can drop the seed.
    """
    val = d.get(key)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    arr = d.get(array_key)
    if isinstance(arr, (list, tuple)) and arr:
        return len(arr)
    mt = d.get("max_tours")
    try:
        return int(mt) if mt is not None else 0
    except (ValueError, TypeError):
        return 0


def _expand_globs(patterns: Sequence[str]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        path = pat if os.path.isabs(pat) else os.path.join(REPO_ROOT, pat)
        out.extend(glob.glob(path, recursive=True))
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
            if cache_mtime > seed_max_mtime and cache_age_s <= max_cache_age_seconds:
                cached = _read_seed_json(abs_cache)
                if cached is not None:
                    table = per_tour_cost_table_from_dict(cached)
                    if table:
                        return table

    return _median_cost_table(_seed_rows(seed_paths), _BY_NB)


@dataclasses.dataclass(frozen=True)
class _SeedRow:
    """Timing fields of one seed JSON."""
    path: str
    mtime: float
    n: int
    beta: int
    q: Optional[int]
    precision: Optional[int]
    max_tours: Optional[int]
    bkz_time: float
    sdbkz_time: float
    bkz_tours_run: int
    sdbkz_tours_run: int
    bkz_early: bool
    sdbkz_early: bool


def _seed_rows(paths: Iterable[str]) -> list[_SeedRow]:
    """Read each seed JSON once; unreadable or malformed seeds dropped."""
    rows: list[_SeedRow] = []
    for path in paths:
        d = _read_seed_json(path)
        if d is None:
            continue
        try:
            n = int(d["n"]); beta = int(d["beta"])
            bkz_t = float(d["bkz_time"]); sd_t = float(d["sdbkz_time"])
            q = _int_or_none(d.get("q", 97))
            precision = _int_or_none(d.get("precision"))
            mt = _int_or_none(d.get("max_tours"))
            mtime = os.path.getmtime(path)
        except (KeyError, ValueError, TypeError, OSError):
            continue
        bkz_tr = _seed_tours_run(d, "bkz_tours_run", "bkz_dln_per_tour")
        sd_tr = _seed_tours_run(d, "sdbkz_tours_run", "sdbkz_dln_per_tour")
        if bkz_tr <= 0 or sd_tr <= 0:
            continue
        rows.append(_SeedRow(
            path=path, mtime=mtime, n=n, beta=beta,
            q=q, precision=precision, max_tours=mt,
            bkz_time=bkz_t, sdbkz_time=sd_t,
            bkz_tours_run=bkz_tr, sdbkz_tours_run=sd_tr,
            bkz_early=_stopped_early(d.get("bkz_termination"), bkz_tr, mt),
            sdbkz_early=_stopped_early(d.get("sdbkz_termination"), sd_tr, mt),
        ))
    return rows


def _int_or_none(v) -> Optional[int]:
    """None stays None; anything else must parse."""
    return None if v is None else int(v)


def _stopped_early(termination, tours_run: int, max_tours: Optional[int]) -> bool:
    """Whether a leg stopped before its budget."""
    if termination is not None:
        return termination == "stagnated"
    return max_tours is not None and tours_run < max_tours


def _projected_tours(tours_run: int, early: bool, max_tours: int) -> int:
    """Tours a leg would run under a ``max_tours`` budget."""
    return min(tours_run, max_tours) if early else max_tours


def _projected_walls(r: _SeedRow, max_tours: int) -> tuple[float, float]:
    """(BKZ, SD-BKZ) leg walls of one seed projected to ``max_tours``."""
    return (r.bkz_time / r.bkz_tours_run
            * _projected_tours(r.bkz_tours_run, r.bkz_early, max_tours),
            r.sdbkz_time / r.sdbkz_tours_run
            * _projected_tours(r.sdbkz_tours_run, r.sdbkz_early, max_tours))


def _drop_cloud_twins(rows: Sequence[_SeedRow]) -> list[_SeedRow]:
    """Drop ``_cloud`` copies of seeds that also exist locally."""
    paths = {r.path for r in rows}
    return [r for r in rows
            if not (r.path.endswith("_cloud.json")
                    and r.path[:-len("_cloud.json")] + ".json" in paths)]


def _median_cost_table(
    rows: Iterable[_SeedRow],
    key: Callable[[_SeedRow], tuple],
    max_tours: Optional[int] = None,
) -> dict[tuple, PerTourCost]:
    """Median per-tour cost per cell, projected to ``max_tours`` when given."""
    buckets: dict[tuple, list[tuple[float, float]]] = {}
    for r in rows:
        if max_tours is None:
            leg = (r.bkz_time / r.bkz_tours_run, r.sdbkz_time / r.sdbkz_tours_run)
        elif max_tours > 0:
            bkz, sd = _projected_walls(r, max_tours)
            leg = (bkz / max_tours, sd / max_tours)
        else:
            leg = (0.0, 0.0)  # zero budget: zero wall
        buckets.setdefault(key(r), []).append(leg)
    return {
        k: PerTourCost(
            n=k[0], beta=k[1],
            bkz_seconds_per_tour=statistics.median(v[0] for v in vals),
            sdbkz_seconds_per_tour=statistics.median(v[1] for v in vals),
            sample_seeds=len(vals),
        )
        for k, vals in buckets.items()
    }


_BY_NBQ = attrgetter("n", "beta", "q")
_BY_NB = attrgetter("n", "beta")


def _precision_pool(
    rows: Sequence[_SeedRow], beta: int, precision: Optional[int],
) -> tuple[list[_SeedRow], list[str]]:
    """Seeds at ``precision`` when any exist at this β, else all, with a note."""
    if precision is None:
        return list(rows), []
    same = [r for r in rows if r.precision == precision]
    if any(r.beta == beta for r in same):
        return same, []
    return list(rows), [f"No seeds at precision={precision} for β={beta}; "
                        "estimate uses other precisions."]


def _naive_cost(
    rows: Sequence[_SeedRow],
    n: int,
    beta: int,
    max_tours: int,
    q: Optional[int],
    source: Optional[tuple[Sequence[_SeedRow], Sequence[_SeedRow]]] = None,
) -> tuple[Optional[PerTourCost], list[str]]:
    """Projected naive cost: (n, β, q) first, then exact q in ``source``, then (n, β).

    ``source`` = (rows at the target precision, all rows) from same-engine trees,
    used only when ``rows`` has no exact (n, β, q) cell.
    """
    notes: list[str] = []
    budgets = {r.max_tours for r in rows if r.beta == beta}
    if budgets and max_tours not in budgets:
        notes.append(f"No seeds at max_tours={max_tours} for β={beta}; projected from "
                     f"max_tours={sorted(budgets, key=lambda b: b or 0)}, less accurate "
                     "(see estimate_sweep_time --backtest, cross-budget).")
    cost, note = None, None
    if q is not None:
        cost, note = _lookup_cost_q(_median_cost_table(rows, _BY_NBQ, max_tours), n, beta, q)
        if (cost is None or note is not None) and source:
            hit = _source_cost_q(rows, source, n, beta, q, max_tours)
            if hit is not None:
                cost, note = hit
        if cost is None:
            notes.append(f"No (n={n}, β={beta}) cell at any q; q={q} ignored, "
                         "cost is q-blind.")
    if cost is None:
        cost, note = _lookup_cost(_median_cost_table(rows, _BY_NB, max_tours), n, beta)
    if note is not None:
        notes.append(note)
    return cost, notes


def _lookup_cost_q(
    table_q: dict[tuple[int, int, int], PerTourCost],
    n: int, beta: int, q: int,
) -> tuple[Optional[PerTourCost], Optional[str]]:
    """Per-(n, β) cost at the target q: exact (n, β, q), else nearest q.

    q drives cost far more than n at fixed (n, β) here, so we match q first
    (exact, then nearest available q at the same (n, β)). Returns (None, note)
    if no (n, β) cell exists at any q.
    """
    exact = table_q.get((n, beta, q))
    if exact is not None:
        return exact, None
    same_nb = sorted(
        ((qk, row) for (nk, b, qk), row in table_q.items()
         if nk == n and b == beta and qk is not None),
        key=lambda kv: kv[0],
    )
    if not same_nb:
        return None, None  # caller falls back to the (n, β) table
    qk, row = min(same_nb, key=lambda kv: abs(kv[0] - q))
    return row, (
        f"No per-tour cost at exactly (n={n}, β={beta}, q={q}); used nearest "
        f"observed q={qk} (cost varies strongly with q, so treat as approximate)."
    )


_BY_NBQP = attrgetter("n", "beta", "q", "precision")


def _per_tour(c: PerTourCost) -> float:
    return c.bkz_seconds_per_tour + c.sdbkz_seconds_per_tour


def _source_cost_q(
    rows: Sequence[_SeedRow],
    source: tuple[Sequence[_SeedRow], Sequence[_SeedRow]],
    n: int, beta: int, q: int, max_tours: int,
) -> Optional[tuple[PerTourCost, str]]:
    """Exact (n, β, q) from same-engine source trees, scaled to this run.

    Scale = median own/source per-tour cost over (n, β, q, precision) cells
    both have at this β, same-n cells only when any exist (that is where a
    host or build difference shows). None if the source lacks the cell too.
    """
    src_pool, src_all = source
    src = _median_cost_table(src_pool, _BY_NBQ, max_tours).get((n, beta, q))
    if src is None:
        return None
    own = _median_cost_table(rows, _BY_NBQP, max_tours)
    ref = _median_cost_table(src_all, _BY_NBQP, max_tours)
    shared = [k for k in own if k[1] == beta and k in ref and _per_tour(ref[k]) > 0]
    keys = [k for k in shared if k[0] == n] or shared
    head = (f"No (n={n}, β={beta}, q={q}) cell in this run; used that exact q from "
            f"same-engine source trees")
    if not keys:
        return src, head + ", unscaled (no shared cell to calibrate)."
    r = statistics.median(_per_tour(own[k]) / _per_tour(ref[k]) for k in keys)
    same_n = "same-n " if keys[0][0] == n else ""
    return (dataclasses.replace(src, bkz_seconds_per_tour=src.bkz_seconds_per_tour * r,
                                sdbkz_seconds_per_tour=src.sdbkz_seconds_per_tour * r),
            head + f" x {r:.3f} (own/source median over {len(keys)} shared {same_n}cells).")


def per_tour_cost_table_to_dict(table: dict[tuple[int, int], PerTourCost]) -> dict:
    """Serialise a cost table to a JSON-safe dict (for cache write)."""
    return {
        "schema_version": 1,
        # Deterministic provenance stamp (SOURCE_DATE_EPOCH or 0): this file is
        # committed under results/paper_claims/, and cache freshness uses the
        # file mtime (not this field), so a wall-clock value here only churns git
        # on every refresh with no content change. Frozen so a
        # refresh with unchanged cost data is byte-identical.
        "generated_utc_epoch": float(os.environ.get("SOURCE_DATE_EPOCH", "0")),
        "entries": [dataclasses.asdict(v) for v in table.values()],
    }


def per_tour_cost_table_from_dict(payload: dict) -> dict[tuple[int, int], PerTourCost]:
    """Inverse of :func:`per_tour_cost_table_to_dict`. Tolerant of unknown keys.

    Rejects payloads whose ``schema_version`` is unrecognised so a future
    v2 cache format does not silently load as v1 and quietly corrupt the
    cost table. Missing ``schema_version`` is tolerated for backwards
    compatibility with pre-versioned cache writes.
    """
    out: dict[tuple[int, int], PerTourCost] = {}
    if not isinstance(payload, dict):
        return out
    schema_version = payload.get("schema_version", 1)
    if schema_version != 1:
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
    """The seeds of one anchor configuration."""
    n: int
    beta: int
    max_tours: int
    rows: tuple[_SeedRow, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(r.path for r in self.rows)

    @property
    def youngest_mtime(self) -> float:
        return max(r.mtime for r in self.rows)


def _gather_anchor_samples(
    rows: Iterable[_SeedRow],
    min_max_tours: int = 500,
) -> dict[tuple[int, int, int], _AnchorSample]:
    """Group seeds by ``(n, β, max_tours)``.

    Only configurations with ``max_tours >= min_max_tours`` are returned —
    short-budget runs (e.g., ``mt70``) don't represent the basis-stabilisation
    regime that mt1000 sweeps spend most of their time in.
    """
    grouped: dict[tuple[int, int, int], list[_SeedRow]] = {}
    for r in rows:
        if (r.max_tours or 0) >= min_max_tours:
            grouped.setdefault((r.n, r.beta, r.max_tours), []).append(r)
    return {k: _AnchorSample(*k, rows=tuple(v)) for k, v in grouped.items()}


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

def _anchored_walls(
    rows: Sequence[_SeedRow],
    cost_table: dict[tuple[int, int], PerTourCost],
    n: int,
    beta: int,
    max_tours: int,
    q: Optional[int],
) -> tuple[Optional[_AnchorSample], Optional[list[float]], list[str]]:
    """Anchored method: best mt>=500 anchor's seeds, projected and cost-scaled."""
    anchor = _select_best_anchor(n, beta, max_tours, _gather_anchor_samples(rows))
    if anchor is None:
        return None, None, ["No suitable anchor (no completed mt>=500 sweep with same "
                            "beta found); anchored method unavailable."]
    notes: list[str] = []
    # Target cost: q-aware when q is given.
    target_cost, target_note = None, None
    if q is not None:
        target_cost, target_note = _lookup_cost_q(_median_cost_table(rows, _BY_NBQ), n, beta, q)
    if target_cost is None:
        target_cost, target_note = _lookup_cost(cost_table, n, beta)
    anchor_cost, anchor_note = _lookup_cost(cost_table, anchor.n, anchor.beta)
    notes += [f"Anchored: {x}" for x in (target_note, anchor_note) if x is not None]
    if anchor_cost is None or target_cost is None:
        notes.append(
            "Anchor selected but per-tour cost lookup failed for either "
            f"target ({n}, {beta}) or anchor ({anchor.n}, {anchor.beta}); "
            "anchored method unavailable."
        )
        return anchor, None, notes
    anchor_total = anchor_cost.bkz_seconds_per_tour + anchor_cost.sdbkz_seconds_per_tour
    if anchor_total <= 0:
        notes.append("Anchor per-tour cost is zero; anchored method unavailable.")
        return anchor, None, notes
    cost_ratio = (target_cost.bkz_seconds_per_tour + target_cost.sdbkz_seconds_per_tour) / anchor_total
    return anchor, [cost_ratio * sum(_projected_walls(r, max_tours)) for r in anchor.rows], notes


def estimate_sweep_wall(
    n: int,
    beta: int,
    max_tours: int,
    num_seeds: int = 20,
    num_workers: int = 22,
    cost_table: Optional[dict[tuple[int, int], PerTourCost]] = None,
    seed_glob_patterns: Optional[Sequence[str]] = None,
    anchor_age_warn_days: float = 7.0,
    q: Optional[int] = None,
    precision: Optional[int] = None,
    q_source_glob_patterns: Optional[Sequence[str]] = None,
) -> SweepEstimate:
    """Estimate wall time for a planned convergence sweep at ``(n, β, max_tours)``.

    Returns a :class:`SweepEstimate` with both naive and anchored predictions
    and a recommendation between them. The function never raises on missing
    data — degraded estimates carry explanatory strings in ``.notes``. A
    negative ``max_tours`` raises ValueError.

    Parameters
    ----------
    n, beta, max_tours
        Target sweep configuration.
    num_seeds, num_workers
        Pool shape. With ``num_seeds <= num_workers``, wall ≈ slowest seed
        (no queueing). With ``num_seeds > num_workers``, wall scales by
        ``ceil(num_seeds / num_workers)``.
    cost_table
        Optional per-tour cost table; when given, naive is per tour × ``max_tours``.
    seed_glob_patterns
        Seed JSONs to read (default: :data:`DEFAULT_SEED_GLOBS`).
    anchor_age_warn_days
        If the youngest seed in the chosen anchor is older than this
        threshold, the anchored figures are suppressed and a warning
        is added to ``notes`` containing the age
        and the most recent commit SHA touching the numerical hotspot
        files.
    q, precision
        Target modulus and MPFR precision; ``None`` blends all values.
    q_source_glob_patterns
        Same-engine seed trees to take an exact (n, β, q) cost from when
        ``seed_glob_patterns`` has none (scaled, see :func:`_source_cost_q`).
    """
    if max_tours < 0:
        raise ValueError(f"max_tours must be >= 0, got {max_tours}")
    notes: list[str] = []
    patterns = tuple(seed_glob_patterns) if seed_glob_patterns is not None else DEFAULT_SEED_GLOBS

    if num_seeds <= 0:
        # Empty pool: no work, no wall. Return a "0-wall, unknown method"
        # estimate rather than predicting a single-seed wall by accident
        # (max(1, ceil(0/w)) === 1).
        return SweepEstimate(
            n=n, beta=beta, max_tours=max_tours,
            num_seeds=num_seeds, num_workers=num_workers,
            predicted_wall_h_naive=0.0,
            predicted_wall_h_anchored=0.0,
            predicted_wall_h_p95=0.0,
            mad_h=0.0,
            anchor_used=None,
            anchor_age_days=None,
            anchor_source_paths=(),
            last_numerical_commit_sha=_last_relevant_commit_sha(),
            method_recommended="unknown",
            notes=("num_seeds is zero; pool is empty.",),
        )

    parallel_factor = max(1, math.ceil(num_seeds / max(1, num_workers)))

    # One read; cloud twins and other precisions dropped.
    rows, pool_notes = _precision_pool(
        _drop_cloud_twins(_seed_rows(_expand_globs(patterns))), beta, precision)
    notes.extend(pool_notes)
    table_given = cost_table is not None
    if cost_table is None:
        cost_table = _median_cost_table(rows, _BY_NB)

    # Naive: projected median seed wall; a caller's table: per tour × max_tours.
    if table_given:
        naive_cost, note = _lookup_cost(cost_table, n, beta)
        naive_notes = [note] if note else []
    else:
        source = None
        if q is not None and q_source_glob_patterns:
            src_all = _drop_cloud_twins(_seed_rows(_expand_globs(q_source_glob_patterns)))
            source = (_precision_pool(src_all, beta, precision)[0], src_all)
        naive_cost, naive_notes = _naive_cost(rows, n, beta, max_tours, q, source)
    notes.extend(naive_notes)

    naive_wall_h: Optional[float]
    if naive_cost is None:
        naive_wall_h = None
        notes.append(f"No per-tour cost data for (n={n}, β={beta}); naive method unavailable.")
    else:
        per_seed_seconds_naive = max_tours * (
            naive_cost.bkz_seconds_per_tour + naive_cost.sdbkz_seconds_per_tour
        )
        naive_wall_h = _seconds_to_hours(per_seed_seconds_naive) * parallel_factor

    anchor, scaled_per_seed_walls, anchor_notes = _anchored_walls(
        rows, cost_table, n, beta, max_tours, q)
    notes.extend(anchor_notes)

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
        if scaled_per_seed_walls is not None:
            anchored_wall_h = (_seconds_to_hours(statistics.median(scaled_per_seed_walls))
                               * parallel_factor)
            p95_wall_h = (_seconds_to_hours(_percentile(scaled_per_seed_walls, 95))
                          * parallel_factor)
            mad_wall_h = (_seconds_to_hours(_median_absolute_deviation(scaled_per_seed_walls))
                          * parallel_factor)

        if anchor_age_days is not None and anchor_age_days > anchor_age_warn_days:
            stamp = (
                f"Anchor age {anchor_age_days:.1f} d exceeds threshold "
                f"{anchor_age_warn_days:.1f} d; anchored figures suppressed."
            )
            if last_sha:
                stamp += f" Last commit touching numerical hotspots: {last_sha[:12]}."
            notes.append(stamp)
            # Suppress the anchored numbers so a consumer reading the
            # fields directly doesn't bypass the staleness warning. The
            # anchor metadata (used / age / paths) is preserved for
            # audit purposes.
            anchored_wall_h = None
            p95_wall_h = None
            mad_wall_h = None

    # Naive always recommended: anchored lost the backtest.
    if naive_wall_h is not None:
        method = "naive"

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


# ---------------------------------------------------------------------------
# Public API: backtest
# ---------------------------------------------------------------------------

def backtest(root: str = "results/seeds") -> list[dict]:
    """Leave-one-cell-out naive, anchored and cross-budget predictions per seed cell."""
    abs_root = root if os.path.isabs(root) else os.path.join(REPO_ROOT, root)
    rows = _drop_cloud_twins(_seed_rows(_expand_globs((os.path.join(abs_root, "**", "seed*.json"),))))

    def tree(r: _SeedRow) -> str:
        return os.path.relpath(r.path, abs_root).split(os.sep)[0]

    cells: dict[str, list[_SeedRow]] = {}
    by_tree_beta: dict[tuple, list[_SeedRow]] = {}
    by_cell_key: dict[tuple, list[_SeedRow]] = {}
    for r in rows:
        cells.setdefault(os.path.dirname(r.path), []).append(r)
        by_tree_beta.setdefault((tree(r), r.beta), []).append(r)
        by_cell_key.setdefault((tree(r), r.n, r.beta, r.q, r.precision), []).append(r)

    def total(cost: Optional[PerTourCost], mt: int) -> Optional[float]:
        if cost is None:
            return None
        return mt * (cost.bkz_seconds_per_tour + cost.sdbkz_seconds_per_tour)

    out: list[dict] = []
    for cell, cell_rows in sorted(cells.items()):
        r0 = cell_rows[0]
        mt = r0.max_tours
        if len(cell_rows) < 3 or not mt:
            continue
        ident = (r0.n, r0.q, r0.precision, mt)
        others = [r for r in by_tree_beta[(tree(r0), r0.beta)]
                  if os.path.dirname(r.path) != cell
                  and (r.n, r.q, r.precision, r.max_tours) != ident]

        same_budget, _ = _precision_pool([r for r in others if r.max_tours == mt],
                                         r0.beta, r0.precision)
        naive, _ = _naive_cost(same_budget, r0.n, r0.beta, mt, r0.q)

        anchored_s = None
        others, _ = _precision_pool(others, r0.beta, r0.precision)
        if any((r.max_tours or 0) >= 500 for r in others):
            _, walls, _ = _anchored_walls(others, _median_cost_table(others, _BY_NB),
                                          r0.n, r0.beta, mt, r0.q)
            anchored_s = statistics.median(walls) if walls else None

        other_budgets = [r for r in by_cell_key[(tree(r0), r0.n, r0.beta, r0.q, r0.precision)]
                         if r.max_tours != mt]
        cross, _ = (_naive_cost(other_budgets, r0.n, r0.beta, mt, r0.q)
                    if other_budgets else (None, []))

        walls = [r.bkz_time + r.sdbkz_time for r in cell_rows]
        out.append({
            "cell": os.path.relpath(cell, abs_root),
            "predicted_s": total(naive, mt),
            "anchored_s": anchored_s,
            "cross_budget_s": total(cross, mt),
            "median_s": statistics.median(walls),
            "max_s": max(walls),
        })
    return out


def summarise_backtest(
    cells: Sequence[dict], actual: str = "median_s", predicted: str = "predicted_s",
) -> dict:
    """Median/p90 error and >1.5x/>2x counts of ``predicted`` vs ``actual``."""
    errs = sorted(abs(math.log(c[predicted] / c[actual])) for c in cells
                  if c[predicted] is not None and c[predicted] > 0 and c[actual] > 0)
    if not errs:
        return {"cells": 0}
    return {
        "cells": len(errs),
        "median_err": math.exp(statistics.median(errs)) - 1,
        "p90_err": math.exp(_percentile(errs, 90)) - 1,
        "over_1_5x": sum(e > math.log(1.5) for e in errs),
        "over_2x": sum(e > math.log(2) for e in errs),
    }
