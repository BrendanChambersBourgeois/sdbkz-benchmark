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
            "tex_anchors": [r"& 0.255 & 0.104 & \textbf{1.844} & 0.140"],
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
            "tex_anchors": [r"& 38/100 & 12/100 & 61/100 & 23/100"],
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
        "tex_anchors": [r"is $1.59$ nats higher on the sieve"],
        "verbatim": "median min-GS log-norm 1.59 nats higher on the sieve (1.844 vs 0.255)",
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
        "tex_anchors": [r"${\approx}4.9\times$ in norm"],
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
        "tex_anchors": [r"bit-identical on G6K"],
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

    # -- RHF: fplll |dHF| ~1e-6, outliers to 1.8e-5 at n=101/113 -------------
    # claim_id keeps the old "le_2e-6" name for key stability (tex reworded the
    # bound to "outliers to 1.8e-5").
    fp101 = _max_abs(101, "fplll_rhf_diff")
    fp113 = _max_abs(113, "fplll_rhf_diff")
    fp_max = max(fp101, fp113)
    # medians for the "~1e-6" typical size
    import statistics as st
    med101 = st.median([abs(r["fplll_rhf_diff"]) for r in xd[101]["data"]["per_seed"]
                        if r["fplll_rhf_diff"] is not None])
    med113 = st.median([abs(r["fplll_rhf_diff"]) for r in xd[113]["data"]["per_seed"]
                        if r["fplll_rhf_diff"] is not None])
    rhf_ok = _approx(fp_max, 1.8e-5, 0.05e-5)   # half a printed unit
    recs.append({
        "claim_id": "rhf_fplll_le_2e-6_n101_113",
        "tex_anchors": [r"($|\Delta\mathrm{HF}|\sim10^{-6}$, outliers to",
                        r"$1.8\times10^{-5}$)"],
        "verbatim": "on fplll |dHF| ~1e-6, outliers to 1.8e-5 (n=101/113, q=97)",
        "paper_value": 1.8e-5,
        "source": {"kind": "validation_json",
                   "path": "results/validation/g6k_sd_xengine_n{101,113}_mt50.json",
                   "field": "max_seed |data.per_seed[*].fplll_rhf_diff|"},
        "method": "max abs fplll_rhf_diff over 20 seeds at n=101/113 (POINTER)",
        "recomputed_value": fp_max,
        "match": rhf_ok,
        "status": "POINTER" if rhf_ok else "DERIVED-UNRESOLVED",
        "note": (f"max|fplll_rhf_diff| = {fp101:.2e} (n=101) / {fp113:.2e} (n=113), "
                 f"median ~{med101:.1e} / ~{med113:.1e}: tex '~1e-6, outliers to "
                 f"1.8e-5' (reworded from <=2e-6)."),
    })

    # -- gs0 2.332 for the jointly-fired n=89 seed (seed 19), bit-identical --
    seed19 = next(r for r in xd[89]["data"]["per_seed"] if r["seed"] == 19)
    fs0, gs0 = seed19["fplll_sdbkz_gs0"], seed19["g6k_sdbkz_gs0"]
    assert fs0 == gs0, f"n=89 seed19 gs0 not bit-identical: {fs0} vs {gs0}"
    recs.append({
        "claim_id": "gs0_n89_fired_seed19",
        "tex_anchors": [r"matches exactly ($2.332$)"],
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
    xeng_row = {89: "89  & 2/20 & 1/20 & 0.50", 101: "101 & 0/20 & 0/20 & 1.00",
                113: "113 & 0/20 & 0/20 & 1.00"}   # tab:xeng-sound rows (tex spacing)
    jac_spec = [(89, 0.50), (101, 1.00), (113, 1.00)]
    for n, paper in jac_spec:
        src = xd[n]["data"]["jaccard_agreement"]
        recs.append({
            "claim_id": f"jaccard_n{n}",
            "tex_anchors": [xeng_row[n]],
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
            "tex_anchors": [xeng_row[n]],
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
            "tex_anchors": [r"(fplll $-0.00039$ vs G6K $-0.00040$)"],
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
# tab:coverage scope (frozen Paper 2 data: fplll 6,320 + G6K
# 2,384). The 'ntru' campaign and the g6k manifest also hold rows outside the
# table: the n>=157 frontier ladders (both engines) and the native beta=40
# ladders at n in {109,127,131,137,139,149,151}. The table's n=127 row is
# beta=20 only, so (127, 40) is excluded by (n, beta).
P2_FPLLL_N = {59, 61, 67, 71, 73, 79, 83, 89, 101, 113, 127}
P2_EXCLUDE = {(127, 40)}


def in_coverage(s: dict) -> bool:
    """True iff manifest row s is counted in tab:coverage (either engine)."""
    return s["n"] in P2_FPLLL_N and (s["n"], s["beta"]) not in P2_EXCLUDE


def _coverage_records() -> list[dict]:
    man = _load("results/seed_manifest.json")
    g6man = _load("results/g6k_seed_manifest.json")

    ntru = [s for s in man["seeds"] if s["campaign"] == "ntru"]
    fp = [s for s in ntru if in_coverage(s)]
    g6 = [s for s in g6man["seeds"] if in_coverage(s)]

    n_fplll = len(fp)     # 6320  (== tab:coverage N_fplll total)
    n_g6k = len(g6)       # 2384  (== tab:coverage N_G6K total)
    total = n_fplll + n_g6k

    fp_cells = {(s["n"], s["beta"], s["q"]) for s in fp}
    g6_cells = {(s["n"], s["beta"], s["q"]) for s in g6}
    n_cells = len(fp_cells | g6_cells)

    recs = [
        {
            "claim_id": "coverage_fplll_total",
            "tex_anchors": [r"\multicolumn{5}{r}{total} & 6320 & 2384"],
            "verbatim": "tab:coverage total N_fplll = 6320",
            "paper_value": 6320,
            "source": {"kind": "seed_manifest", "path": "results/seed_manifest.json",
                       "field": "count(seeds where campaign=='ntru' and in_coverage)"},
            "method": "filter seed_manifest to tab:coverage scope and count (POINTER)",
            "recomputed_value": n_fplll,
            "match": n_fplll == 6320,
            "status": "POINTER",
            "note": f"excludes {len(ntru) - n_fplll} 'ntru' rows outside the table "
                    "(n>=157 frontier ladders, native beta=40 ladders incl. n=127).",
        },
        {
            "claim_id": "coverage_g6k_total",
            "tex_anchors": [r"\multicolumn{5}{r}{total} & 6320 & 2384"],
            "verbatim": "tab:coverage total N_G6K = 2384",
            "paper_value": 2384,
            "source": {"kind": "seed_manifest", "path": "results/g6k_seed_manifest.json",
                       "field": "count(seeds where in_coverage)"},
            "method": "count g6k manifest rows in tab:coverage scope (POINTER)",
            "recomputed_value": n_g6k,
            "match": n_g6k == 2384,
            "status": "POINTER",
            "note": f"excludes {len(g6man['seeds']) - n_g6k} g6k rows at n>=157 "
                    "(frontier, outside the table).",
        },
        {
            "claim_id": "coverage_seed_pairs",
            "tex_anchors": [r"Totals: 8{,}704 seed pairs over 147 $(n,\beta,q)$ cells"],
            "verbatim": "8,704 seed pairs over 147 (n,beta,q) cells",
            "paper_value": 8704,
            "source": {"kind": "seed_manifest",
                       "path": "results/seed_manifest.json + results/g6k_seed_manifest.json",
                       "field": "N_fplll(6320) + N_G6K(2384)"},
            "method": "paper-2 fplll seed count + g6k seed count (POINTER)",
            "recomputed_value": total,
            "match": total == 8704,
            "status": "POINTER",
            "note": "6320 + 2384 = 8704 (pre-B-ingest prose said 8,144 = 8704-560; fixed 2026-09-27).",
        },
        {
            "claim_id": "coverage_cells",
            "tex_anchors": [r"Totals: 8{,}704 seed pairs over 147 $(n,\beta,q)$ cells"],
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
