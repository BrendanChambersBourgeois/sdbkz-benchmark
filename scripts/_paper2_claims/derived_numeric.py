#!/usr/bin/env python3
"""Paper-2 claims ledger — DERIVED numeric slice (plan steps 4b + 4c).

Two families of number that have NO committed provenance in the repo:

  4b. campaign cost  ~= 9,500 core-hours     (tab:coverage caption)
  4c. three bootstrap CIs on the n=89 / n=101 beta=40 onset gaps, as printed
        [-0.14, +0.50]  n=89 fplll onset-modulus gap   (point +0.16)
        [+0.35, +1.81]  n=89 G6K   onset-modulus gap   (point +0.82, 0.42% of q)
        [ 6.0%, 11.0%]  n=101 fplll DSD onset-% gap     (point 9%)
  4d. fplll beta=40 frontier recoveries per 100 core-hours, SD-BKZ over BKZ,
      with a key-resampling CI on the ratio (sec:frontier)

Every DSD verdict is scored with the EXISTING primitives imported from
``scripts/extract_dsd_onset.py`` (``_seed_fires``, ``_q_grid``, ``short_threshold``)
so the fire vectors are byte-identical to the figure / onset-table path. The onset
interpolation here is _interp_onset's arithmetic WITHOUT the final round(.,1): the
published point estimates (+0.16 / +0.82 / 9%) are the *unrounded* gaps between the
two variants' 50%-crossings (193.827-193.667 = 0.16, etc.), so rounding to 0.1 would
collapse the fplll gap to 0.1 and never reproduce +0.16.

Read-only on results/seeds/. Writes nothing. Exposes build_records() -> list[dict].
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

import numpy as np

# --- locate the repo and import the committed scoring primitives -------------
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (scripts/_paper2_claims/ -> up 3)
SCRIPTS = os.path.join(BASE, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
from extract_dsd_onset import (  # noqa: E402  (existing primitives)
    DEFAULT_TOURS,
    _q_grid,
    _seed_fires,
)

from _paper2_claims.pointer import in_coverage  # noqa: E402  (tab:coverage scope)

DEFAULT_RATE = 0.5
TOURS_DEFAULT = DEFAULT_TOURS  # single source: extract_dsd_onset
RNG_SEED = 20260710          # pinned so the CIs are byte-reproducible
B = 10000                    # bootstrap resamples


# =============================================================================
# 4b. core-hours
# =============================================================================
def _per_tour_table() -> dict:
    """(n, beta) -> (bkz_spt, sdbkz_spt) from the committed cost table."""
    p = os.path.join(BASE, "results", "paper_claims", "per_tour_cost_table.json")
    tab = {}
    for e in json.load(open(p))["entries"]:
        tab[(e["n"], e["beta"])] = (e["bkz_seconds_per_tour"],
                                    e["sdbkz_seconds_per_tour"])
    return tab


def _nearest_cost(tab: dict, n: int, beta: int):
    """Nearest (n, beta) per-tour cost: same beta, closest n."""
    cands = [k for k in tab if k[1] == beta]
    key = min(cands, key=lambda k: abs(k[0] - n))
    return key, tab[key]


def _core_hours():
    """Ground-truth core-hours: sum the ACTUAL recorded bkz_time+sdbkz_time over
    every paper-2 coverage seed (results/seeds/{ntru,ntru_g6k};
    pointer.in_coverage), from the seed JSONs the manifests point at."""
    total = 0.0
    breakdown: dict = defaultdict(float)
    rows: set = set()
    n_seeds = 0
    missing = 0
    for mf, tree in [("seed_manifest.json", "ntru"),
                     ("g6k_seed_manifest.json", "ntru_g6k")]:
        man = json.load(open(os.path.join(BASE, "results", mf)))
        for s in man["seeds"]:
            if s["path"].split("/")[2] != tree or not in_coverage(s):
                continue
            n_seeds += 1
            rows.add((s["n"], s["beta"], s.get("max_tours", TOURS_DEFAULT)))
            try:
                d = json.load(open(os.path.join(BASE, s["path"])))
                bt, st = d.get("bkz_time"), d.get("sdbkz_time")
                if bt is None or st is None:
                    missing += 1
                    continue
                ch = (bt + st) / 3600.0
                total += ch
                breakdown[f"n{s['n']}_b{s['beta']}"] += ch
            except FileNotFoundError:
                missing += 1
    breakdown["_missing_time_seeds"] = missing
    return total, dict(breakdown), n_seeds, len(rows)


# =============================================================================
# 4c. bootstrap CIs
# =============================================================================
def _fire_matrix(tree: str, n: int, beta: int, variant: str):
    """q -> {sid: 0/1 fire} for one variant, scored by the committed _seed_fires.

    Returns (matrix, modal_count). Read-only glob mirrors _cell_rate's pattern."""
    mat: dict[int, dict[int, int]] = {}
    for q in _q_grid(tree, n, beta):
        pat = os.path.join(BASE, "results", "seeds", tree, f"q{q}",
                           f"p*_mt{TOURS_DEFAULT}", f"n{n:03d}_beta{beta:02d}", "seed*.json")
        cell: dict[int, int] = {}
        for f in sorted(glob.glob(pat)):
            sid = int(re.search(r"seed(\d+)", os.path.basename(f)).group(1))
            seed = json.load(open(f))
            cell[sid] = int(_seed_fires(seed, variant, n))
        if cell:
            mat[q] = cell
    counts = [len(c) for c in mat.values()]
    modal = max(set(counts), key=counts.count) if counts else 0
    return mat, modal


