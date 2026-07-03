"""Shared data loading and lattice math for the SD-BKZ benchmark analysis.

Provides:
    ln_fixed_point()         — Li-Nguyen Rankin profile
    gsa_fixed_point()        — Geometric Series Assumption Rankin profile
    load_all_seeds()         — Group per-seed JSONs by (n, beta); dual-mode
                                (legacy globber for positional dirs, v1.3
                                manifest query for campaign/n/beta/... kwargs)
    load_3x_tour_data()      — Load 3x-tour experiment seeds
    _load_convergence_files() — Load 500-tour convergence test seeds
    _group_advantages()      — Per-group advantage arrays
    _decompose_seed()        — Head/mid/tail Rankin profile decomposition

The figure modules and the diagnostics/tables modules import from here.
The leading underscore on _load_convergence_files / _group_advantages /
_decompose_seed marks them as package-internal helpers (no stable API
guarantee for external callers).
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import warnings
from collections import defaultdict
from typing import Any

import numpy as np

SeedDict = dict[str, Any]
GroupKey = tuple[int, int]
Groups = dict[GroupKey, list[SeedDict]]

DEFAULT_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "results", "seed_manifest.json",
)
_MANIFEST_CACHE: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Lattice math (kept in sync with sweep_parallel.py / sweep_cloud.py)
# ─────────────────────────────────────────────────────────────────────────────

def ln_fixed_point(size: int, beta: int) -> list[float]:
    """Compute the Li-Nguyen fixed-point Rankin profile.

    Args:
        size: Number of active Gram-Schmidt vectors (n+1 for LWE-Kannan).
        beta: BKZ block size.

    Returns:
        List of floats: the fixed-point Rankin profile values.
    """
    exp = (size - 1) / (2 * (beta - 1)) + (beta * (beta - 2)) / (
        2 * size * (beta - 1)
    )
    log_v_beta = math.log(beta / (2 * math.pi * math.e)) * exp
    log_delta = math.log(beta / (2 * math.pi * math.e)) / (2 * beta - 2)
    total_vol = sum((size + 1 - 2 * i) * log_delta for i in range(1, size + 1))
    profile, cum = [], 0.0
    for i in range(1, size + 1):
        cum += (size + 1 - 2 * i) * log_delta
        profile.append(cum - (i / size) * total_vol)
    return [p + log_v_beta for p in profile]


def gsa_fixed_point(size: int, beta: int) -> list[float]:
    """Compute the GSA (Geometric Series Assumption) Rankin profile.

    GSA uses log_delta = log(β/(2πe)) / (2β), differing from Li-Nguyen
    which uses 1/(2β-2). Same structure, slightly different slope.

    Args:
        size: Number of active Gram-Schmidt vectors.
        beta: BKZ block size.

    Returns:
        List of floats: the GSA Rankin profile values.
    """
    log_delta = math.log(beta / (2 * math.pi * math.e)) / (2 * beta)
    total_vol = sum((size + 1 - 2 * i) * log_delta for i in range(1, size + 1))
    profile, cum = [], 0.0
    for i in range(1, size + 1):
        cum += (size + 1 - 2 * i) * log_delta
        profile.append(cum - (i / size) * total_vol)
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_manifest(manifest_path: str) -> dict:
    """Read + cache the seed manifest. Cache keyed on (path, mtime)."""
    key = (os.path.abspath(manifest_path), os.path.getmtime(manifest_path))
    cached = _MANIFEST_CACHE.get(key)
    if cached is not None:
        return cached
    with open(manifest_path) as f:
        manifest = json.load(f)
    _MANIFEST_CACHE.clear()
    _MANIFEST_CACHE[key] = manifest
    return manifest


def _manifest_entry_matches(
    entry: dict,
    campaign: str | None,
    n: int | None, beta: int | None, q: int | None,
    precision: int | None, max_tours: int | None,
    include_fat: bool, include_unverified: bool,
    fplll_version: str | None,
) -> bool:
    if campaign is not None and entry["campaign"] != campaign:
        return False
    if n is not None and entry["n"] != n:
        return False
    if beta is not None and entry["beta"] != beta:
        return False
    if q is not None and entry["q"] != q:
        return False
    if precision is not None and entry.get("precision") != precision:
        return False
    if max_tours is not None and entry.get("max_tours") != max_tours:
        return False
    if fplll_version is not None and entry.get("fplll_version") != fplll_version:
        return False
    tags = set(entry.get("tags", []))
    if not include_fat and "fat" in tags:
        return False
    if not include_unverified and not entry.get("verified", False):
        return False
    return True


def _manifest_load_groups(
    *,
    campaign: str | None = "main",
    n: int | None = None, beta: int | None = None, q: int | None = 97,
    precision: int | None = None, max_tours: int | None = None,
    fplll_version: str | None = None,
    include_fat: bool = False,
    include_unverified: bool = False,
    min_seeds: int = 1,
    load_json: bool = True,
    manifest_path: str | None = None,
) -> Groups:
    """v1.3 manifest-driven loader. Dedup by (campaign, n, β, seed);
    within each key, prefer the non-cloud copy so that paper-era
    figures remain byte-identical to their legacy globber output
    (raw/ wins over cloud/ for the 205 §3.7 dual-copy pairs).
    """
    manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"seed_manifest.json not found at {manifest_path}. "
            "Run scripts/build_seed_manifest.py first."
        )
    manifest = _load_manifest(manifest_path)

    by_key: dict = {}
    for entry in manifest["seeds"]:
        if not _manifest_entry_matches(
            entry, campaign, n, beta, q,
            precision, max_tours,
            include_fat, include_unverified, fplll_version,
        ):
            continue
        is_fat = "fat" in entry.get("tags", [])
        # When include_fat=True we keep fat alongside lean (same n, β,
        # seed); the fat flag becomes part of the dedup key so the two
        # don't collide.
        key = (entry["n"], entry["beta"], entry["seed"], is_fat)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = entry
        else:
            # Prefer non-cloud copy (matches legacy raw/ > cloud/ order).
            prev_cloud = "cloud" in prev.get("tags", [])
            new_cloud = "cloud" in entry.get("tags", [])
            if prev_cloud and not new_cloud:
                by_key[key] = entry

    groups: dict = defaultdict(list)
    repo_root = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    for entry in by_key.values():
        if not load_json:
            groups[(entry["n"], entry["beta"])].append(dict(entry))
            continue
        # Resolve the manifest's relative `path` against the repo root
        # (manifest stores paths relative to repo root, e.g.
        # results/seeds/main/q97/n050_beta30/seed0001.json).
        abs_path = os.path.join(repo_root, entry["path"])
        try:
            with open(abs_path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        # Inject manifest-side fields that callers sometimes need
        # (provenance tags, canonical relative path). Prefixed with
        # `_manifest_` to avoid colliding with the JSON schema.
        data["_manifest_tags"] = list(entry.get("tags", []))
        data["_manifest_path"] = entry["path"]
        data["_manifest_campaign"] = entry["campaign"]
        groups[(entry["n"], entry["beta"])].append(data)

    filtered = {
        k: sorted(v, key=lambda d: d["seed"])
        for k, v in sorted(groups.items())
        if len(v) >= min_seeds
    }

    total = sum(len(v) for v in filtered.values())
    print(f"Loaded {total} seeds across {len(filtered)} groups "
          f"from seed_manifest.json "
          f"(campaign={campaign}, q={q}"
          + (f", n={n}" if n is not None else "")
          + (f", β={beta}" if beta is not None else "")
          + ")")
    return filtered


def load_all_seeds(*args: Any, **kwargs: Any) -> Groups:
    """Load seeds grouped by (n, beta). Dual-mode.

    Legacy (pre-v1.3) — positional directory args::

        groups = load_all_seeds("/some/external/dir", min_seeds=1)

    Globs every `n*_beta*_seed*.json` under each dir, dedup by basename,
    skips non-q=97 files. Still supported for off-tree datasets. The
    pre-v1.3 `results/raw/` + `results/cloud/` directories were deleted
    at v2.0.0 alongside the back-compat symlinks; pass explicit paths
    only for one-off external seed sets.

    v1.3 manifest mode — keyword args::

        groups = load_all_seeds(campaign="main", q=97)
        groups = load_all_seeds(campaign="cliff500")
        groups = load_all_seeds(campaign="q3329", precision=1000, max_tours=70)

    Queries `results/seed_manifest.json` directly. Dedups by (n, β,
    seed) within the selected campaign, preferring the non-cloud copy
    so that paper-era figures stay byte-identical to the legacy
    globber output.

    Returns:
        dict: {(n, beta): [seed_data_dict, ...]} sorted by (n, beta),
        each value sorted by seed.
    """
    # Legacy routing: any positional string that looks like a path →
    # run the globber. This keeps every pre-v1.3 caller working
    # unchanged through the symlink layer.
    if args and all(isinstance(a, str) for a in args):
        return _legacy_load_all_seeds(*args, **kwargs)
    return _manifest_load_groups(*args, **kwargs)


def _legacy_load_all_seeds(*dirs: str, min_seeds: int = 1) -> Groups:
    """Legacy globber kept verbatim so pre-v1.3 callers stay
    byte-identical through the back-compat symlinks at old paths.
    New code should pass `campaign=...` kwargs to the public
    `load_all_seeds()` instead.
    """
    groups = defaultdict(list)
    seen = set()
    n_json_errors = 0
    n_key_errors = 0
    n_non_q97 = 0
    n_incomplete = 0

    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for fp in sorted(glob.glob(os.path.join(d, "n*_beta*_seed*.json"))):
            fname = os.path.basename(fp)
            # Skip filenames with an explicit non-97 q tag. Negative
            # lookahead so `_q97_seed` (if ever standardised) is NOT
            # dropped here — the data["q"] check below is still the
            # authoritative gate. The filter prevents q=3329 verification
            # seeds from contaminating the main q=97 aggregate when both
            # directories are scanned together.
            if re.search(r"_q(?!97_)\d+_seed", fname):
                n_non_q97 += 1
                continue
            if fname in seen:
                continue
            seen.add(fname)
            try:
                with open(fp) as f:
                    data = json.load(f)
                if data.get("status") != "completed":
                    n_incomplete += 1
                    continue
                # Belt-and-braces: skip any seed whose q field is not 97.
                if data.get("q", 97) != 97:
                    n_non_q97 += 1
                    continue
                groups[(data["n"], data["beta"])].append(data)
            except json.JSONDecodeError:
                n_json_errors += 1
                continue
            except KeyError:
                n_key_errors += 1
                continue

    # Filter by min_seeds and sort
    filtered = {
        k: sorted(v, key=lambda d: d["seed"])
        for k, v in sorted(groups.items())
        if len(v) >= min_seeds
    }

    total = sum(len(v) for v in filtered.values())
    skipped_bits = []
    if n_non_q97:      skipped_bits.append(f"{n_non_q97} non-q97")
    if n_incomplete:   skipped_bits.append(f"{n_incomplete} incomplete")
    if n_json_errors:  skipped_bits.append(f"{n_json_errors} json errors")
    if n_key_errors:   skipped_bits.append(f"{n_key_errors} missing keys")
    skipped_suffix = f" (skipped: {', '.join(skipped_bits)})" if skipped_bits else ""
    print(f"Loaded {total} seeds across {len(filtered)} groups "
          f"from {len(dirs)} director{'y' if len(dirs) == 1 else 'ies'}"
          f"{skipped_suffix}")
    return filtered


def load_3x_tour_data(
    tour_dir: str | None = None,
    manifest_path: str | None = None,
) -> list[SeedDict]:
    """Load 3x tour experiment seed JSONs.

    Prefers the v1.3 seed_manifest.json (campaign="tours3x") when
    available; falls back to the legacy glob of `tour_dir` for
    callers that still pass a directory. Either mode returns a
    flat list of seed dicts loaded from disk.
    """
    if tour_dir is None or manifest_path:
        manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
        if os.path.exists(manifest_path):
            manifest = _load_manifest(manifest_path)
            repo_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            seeds = []
            entries = [
                e for e in manifest["seeds"]
                if e["campaign"] == "tours3x" and "3x" in e.get("tags", [])
            ]
            entries.sort(key=lambda e: (e["n"], e["beta"], e["seed"]))
            for entry in entries:
                abs_path = os.path.join(repo_root, entry["path"])
                try:
                    with open(abs_path) as f:
                        seeds.append(json.load(f))
                except (json.JSONDecodeError, KeyError, OSError):
                    continue
            print(f"Loaded {len(seeds)} seeds from 3x tour experiment "
                  f"(manifest campaign=tours3x)")
            return seeds

    if not os.path.isdir(tour_dir):
        print(f"3x tour directory not found: {tour_dir}")
        return []
    seeds = []
    for fp in sorted(glob.glob(os.path.join(tour_dir, "n*_beta*_3x_seed*.json"))):
        try:
            with open(fp) as f:
                seeds.append(json.load(f))
        except (json.JSONDecodeError, KeyError):
            continue
    print(f"Loaded {len(seeds)} seeds from 3x tour experiment")
    return seeds


def _load_convergence_files(
    convergence_dir: str | None = None,
    *,
    n: int | None = None, beta: int | None = None,
    max_tours: int | None = None,
    manifest_path: str | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None, int | None, int | None, int]:
    """Load all convergence test seed JSONs.

    Prefers the v1.3 seed_manifest.json (campaign="convergence"); the
    caller may optionally narrow by (n, beta, max_tours) to pick a
    specific convergence-test variant (e.g., n=90 β=30 mt=500 vs
    n=140 β=30 mt=500). Falls back to globbing `convergence_dir` if
    that positional path is given and the manifest does not yield
    a match (preserves pre-v1.3 callers through back-compat symlinks).

    Returns (bkz_arr, sd_arr, n_val, beta_val, n_seeds) where the
    arrays are shape (n_seeds, n_tours), or (None, None, None, None,
    0) if no files match.
    """
    bkz_trajs = []
    sd_trajs = []
    n_val = beta_val = None

    manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
    if os.path.exists(manifest_path):
        manifest = _load_manifest(manifest_path)
        repo_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        entries = [
            e for e in manifest["seeds"]
            if e["campaign"] == "convergence"
        ]
        if n is not None:
            entries = [e for e in entries if e["n"] == n]
        if beta is not None:
            entries = [e for e in entries if e["beta"] == beta]
        if max_tours is not None:
            entries = [e for e in entries if e.get("max_tours") == max_tours]
        # If the caller passed convergence_dir, filter entries whose
        # path lives under that dir — keeps the legacy `convergence/`
        # vs `convergence_test/` disambiguation working.
        if convergence_dir is not None:
            cdir_abs = os.path.realpath(convergence_dir)
            filt = []
            for e in entries:
                abs_path = os.path.realpath(os.path.join(repo_root, e["path"]))
                legacy_abs = os.path.realpath(os.path.join(
                    convergence_dir,
                    f"convergence_n{e['n']}_beta{e['beta']}_seed{e['seed']}.json",
                ))
                if os.path.exists(legacy_abs) and (
                    os.path.samefile(legacy_abs, abs_path)
                    if os.path.exists(abs_path) else False
                ):
                    filt.append(e)
                elif cdir_abs in abs_path:
                    filt.append(e)
            entries = filt
        entries.sort(key=lambda e: (e["n"], e["beta"], e["seed"]))
        for entry in entries:
            abs_path = os.path.join(repo_root, entry["path"])
            try:
                with open(abs_path) as _fh:
                    d = json.load(_fh)
            except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
                continue
            try:
                bkz_trajs.append(d["bkz_dln_per_tour"])
                sd_trajs.append(d["sdbkz_dln_per_tour"])
            except KeyError:
                continue
            if n_val is None:
                n_val, beta_val = d["n"], d["beta"]
        if bkz_trajs:
            return (np.array(bkz_trajs), np.array(sd_trajs),
                    n_val, beta_val, len(bkz_trajs))

    if convergence_dir is None:
        return None, None, None, None, 0
    files = sorted(glob.glob(
        os.path.join(convergence_dir, "convergence_n*_beta*_seed*.json")
    ))
    if not files:
        return None, None, None, None, 0

    for f in files:
        try:
            with open(f) as _fh:
                d = json.load(_fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        try:
            bkz_trajs.append(d["bkz_dln_per_tour"])
            sd_trajs.append(d["sdbkz_dln_per_tour"])
        except KeyError:
            continue
        if n_val is None:
            n_val, beta_val = d["n"], d["beta"]

    return (np.array(bkz_trajs), np.array(sd_trajs),
            n_val, beta_val, len(bkz_trajs))


def _seed_has_sentinel(seed: SeedDict) -> bool:
    """True if either variant's stored GS profile carries the -345 clamp
    sentinel (gs_lognorm < -300). Such a seed's dln/advantage/rankin were
    computed off a catastrophically-cancelled double-precision GSO and are
    untrustworthy, so they must not enter an aggregate (deep audit 2026-07-04
    finding 2). The recovery verdict is unaffected -- only the GSO metrics are."""
    for variant in ("bkz", "sdbkz"):
        gs = seed.get(f"gs_lognorms_{variant}") or []
        if any(x is not None and x < -300.0 for x in gs):
            return True
    return False


def _group_advantages(groups: Groups) -> dict[GroupKey, np.ndarray]:
    """Extract advantages as numpy arrays per group, dropping clamp-poisoned
    seeds (their advantage = bkz_final_dln - sdbkz_final_dln is corrupt)."""
    out: dict[GroupKey, np.ndarray] = {}
    dropped = 0
    for k, v in groups.items():
        clean = [d["advantage"] for d in v if not _seed_has_sentinel(d)]
        dropped += len(v) - len(clean)
        out[k] = np.array(clean)
    if dropped:
        warnings.warn(
            f"_group_advantages: dropped {dropped} clamp-poisoned seed(s) "
            f"(gs_lognorm < -300) from advantage aggregates",
            stacklevel=2,
        )
    return out


def _per_position_improvement(seed_data: SeedDict) -> np.ndarray | None:
    """Per-position |BKZ−R*| − |SDBKZ−R*| for a single seed.

    Returns:
        numpy array of length n+1, or None if data missing.
    """
    rp_bkz = seed_data.get("rankin_profile_bkz")
    rp_sd = seed_data.get("rankin_profile_sdbkz")
    if rp_bkz is None or rp_sd is None:
        return None

    n, beta = seed_data["n"], seed_data["beta"]
    size = len(rp_bkz)
    if size != len(rp_sd):
        return None

    fp = ln_fixed_point(n + 1, beta)
    if len(fp) != size:
        return None

    fp_arr = np.array(fp)
    return np.abs(np.array(rp_bkz) - fp_arr) - np.abs(np.array(rp_sd) - fp_arr)


def _per_position_group_stats(
    seeds: list[SeedDict],
) -> tuple[np.ndarray | None, np.ndarray | None, int]:
    """Aggregate per-position improvement across seeds.

    Returns:
        (means, stds, n_used) or (None, None, 0) if no valid seeds.
    """
    arrays = []
    for s in seeds:
        imp = _per_position_improvement(s)
        if imp is not None:
            arrays.append(imp)
    if not arrays:
        return None, None, 0
    stacked = np.stack(arrays)
    return stacked.mean(axis=0), stacked.std(axis=0), len(arrays)


def _decompose_seed(
    seed_data: SeedDict,
) -> tuple[float, float, float] | None:
    """Compute head/mid/tail improvement for a single seed.

    Used by fig_spatial_decomposition and table_spatial.

    Returns:
        (head_mean, mid_mean, tail_mean) or None if data missing.
    """
    rp_bkz = seed_data.get("rankin_profile_bkz")
    rp_sd = seed_data.get("rankin_profile_sdbkz")
    if rp_bkz is None or rp_sd is None:
        return None

    n, beta = seed_data["n"], seed_data["beta"]
    size = len(rp_bkz)
    if size != len(rp_sd):
        return None

    fp = ln_fixed_point(n + 1, beta)
    if len(fp) != size:
        return None

    fp_arr = np.array(fp)
    bkz_dist = np.abs(np.array(rp_bkz) - fp_arr)
    sd_dist = np.abs(np.array(rp_sd) - fp_arr)
    improvement = bkz_dist - sd_dist  # positive = SD-BKZ closer

    # np.array_split handles non-multiple-of-3 sizes by distributing the
    # remainder across the earlier segments so all three are within one
    # element of equal. Previously (size // 3) left the remainder in the
    # tail, slightly biasing the tail share upward in Table 4 at non-
    # multiple-of-3 dimensions (e.g. n=100 → size=101, old tail=35 vs 33/33).
    head, mid, tail = np.array_split(improvement, 3)
    return (float(np.mean(head)), float(np.mean(mid)), float(np.mean(tail)))
