#!/usr/bin/env python3
"""Paper-2 claims ledger -- POINTER slice (plan step 3).

Records the flagged paper-2 numbers that are ALREADY backed by a committed
validation JSON / seed manifest.  Each record is a POINTER: the value is copied
verbatim from a committed source field, and we assert-fail-loud that the copied
value still equals the source field (drift guard), then compare against the
paper's printed value.

Sources (all under the repo root):
  results/validation/sieve_vs_enum_min_gs_clearing.json   (min-GS medians/counts/nats)
  results/validation/g6k_sd_xengine_n{89,101,113}_mt50.json (RHF/gs0/Jaccard/fired)
  results/validation/adr008_sd_cross_engine.json          (slope signature)
  results/seed_manifest.json + results/g6k_seed_manifest.json (coverage 8704 / 147 cells)

The pointer slice does NOT re-score raw seeds, so it does not need
extract_dsd_onset's scoring primitives (onset_for / _seed_fires / _cell_rate) --
those are for the RECOMPUTED slice.  Byte-identity of the pointer values is
guaranteed structurally: they are read straight out of the committed artifacts.

Read-only.  Never writes under results/seeds/.
"""
from __future__ import annotations

import json
import math
import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (scripts/_paper2_claims/ -> up 3)


def _load(rel: str) -> dict:
    with open(os.path.join(BASE, rel)) as f:
        return json.load(f)