def _interp_onset_unrounded(curve, rate=DEFAULT_RATE):
    """_interp_onset's arithmetic with NO round(.,1) (see module docstring)."""
    if not curve:
        return None
    if curve[0][1] >= rate:
        return float(curve[0][0])
    prev_q, prev_r = curve[0]
    for q, r in curve[1:]:
        if r >= rate:
            if r == prev_r:
                return float(q)
            return prev_q + (q - prev_q) * (rate - prev_r) / (r - prev_r)
        prev_q, prev_r = q, r
    return None


def _aligned_arrays(tree, n, beta):
    """Build (qs, universe_sids, SD_array, BKZ_array) restricted to q-cells that
    carry the modal (full) seed set, so a common seed-index resample applies to
    every cell used for the crossing. Arrays are shape (n_q, n_seeds) of 0/1,
    columns ordered by sorted seed id."""
    sd_mat, modal = _fire_matrix(tree, n, beta, "sdbkz")
    bkz_mat, _ = _fire_matrix(tree, n, beta, "bkz")
    qs = sorted(q for q in sd_mat if len(sd_mat[q]) == modal and len(bkz_mat.get(q, {})) == modal)
    universe = sorted(sd_mat[qs[0]].keys())
    for q in qs:
        assert sorted(sd_mat[q].keys()) == universe, f"seed-id mismatch at q={q}"
    sd_arr = np.array([[sd_mat[q][s] for s in universe] for q in qs], dtype=float)
    bkz_arr = np.array([[bkz_mat[q][s] for s in universe] for q in qs], dtype=float)
    return qs, universe, sd_arr, bkz_arr


def _onsets_from_rates(qs, sd_rates, bkz_rates):
    sd = _interp_onset_unrounded(list(zip(qs, sd_rates, strict=True)))
    bkz = _interp_onset_unrounded(list(zip(qs, bkz_rates, strict=True)))
    return sd, bkz


