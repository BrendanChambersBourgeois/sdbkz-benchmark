"""Shared data loading and lattice math for the SD-BKZ benchmark analysis.

Provides:
    ln_fixed_point()         — Li-Nguyen Rankin profile
    gsa_fixed_point()        — Geometric Series Assumption Rankin profile
    load_all_seeds()         — Group per-seed JSONs by (n, beta)
    load_3x_tour_data()      — Load 3x-tour experiment seeds
    _load_convergence_files() — Load 500-tour convergence test seeds
    _group_advantages()      — Per-group advantage arrays
    _decompose_seed()        — Head/mid/tail Rankin profile decomposition

The figure modules and the diagnostics/tables modules import from here.
The leading underscore on _load_convergence_files / _group_advantages /
_decompose_seed marks them as package-internal helpers (no stable API
guarantee for external callers).
"""
import os
import json
import glob
import math
import re
from collections import defaultdict

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Lattice math (kept in sync with sweep_parallel.py / sweep_cloud.py)
# ─────────────────────────────────────────────────────────────────────────────

def ln_fixed_point(size, beta):
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


def gsa_fixed_point(size, beta):
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

def load_all_seeds(*dirs, min_seeds=1):
    """Load all seed JSONs from one or more directories and group by (n, beta).

    Args:
        *dirs: One or more directories containing n*_beta*_seed*.json files.
        min_seeds: Minimum seeds to include a group (default 1).

    Returns:
        dict: {(n, beta): [seed_data_dict, ...]} sorted by (n, beta).
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


def load_3x_tour_data(tour_dir):
    """Load 3x tour experiment seed JSONs.

    Loads only the extended-format files (n*_beta*_3x_seed*.json), which
    contain the advantage_3x / advantage_equal_tours fields used by the
    fig7 visualization. The directory may also contain old-format files
    (n*_beta*_seed*.json) from the original 10-seed pilot experiment;
    those are skipped.

    Args:
        tour_dir: Path to results/3x_tours/ directory.

    Returns:
        list of dicts, one per seed.
    """
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


def _load_convergence_files(convergence_dir):
    """Load all convergence test seed JSONs from a directory.

    Returns (bkz_arr, sd_arr, n_val, beta_val, n_seeds) where the arrays
    are shape (n_seeds, n_tours), or (None, None, None, None, 0) if no
    files match.
    """
    files = sorted(glob.glob(
        os.path.join(convergence_dir, "convergence_n*_beta*_seed*.json")
    ))
    if not files:
        return None, None, None, None, 0

    bkz_trajs = []
    sd_trajs = []
    n_val = beta_val = None
    for f in files:
        d = json.load(open(f))
        bkz_trajs.append(d["bkz_dln_per_tour"])
        sd_trajs.append(d["sdbkz_dln_per_tour"])
        if n_val is None:
            n_val, beta_val = d["n"], d["beta"]

    return (np.array(bkz_trajs), np.array(sd_trajs),
            n_val, beta_val, len(bkz_trajs))


def _group_advantages(groups):
    """Extract advantages as numpy arrays per group."""
    return {
        k: np.array([d["advantage"] for d in v])
        for k, v in groups.items()
    }


def _per_position_improvement(seed_data):
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


def _per_position_group_stats(seeds):
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


def _decompose_seed(seed_data):
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