def _approx(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


# --------------------------------------------------------------------------- #
#  (1) min-GS medians / counts / nats                                         #
# --------------------------------------------------------------------------- #
def _mings_records() -> list[dict]:
    rel = "results/validation/sieve_vs_enum_min_gs_clearing.json"
    d = _load(rel)
    cell = d["data_n89_beta40_mt50_p250"]["q137_N100_tight"]
    recs = []

    # medians:  fplll SD 0.255 / BKZ 0.104 ; g6k SD 1.844 / BKZ 0.140
    med_spec = [
        ("mings_med_fplll_sd", "fplll", "SD", 0.255, 589),
        ("mings_med_fplll_bkz", "fplll", "BKZ", 0.104, 589),
        ("mings_med_g6k_sd", "g6k", "SD", 1.844, 589),
        ("mings_med_g6k_bkz", "g6k", "BKZ", 0.140, 589),
    ]
    for cid, eng, var, paper, line in med_spec:
        src = cell[eng][var]["med_min_gs"]
        recs.append({
            "claim_id": cid,
            "tex_lines": [589],
            "verbatim": "median min_i log||b*_i||: 0.255 / 0.104 / 1.844 / 0.140",
            "paper_value": paper,
            "source": {"kind": "validation_json", "path": rel,
                       "field": f"data_n89_beta40_mt50_p250.q137_N100_tight.{eng}.{var}.med_min_gs"},
            "method": "verbatim copy of committed median-min-GS field (POINTER)",
            "recomputed_value": src,
            "match": _approx(src, paper, 1e-3),
            "status": "POINTER",
            "note": f"{eng} {var} @ q137 N=100 tight cell; artifact_check PASSED 2026-06-08.",
        })

    # min-GS-clearing counts (b1):  38 / 12 / 61 / 23
    cnt_spec = [
        ("mings_b1_fplll_sd", "fplll", "SD", 38),
        ("mings_b1_fplll_bkz", "fplll", "BKZ", 12),
        ("mings_b1_g6k_sd", "g6k", "SD", 61),
        ("mings_b1_g6k_bkz", "g6k", "BKZ", 23),
    ]
    for cid, eng, var, paper in cnt_spec:
        src = cell[eng][var]["b1"]
        recs.append({
            "claim_id": cid,
            "tex_lines": [585, 688],
            "verbatim": "min-GS-clearing @ q=137: 38/100 12/100 61/100 23/100",
            "paper_value": paper,
            "source": {"kind": "validation_json", "path": rel,
                       "field": f"data_n89_beta40_mt50_p250.q137_N100_tight.{eng}.{var}.b1"},
            "method": "verbatim copy of committed b1 (#seeds min(gs)>1.5) field (POINTER)",
            "recomputed_value": src,
            "match": src == paper,
            "status": "POINTER",
            "note": f"{eng} {var} min-GS-clearing count @ q137 N=100.",
        })

    # nats gap = g6k-SD median - fplll-SD median = 1.844 - 0.255 = 1.589 -> +1.59
    sd_g6k = cell["g6k"]["SD"]["med_min_gs"]
    sd_fpl = cell["fplll"]["SD"]["med_min_gs"]
    nats = sd_g6k - sd_fpl
    recs.append({
        "claim_id": "mings_nats",
        "tex_lines": [688],
        "verbatim": "median log-norm 1.844 (sieve) vs 0.255 (enum), +1.59 nats",
        "paper_value": 1.59,
        "source": {"kind": "validation_json", "path": rel,
                   "field": "g6k.SD.med_min_gs - fplll.SD.med_min_gs (q137_N100_tight)"},
        "method": "1.844 - 0.255 = 1.589 (light arithmetic on two POINTER fields)",
        "recomputed_value": round(nats, 2),
        "match": _approx(round(nats, 2), 1.59, 1e-9),
        "status": "POINTER",
        "note": f"exact nats = {nats:.4f}; tex rounds to +1.59.",
    })

    # ratio in vector norm = exp(nats) ~ 4.9x
    ratio = math.exp(nats)
    recs.append({
        "claim_id": "mings_ratio",
        "tex_lines": [689],
        "verbatim": "~4.9x in vector norm",
        "paper_value": 4.9,
        "source": {"kind": "validation_json", "path": rel,
                   "field": "exp(g6k.SD.med_min_gs - fplll.SD.med_min_gs)"},
        "method": "exp(1.589) = 4.899 (light arithmetic on POINTER fields)",
        "recomputed_value": round(ratio, 1),
        "match": _approx(round(ratio, 1), 4.9, 1e-9),
        "status": "POINTER",
        "note": f"exact ratio = {ratio:.4f}; tex rounds to ~4.9x.",
    })
    return recs


# --------------------------------------------------------------------------- #
#  (2) RHF / gs0 / Jaccard / fired counts / slope                             #
# --------------------------------------------------------------------------- #
def _xengine_records() -> list[dict]:
    recs = []
    xfiles = {n: f"results/validation/g6k_sd_xengine_n{n}_mt50.json"
              for n in (89, 101, 113)}
    xd = {n: _load(rel) for n, rel in xfiles.items()}

    def _max_abs(n: int, key: str) -> float:
        return max(abs(r[key]) for r in xd[n]["data"]["per_seed"]
                   if r[key] is not None)

    # -- RHF: g6k bases bit-identical (rhf_diff == 0) at n=101/113 -----------
    g6_max = max(_max_abs(101, "g6k_rhf_diff"), _max_abs(113, "g6k_rhf_diff"))
    recs.append({
        "claim_id": "rhf_g6k_bit_identical_n101_113",
        "tex_lines": [503, 504],
        "verbatim": "at n=101/113 the stored Hermite-factor values of the G6K "
                    "BKZ and SD-BKZ bases are bit-identical seed-for-seed",
        "paper_value": 0.0,
        "source": {"kind": "validation_json",
                   "path": "results/validation/g6k_sd_xengine_n{101,113}_mt50.json",
                   "field": "max_seed |data.per_seed[*].g6k_rhf_diff|"},
        "method": "max abs g6k_rhf_diff over 20 seeds at n=101 and n=113 (POINTER)",
        "recomputed_value": g6_max,
        "match": g6_max == 0.0,
        "status": "POINTER",
        "note": "g6k SD-BKZ vs BKZ RHF is bit-identical (0.0 exactly) on all 40 seeds.",
    })

    # -- RHF: fplll RHF diff <= 2e-6 at n=101/113  (STRICT MAX FAILS) --------
    fp101 = _max_abs(101, "fplll_rhf_diff")
    fp113 = _max_abs(113, "fplll_rhf_diff")
    fp_max = max(fp101, fp113)
    # medians for the honest interpretation note
    import statistics as st
    med101 = st.median([abs(r["fplll_rhf_diff"]) for r in xd[101]["data"]["per_seed"]
                        if r["fplll_rhf_diff"] is not None])
    med113 = st.median([abs(r["fplll_rhf_diff"]) for r in xd[113]["data"]["per_seed"]
                        if r["fplll_rhf_diff"] is not None])
    recs.append({
        "claim_id": "rhf_fplll_le_2e-6_n101_113",
        "tex_lines": [504, 505, 506],
        "verbatim": "on fplll the BKZ-vs-SD-BKZ Hermite factors hold to "
                    "<=2x10^-6 across 20 seeds at each of n=67/101/113",
        "paper_value": 2e-6,
        "source": {"kind": "validation_json",
                   "path": "results/validation/g6k_sd_xengine_n{101,113}_mt50.json",
                   "field": "max_seed |data.per_seed[*].fplll_rhf_diff|"},
        "method": "max abs fplll_rhf_diff over 20 seeds at n=101/113 (POINTER)",
        "recomputed_value": fp_max,
        "match": fp_max <= 2e-6,
        "status": "DERIVED-UNRESOLVED",
        "note": (f"STRICT MAX VIOLATES the <=2e-6 bound: max|fplll_rhf_diff| = "
                 f"{fp101:.2e} (n=101) / {fp113:.2e} (n=113). The MEDIAN does hold "
                 f"(~{med101:.1e} n=101 / ~{med113:.1e} n=113); ~2-3 outlier seeds "
                 f"per cell reach 1-1.8e-5. tex n=67 leg not checkable (no "
                 f"g6k_sd_xengine_n67 file committed). Flag for human: either the "
                 f"<=2e-6 is a median/typical bound (relax tex wording) or the "
                 f"outlier seeds need explaining. Do NOT edit tex from the ledger."),
    })

    # -- gs0 2.332 for the jointly-fired n=89 seed (seed 19), bit-identical --
    seed19 = next(r for r in xd[89]["data"]["per_seed"] if r["seed"] == 19)
    fs0, gs0 = seed19["fplll_sdbkz_gs0"], seed19["g6k_sdbkz_gs0"]
    assert fs0 == gs0, f"n=89 seed19 gs0 not bit-identical: {fs0} vs {gs0}"
    recs.append({
        "claim_id": "gs0_n89_fired_seed19",
        "tex_lines": [523, 531],
        "verbatim": "the jointly-fired n=89 seed matches exactly (2.332)",
        "paper_value": 2.332,
        "source": {"kind": "validation_json",
                   "path": "results/validation/g6k_sd_xengine_n89_mt50.json",
                   "field": "data.per_seed[seed=19].{fplll,g6k}_sdbkz_gs0"},
        "method": "round(gs0, 3) of the jointly-fired seed-19 first GS log-norm (POINTER)",
        "recomputed_value": round(fs0, 3),
        "match": _approx(round(fs0, 3), 2.332, 1e-9),
        "status": "POINTER",
        "note": f"fplll==g6k bit-identical = {fs0:.6f}; both fire (<3.5). "
                f"g6k-only fire is seed 17 (g6k gs0 {xd[89]['data']['per_seed'][16]['g6k_sdbkz_gs0']:.3f}).",
    })

    # -- Jaccard agreement per n --------------------------------------------
    jac_spec = [(89, 0.50), (101, 1.00), (113, 1.00)]
    for n, paper in jac_spec:
        src = xd[n]["data"]["jaccard_agreement"]
        recs.append({
            "claim_id": f"jaccard_n{n}",
            "tex_lines": [520, 521, 534],
            "verbatim": f"Jaccard n={n} = {paper:.2f} "
                        f"({'0/0 vacuous' if paper == 1.00 else 'real'})",
            "paper_value": paper,
            "source": {"kind": "validation_json", "path": xfiles[n],
                       "field": "data.jaccard_agreement"},
            "method": "verbatim copy of committed jaccard_agreement (POINTER)",
            "recomputed_value": src,
            "match": _approx(src, paper, 1e-9),
            "status": "POINTER",
            "note": "n=101/113 Jaccard 1.00 is vacuous (0/0, neither engine fires).",
        })

    # -- fired counts (tab:xeng-sound):  n=89 g6k 2/1, n=101/113 0/0 ---------
    fired_spec = [
        ("xeng_fired_n89_g6k", 89, "g6k_fired_seeds", 2),
        ("xeng_fired_n89_fplll", 89, "fplll_fired_seeds", 1),
        ("xeng_fired_n101_g6k", 101, "g6k_fired_seeds", 0),
        ("xeng_fired_n101_fplll", 101, "fplll_fired_seeds", 0),
        ("xeng_fired_n113_g6k", 113, "g6k_fired_seeds", 0),
        ("xeng_fired_n113_fplll", 113, "fplll_fired_seeds", 0),
    ]
    for cid, n, key, paper in fired_spec:
        src = len(xd[n]["data"][key])
        matched = xd[n]["data"]["matched_seeds"]
        assert matched == 20, f"n={n} matched_seeds != 20"
        recs.append({
            "claim_id": cid,
            "tex_lines": [534, 535, 536],
            "verbatim": f"tab:xeng-sound n={n} {key.split('_')[0]} fired {paper}/20",
            "paper_value": paper,
            "source": {"kind": "validation_json", "path": xfiles[n],
                       "field": f"len(data.{key}) of data.matched_seeds"},
            "method": f"count of {key} over 20 matched seeds (POINTER)",
            "recomputed_value": src,
            "match": src == paper,
            "status": "POINTER",
            "note": f"{key.split('_')[0]} fired {src}/{matched} at q=97.",
        })

    # -- slope-flattening signature (adr008): fplll -0.00039 / g6k -0.00040 --
    rel = "results/validation/adr008_sd_cross_engine.json"
    adr = _load(rel)
    slope = adr["data"]["sd_minus_bkz_delta"]["slope"]
    for cid, eng, paper, line in [
        ("slope_flatten_fplll", "fplll", -0.00039, 247),
        ("slope_flatten_g6k", "g6k", -0.00040, 248),
    ]:
        src = slope[eng]
        recs.append({
            "claim_id": cid,
            "tex_lines": [247, 248, 494, 495],
            "verbatim": "per-tour GS-slope-flattening signature "
                        "(-0.00039 vs G6K -0.00040)",
            "paper_value": paper,
            "source": {"kind": "validation_json", "path": rel,
                       "field": f"data.sd_minus_bkz_delta.slope.{eng}"},
            "method": "verbatim copy of committed SD-minus-BKZ slope delta (POINTER)",
            "recomputed_value": src,
            "match": _approx(src, paper, 1e-9),
            "status": "POINTER",
            "note": "ADR-008 3-tour cross-engine validation; same_direction=True.",
        })
    return recs


# --------------------------------------------------------------------------- #
#  (3) coverage: 8704 seed pairs over 147 (n,beta,q) cells                     #
# --------------------------------------------------------------------------- #
# Paper-2 fplll dimensions (coverage table tab:coverage rows). The 'ntru'
# campaign in seed_manifest.json also carries the n>=157 frontier onset runs
# (157/167/173/181) which are NOT part of the paper-2 coverage table, so the
# cell filter restricts to these dimensions.
P2_FPLLL_N = {59, 61, 67, 71, 73, 79, 83, 89, 101, 113, 127}


def _coverage_records() -> list[dict]:
    man = _load("results/seed_manifest.json")
    g6man = _load("results/g6k_seed_manifest.json")

    fp = [s for s in man["seeds"]
          if s["campaign"] == "ntru" and s["n"] in P2_FPLLL_N]
    g6 = g6man["seeds"]

    n_fplll = len(fp)     # 6320  (== tab:coverage N_fplll total)
    n_g6k = len(g6)       # 2384  (== tab:coverage N_G6K total)
    total = n_fplll + n_g6k

    fp_cells = {(s["n"], s["beta"], s["q"]) for s in fp}
    g6_cells = {(s["n"], s["beta"], s["q"]) for s in g6}
    n_cells = len(fp_cells | g6_cells)

    recs = [
        {
            "claim_id": "coverage_fplll_total",
            "tex_lines": [331],
            "verbatim": "tab:coverage total N_fplll = 6320",
            "paper_value": 6320,
            "source": {"kind": "seed_manifest", "path": "results/seed_manifest.json",
                       "field": "count(seeds where campaign=='ntru' and n in P2_FPLLL_N)"},
            "method": "filter seed_manifest to paper-2 fplll dimensions and count (POINTER)",
            "recomputed_value": n_fplll,
            "match": n_fplll == 6320,
            "status": "POINTER",
            "note": "excludes n>=157 frontier onset runs (157/167/173/181, 420 seeds) "
                    "that live in the same 'ntru' campaign but not the paper-2 grid.",
        },
        {
            "claim_id": "coverage_g6k_total",
            "tex_lines": [331],
            "verbatim": "tab:coverage total N_G6K = 2384",
            "paper_value": 2384,
            "source": {"kind": "seed_manifest", "path": "results/g6k_seed_manifest.json",
                       "field": "len(seeds)"},
            "method": "count entire committed g6k manifest (POINTER)",
            "recomputed_value": n_g6k,
            "match": n_g6k == 2384,
            "status": "POINTER",
            "note": "whole g6k manifest is paper-2 (n in {67,79,89,101,113}).",
        },
        {
            "claim_id": "coverage_seed_pairs",
            "tex_lines": [301],
            "verbatim": "8,704 seed pairs over 147 (n,beta,q) cells",
            "paper_value": 8704,
            "source": {"kind": "seed_manifest",
                       "path": "results/seed_manifest.json + results/g6k_seed_manifest.json",
                       "field": "N_fplll(6320) + N_G6K(2384)"},
            "method": "paper-2 fplll seed count + g6k seed count (POINTER)",
            "recomputed_value": total,
            "match": total == 8704,
            "status": "POINTER",
            "note": "6320 + 2384 = 8704. NOTE tex line 293 prose still says stale 8,144 "
                    "(pre-B-ingest = 8704-560); separate one-token tex bug, out of ledger scope.",
        },
        {
            "claim_id": "coverage_cells",
            "tex_lines": [301],
            "verbatim": "147 (n,beta,q) cells, q in [97,1811]",
            "paper_value": 147,
            "source": {"kind": "seed_manifest",
                       "path": "results/seed_manifest.json + results/g6k_seed_manifest.json",
                       "field": "|distinct (n,beta,q) over paper-2 fplll UNION g6k|"},
            "method": "union of distinct (n,beta,q) cells across both engines (POINTER)",
            "recomputed_value": n_cells,
            "match": n_cells == 147,
            "status": "POINTER",
            "note": f"fplll cells {len(fp_cells)} + g6k cells {len(g6_cells)}, "
                    f"union {n_cells} (g6k cells are a subset overlap of fplll q-grid).",
        },
    ]
    return recs


def build_records() -> list[dict]:
    recs = []
    recs += _mings_records()
    recs += _xengine_records()
    recs += _coverage_records()
    return recs


if __name__ == "__main__":
    rs = build_records()
    ok = 0
    for r in rs:
        flag = "OK " if r["match"] else "!! "
        print(f"{flag}{r['claim_id']:32} paper={r['paper_value']!r:>12}  "
              f"recomputed={r['recomputed_value']!r:>14}  [{r['status']}]")
        ok += bool(r["match"])
    print(f"\n{ok}/{len(rs)} records match.")
    print(json.dumps(rs, indent=2))