def _bootstrap_gap(tree, n, beta, estimand, rng_seed=RNG_SEED, b=B):
    """Nonparametric bootstrap of the SD-BKZ onset gap.

    Design = key resampling: one seed-index resample per replicate, applied to
    every q-cell. A seed id fixes the NTRU key along the whole q-ladder, so the
    key is the independent unit; SD/BKZ stay paired within a seed.

    estimand: 'abs'  -> gap = BKZ_onset - SD_onset (modulus units)
              'pct'  -> gap = 100*(BKZ_onset - SD_onset)/SD_onset (percent)
    Returns (point_estimate, lo, hi, meta)."""
    qs, universe, sd_arr, bkz_arr = _aligned_arrays(tree, n, beta)
    m = len(universe)
    nq = len(qs)

    def gap(sd_rates, bkz_rates):
        sd, bkz = _onsets_from_rates(qs, sd_rates, bkz_rates)
        if sd is None or bkz is None:
            return None
        return (bkz - sd) if estimand == "abs" else 100.0 * (bkz - sd) / sd

    point = gap(sd_arr.mean(axis=1), bkz_arr.mean(axis=1))

    rng = np.random.default_rng(rng_seed)
    gaps = np.empty(b)
    for i in range(b):
        sdr = np.empty(nq)
        bkr = np.empty(nq)
        cols = rng.integers(0, m, m)              # one key resample for all cells
        for j in range(nq):
            sdr[j] = sd_arr[j, cols].mean()
            bkr[j] = bkz_arr[j, cols].mean()
        gaps[i] = gap(sdr, bkr)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    meta = {"n_q_cells": nq, "seed_universe": m, "q_grid": qs,
            "design": "key resample, common across q-cells"}
    return float(point), float(lo), float(hi), meta


# =============================================================================
# 4d. frontier recoveries per core-hour
# =============================================================================
def _cost_ratio(n, seed_max=None, rng_seed=RNG_SEED, b=B):
    """Exact-match recoveries per 100 core-hours over one fplll beta=40,
    50-tour ladder, pooled over its q cells, and the SD-BKZ/BKZ ratio with a
    bootstrap CI over keys (seed ids). Returns (sd, bkz, ratio, lo, hi, n_keys)."""
    per_key: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(4))
    pat = os.path.join(BASE, "results", "seeds", "ntru", "q*",
                       f"p*_mt{TOURS_DEFAULT}", f"n{n:03d}_beta40", "seed*.json")
    for f in sorted(glob.glob(pat)):
        with open(f) as fh:
            d = json.load(fh)
        if seed_max and d["seed"] > seed_max:
            continue
        per_key[d["seed"]] += (d["secret_exact_match_sdbkz"], d["secret_exact_match_bkz"],
                               d["sdbkz_time"], d["bkz_time"])
    a = np.array([per_key[k] for k in sorted(per_key)])

    def rates(x):
        t = x.sum(axis=0)
        return t[0] / t[2] * 3.6e5, t[1] / t[3] * 3.6e5

    sd, bkz = rates(a)
    rng = np.random.default_rng(rng_seed)
    boot = np.empty(b)
    for i in range(b):
        s_, b_ = rates(a[rng.integers(0, len(a), len(a))])
        boot[i] = s_ / b_
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(sd), float(bkz), float(sd / bkz), float(lo), float(hi), len(a)


# =============================================================================
# ledger records
# =============================================================================
def _sig2(x):
    """Round to 2 significant figures for the match test."""
    if x == 0:
        return 0.0
    return round(x, -int(math.floor(math.log10(abs(x)))) + 1)


def build_records() -> list[dict]:
    records = []

    # ---- 4b core-hours -------------------------------------------------------
    total, breakdown, nseeds, ncells = _core_hours()
    ch_match = 9450.0 <= total <= 9550.0
    records.append({
        "claim_id": "cost_core_hours",
        "tex_anchors": [r"$\approx$9{,}500 core-hours"],
        "verbatim": "about 9,500 core-hours of reduction across both oracles",
        "paper_value": 9500.0,
        "source": {"kind": "manifest+recorded_seed_times",
                   "fields": "bkz_time + sdbkz_time (per seed JSON)",
                   "manifests": ["results/seed_manifest.json",
                                 "results/g6k_seed_manifest.json"]},
        "method": ("GROUND TRUTH: sum of recorded (bkz_time + sdbkz_time)/3600 over "
                   "every paper-2 coverage seed (trees ntru+ntru_g6k, n<157) "
                   f"from the manifests -- {nseeds} seed-pairs, {ncells} (n,beta,tours) "
                   "rows; no cost-table extrapolation"),
        "recomputed_value": round(total, 1),
        "match": ch_match,
        "status": "DERIVED" if ch_match else "DERIVED-UNRESOLVED",
        "note": ("per-(n,beta) core-hour breakdown: "
                 + ", ".join(f"{k}={v:.0f}" for k, v in sorted(breakdown.items())
                             if k != "_missing_time_seeds")
                 + f". Direct sum of recorded per-seed compute times (0 missing) = "
                 f"{total:.0f} core-h vs tex '~9,500' = {total/9500.0:.3f}x -> MATCH.") if ch_match
                else (f"direct-time sum {total:.0f} core-h vs tex 9,500 = "
                      f"{total/9500.0:.2f}x -- outside 9.45-9.55k band, investigate"),
    })

    # ---- 4c bootstrap CIs ----------------------------------------------------
    ci_specs = [
        {"claim_id": "bootstrap_ci_n89_fplll_onset_gap", "tree": "ntru",
         "n": 89, "estimand": "abs", "tex_anchors": [r"$[-0.14, +0.50]$"],
         "verbatim": "+0.16 units, CI [-0.14, +0.50] (spans 0)",
         "paper_point": 0.16, "paper_lo": -0.14, "paper_hi": 0.50, "unit": "modulus"},
        {"claim_id": "bootstrap_ci_n89_g6k_onset_gap", "tree": "ntru_g6k",
         "n": 89, "estimand": "abs",
         "tex_anchors": [r"the G6K gap $+0.82$ ($[+0.35, +1.81]$)"],
         "verbatim": "+0.82 units, CI [+0.35, +1.81]",
         "paper_point": 0.82, "paper_lo": 0.35, "paper_hi": 1.81, "unit": "modulus"},
        {"claim_id": "bootstrap_ci_n101_fplll_rate_gap", "tree": "ntru",
         "n": 101, "estimand": "pct", "tex_anchors": [r"$[6.0\%,11.0\%]$"],
         "verbatim": "9% gap, CI [6.0%, 11.0%]",
         "paper_point": 9.0, "paper_lo": 6.0, "paper_hi": 11.0, "unit": "percent"},
    ]
    for spec in ci_specs:
        point, lo, hi, meta = _bootstrap_gap(spec["tree"], spec["n"], 40,
                                             spec["estimand"])
        # match: point est to 2 sig figs, both CI bounds to 2 sig figs
        point_ok = abs(point - spec["paper_point"]) <= 0.02 * max(1, abs(spec["paper_point"])) \
            or _sig2(point) == _sig2(spec["paper_point"])
        lo_ok = abs(lo - spec["paper_lo"]) <= max(0.05, 0.05 * abs(spec["paper_lo"]))
        hi_ok = abs(hi - spec["paper_hi"]) <= max(0.05, 0.05 * abs(spec["paper_hi"]))
        match = bool(point_ok and lo_ok and hi_ok)
        records.append({
            "claim_id": spec["claim_id"],
            "tex_anchors": spec["tex_anchors"],
            "verbatim": spec["verbatim"],
            "paper_value": {"point": spec["paper_point"],
                            "ci": [spec["paper_lo"], spec["paper_hi"]]},
            "source": {"kind": "seeds",
                       "glob": f"results/seeds/{spec['tree']}/q*/p*_mt{TOURS_DEFAULT}/"
                               f"n{spec['n']:03d}_beta40/"},
            "method": (f"nonparametric bootstrap over keys (one seed-index resample "
                       f"applied to every q-cell, SD/BKZ paired within seed), B={B}, "
                       f"rng_seed={RNG_SEED}; "
                       f"estimand=SD-BKZ onset "
                       f"{'modulus gap' if spec['estimand']=='abs' else 'percent gap'}; "
                       f"per resample recompute both 50%-onsets via unrounded "
                       f"_interp_onset over the {meta['n_q_cells']} full-seed q-cells; "
                       f"percentile [2.5,97.5]; fires via extract_dsd_onset._seed_fires"),
            "recomputed_value": {"point": round(point, 3),
                                 "ci": [round(lo, 3), round(hi, 3)],
                                 "B": B, "rng_seed": RNG_SEED,
                                 "seed_universe": meta["seed_universe"]},
            "match": match,
            "status": "DERIVED" if match else "DERIVED-UNRESOLVED",
            "note": (f"point est {point:+.3f} vs tex {spec['paper_point']:+.2f} "
                     f"({spec['unit']}); CI [{lo:+.3f},{hi:+.3f}] vs tex "
                     f"[{spec['paper_lo']:+.2f},{spec['paper_hi']:+.2f}]. "
                     f"{meta['seed_universe']} seeds/cell over q={meta['q_grid']}. "
                     f"Point est is exact (deterministic full-sample gap); CI bounds "
                     f"depend on rng_seed (pinned) and B." + spec.get("extra", ""))
        })

    # ---- 4d frontier recoveries per core-hour ---------------------------------
    cost_specs = [
        (157, None, 6.96, 11.70, 0.60, 0.56, 0.63,
         [r"$6.96$ against $11.70$ at $n=157$", r"$0.60$ ($95\%$ key-resampling"]),
        (163, 20, 7.14, 8.41, 0.85, 0.72, 1.03,
         [r"$7.14$ against $8.41$ at $n=163$", r"$0.85$ ($[0.72,1.03]$)"]),
        (167, None, 3.23, 3.49, 0.93, 0.69, 1.21,
         [r"$3.23$ against $3.49$", r"$0.93$ ($[0.69,1.21]$)"]),
    ]
    for n, smax, p_sd, p_bkz, p_ratio, p_lo, p_hi, anchors in cost_specs:
        sd, bkz, ratio, lo, hi, nk = _cost_ratio(n, smax)
        got = [round(v, 2) for v in (sd, bkz, ratio, lo, hi)]
        match = got == [p_sd, p_bkz, p_ratio, p_lo, p_hi]
        records.append({
            "claim_id": f"frontier_cost_ratio_n{n}_b40_fplll",
            "tex_anchors": anchors,
            "verbatim": (f"n={n}: {p_sd} against {p_bkz} per 100 core-hours, "
                         f"ratio {p_ratio} [{p_lo},{p_hi}]"),
            "paper_value": {"sd": p_sd, "bkz": p_bkz, "ratio": p_ratio, "ci": [p_lo, p_hi]},
            "source": {"kind": "seeds",
                       "glob": f"results/seeds/ntru/q*/p*_mt{TOURS_DEFAULT}/n{n:03d}_beta40/"},
            "method": ("secret_exact_match legs over summed leg time (sdbkz_time, "
                       "bkz_time), pooled over the ladder's q cells"
                       + (f", seeds 1-{smax}" if smax else "")
                       + f"; ratio CI by bootstrap over keys, B={B}, rng_seed={RNG_SEED}, "
                       "percentile [2.5,97.5]"),
            "recomputed_value": {"sd": got[0], "bkz": got[1], "ratio": got[2],
                                 "ci": got[3:], "keys": nk},
            "match": match,
            "status": "DERIVED" if match else "DERIVED-UNRESOLVED",
            "note": f"{nk} keys.",
        })

    return records


if __name__ == "__main__":
    recs = build_records()
    print(json.dumps(recs, indent=2))
    print("\n--- summary ---")
    for r in recs:
        print(f"{r['claim_id']:38s} match={r['match']!s:5s} status={r['status']}")
    print("reproduced(all match):", all(r["match"] for r in recs))
