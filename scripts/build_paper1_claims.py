#!/usr/bin/env python3
"""Build the paper-1 claims ledger: results/paper_claims/paper1_claims.json.

One record per printed number in paper1/latex/sdbkz_paper_latex.tex, recomputed
from committed seeds. Same record shape and status taxonomy as the paper-2
ledger (scripts/build_paper2_claims.py). tests/test_paper1_claims.py fails when
a tex number, an anchor or the seeds move without the others.

Table rows are parsed from the tex, so the printed value is the paper value;
prose claims carry a literal anchor and the value printed there.

Read-only on results/seeds/; writes exactly results/paper_claims/paper1_claims.json.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics as st
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, BASE)

import numpy as np  # noqa: E402
from build_paper2_claims import _resolve_tex_lines  # noqa: E402
from log import get_logger  # noqa: E402
from scipy import stats  # noqa: E402

from analysis._data import load_all_seeds  # noqa: E402

PIPELINE = get_logger("build_paper1_claims")
OUT = os.path.join(BASE, "results", "paper_claims", "paper1_claims.json")
TEX = os.path.join(BASE, "paper1", "latex", "sdbkz_paper_latex.tex")
SCHEMA_VERSION = 1

DIMS = tuple(range(50, 151, 10))
HF_OUTLIER = 1e-3      # a seed whose two HFs differ by more is an outlier seed
SLOPE_POSITIONS = 75   # leading active positions the Figure 8 slopes are fitted on


def _matches(got, paper, decimals: int) -> bool:
    """got rounds to paper at the printed number of decimals (lists elementwise)."""
    if isinstance(paper, (list, tuple)):
        return len(got) == len(paper) and all(
            _matches(g, p, decimals) for g, p in zip(got, paper, strict=True))
    return abs(got - paper) <= 0.5 * 10 ** -decimals + 1e-12


def _rec(cid, anchor, paper, got, decimals, source, method, status="RECOMPUTED",
         match=None):
    return {
        "claim_id": cid, "tex_anchors": [anchor], "verbatim": anchor,
        "paper_value": paper, "recomputed_value": got,
        "match": _matches(got, paper, decimals) if match is None else match,
        "status": status, "source": source, "method": method, "note": "",
    }


def _table_rows(label: str) -> dict[int, tuple[str, list[float]]]:
    """{beta: (row text, printed values)} for the tabular under a table label."""
    with open(TEX, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, line in enumerate(lines) if f"\\label{{{label}}}" in line)
    rows = {}
    for line in lines[start:]:
        if "\\end{table}" in line:
            break
        m = re.match(r"\s*(\d+)\s*&(.*)\\\\", line)
        if m:
            cells = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", m.group(2)).replace("$", "")
            rows[int(m.group(1))] = (line.strip(), [float(c) for c in cells.split("&")])
    return rows


def _advantage_records(main) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97, "field": "advantage"}
    mean = {k: st.mean(s["advantage"] for s in v) for k, v in main.items()}
    recs = []
    rows = _table_rows("tab:beta-n-matrix")
    if sorted(rows) != [20, 30, 40]:
        raise SystemExit(f"tab:beta-n-matrix rows not parsed: {sorted(rows)}")
    for beta, (row, printed) in rows.items():
        got = [mean[(n, beta)] for n in DIMS]
        recs.append(_rec(f"adv_table_beta{beta}", row, printed, got, 3, src,
                         "group mean advantage, n=50..150, against the table row"))
    prose = {
        20: (r"$0.291 \to 0.314 \to 0.413 \to 0.473 \to 0.484 \to 0.362 \to 0.235 \to 0.094 \to 0.003 \to -0.108 \to -0.173$",
             [0.291, 0.314, 0.413, 0.473, 0.484, 0.362, 0.235, 0.094, 0.003, -0.108, -0.173], DIMS),
        30: (r"$0.405 \to 0.490 \to 0.524 \to 0.580 \to 0.922 \to 1.349 \to 1.112 \to 0.741 \to 0.352 \to -0.036 \to -0.395$",
             [0.405, 0.490, 0.524, 0.580, 0.922, 1.349, 1.112, 0.741, 0.352, -0.036, -0.395], DIMS),
        40: (r"$-0.028$ at $n=120$, $-1.325$ at $n=130$, $-1.452$ at $n=140$, $-1.292$ at $n=150$",
             [-0.028, -1.325, -1.452, -1.292], (120, 130, 140, 150)),
    }
    for beta, (anchor, paper, dims) in prose.items():
        recs.append(_rec(f"adv_prose_beta{beta}", anchor, paper,
                         [mean[(n, beta)] for n in dims], 3, src,
                         "group mean advantage against the trajectory sentence"))
    return recs


def _n110_paired_record(main) -> dict:
    a = {s["seed"]: s["advantage"] for s in main[(110, 40)]}
    b = {s["seed"]: s["advantage"] for s in main[(110, 30)]}
    diff = [a[k] - b[k] for k in sorted(set(a) & set(b))]
    m, se = st.mean(diff), st.stdev(diff) / math.sqrt(len(diff))
    t = float(stats.t.ppf(0.975, len(diff) - 1))
    got = [m, m - t * se, m + t * se]
    rec = _rec("n110_beta40_vs_beta30_paired",
               r"paired on the 100 shared seeds $+0.046$, 95\% CI $[-0.006, 0.098]$",
               [0.046, -0.006, 0.098], got, 3,
               {"kind": "seeds", "campaign": "main", "q": 97, "field": "advantage",
                "cells": ["n110_beta40", "n110_beta30"]},
               "per-seed advantage difference on shared seeds; mean and t-interval",
               status="DERIVED")
    rec["match"] = rec["match"] and len(diff) == 100
    rec["note"] = f"{len(diff)} shared seeds"
    return rec


def _rhf_records(main) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97, "field": "rhf_advantage"}
    outliers = {k: sum(abs(s["rhf_advantage"]) > HF_OUTLIER for s in v)
                for k, v in main.items()}
    clean = [abs(st.mean(s["rhf_advantage"] for s in v))
             for k, v in main.items() if not outliers[k]]
    worst = max(clean)
    starred = sorted(c for c in outliers.values() if c)
    return [
        _rec("rhf_mean_diff_bound",
             r"mean RHF differences are below $3\times 10^{-6}$ in all groups without outlier seeds",
             3e-6, worst, 6, src,
             "largest |group mean rhf_advantage| over groups with no outlier seed",
             status="DERIVED", match=worst < 3e-6),
        _rec("rhf_outlier_seed_range",
             r"differs by more than $10^{-3}$ in 1 to 47 seeds",
             [1, 47], [starred[0], starred[-1]], 0, src,
             f"outlier seeds per group (|rhf_advantage| > {HF_OUTLIER}), fewest and most",
             status="DERIVED"),
    ]


def _tours3x_records(t3) -> list[dict]:
    src = {"kind": "seeds", "campaign": "tours3x", "q": 97}
    dims = (50, 60, 70, 80)
    bkz = {n: st.mean(s["bkz_time"] for s in t3[(n, 30)]) for n in dims}
    sd = {n: st.mean(s["sdbkz_time"] for s in t3[(n, 30)]) for n in dims}
    ratio = [(sd[n] / 70) / (bkz[n] / 210) for n in dims]
    closed = sum(s["gap_closed"] for n in dims for s in t3[(n, 30)])
    seeds = sum(len(t3[(n, 30)]) for n in dims)
    return [
        _rec("tours3x_tour_cost_ratio",
             r"costing $2.70$--$2.82\times$ a single BKZ tour in these runs",
             [2.70, 2.82], [min(ratio), max(ratio)], 2, src,
             "mean SD-BKZ time per tour over mean BKZ time per tour, beta=30, range over n"),
        _rec("tours3x_equal_time_tours", r"as BKZ at 189--197 tours",
             [189, 197], [70 * min(ratio), 70 * max(ratio)], 0, src,
             "70 SD-BKZ tours in BKZ tours at the measured cost ratio"),
        _rec("tours3x_n50_seconds",
             r"SD-BKZ@70 took 921 seconds and BKZ@210 took 981",
             [921, 981], [sd[50], bkz[50]], 0, src, "mean wall time per seed, n=50 beta=30"),
        _rec("tours3x_extra_compute_pct",
             r"BKZ received 6.5\% more compute (8.4\% over the four dimensions)",
             [6.5, 8.4],
             [100 * (bkz[50] / sd[50] - 1),
              100 * (sum(bkz.values()) / sum(sd.values()) - 1)], 1, src,
             "BKZ@210 over SD-BKZ@70 mean wall time, n=50 and summed over n=50..80"),
        _rec("tours3x_gaps_closed", r"(0/400 gaps closed)",
             [0, 400], [closed, seeds], 0, src, "gap_closed count over beta=30 seeds"),
        _rec("tours3x_gap_at_3x",
             r"$+0.38$ nats at $n=50$, $+0.50$ at $n=60$, $+0.55$ at $n=70$, $+0.56$ at $n=80$",
             [0.38, 0.50, 0.55, 0.56],
             [st.mean(s["advantage_3x"] for s in t3[(n, 30)]) for n in dims], 2, src,
             "mean advantage_3x per dimension, beta=30"),
    ]


def _figure8_records(main) -> list[dict]:
    beta = 30
    slopes = {}
    for n in (70, 100, 130, 150):
        seeds = main[(n, beta)]
        m = seeds[0]["m"]
        for var in ("bkz", "sdbkz"):
            prof = np.mean([s[f"gs_lognorms_{var}"][m:] for s in seeds], axis=0)
            head = prof[:SLOPE_POSITIONS]
            slopes[(n, var)] = float(-np.polyfit(np.arange(len(head)), head, 1)[0])
    log_factor = math.log(beta / (2 * math.pi * math.e))
    gsa = (log_factor + math.log(math.pi * beta) / beta) / (beta - 1)
    fixed_point = log_factor / (beta - 1)
    flatter = sum(slopes[(n, "sdbkz")] < slopes[(n, "bkz")] for n in (70, 100, 130, 150))
    src = {"kind": "seeds", "campaign": "main", "q": 97,
           "field": "gs_lognorms_{bkz,sdbkz}", "cells": "n070..n150_beta30"}
    return [
        _rec("fig8_slopes",
             r"fitted slope $0.0266$--$0.0279$ per position, against $0.0247$ for the GSA and $0.0194$ for the fixed point",
             [0.0266, 0.0279, 0.0247, 0.0194],
             [min(slopes.values()), max(slopes.values()), gsa, fixed_point], 4, src,
             f"least-squares slope of the mean active-block profile, first {SLOPE_POSITIONS} "
             "positions; reference slopes from the closed forms", status="DERIVED"),
        _rec("fig8_sd_flatter", r"SD-BKZ is slightly flatter than BKZ in all four",
             4, flatter, 0, src, "panels where the SD-BKZ slope is below the BKZ slope",
             status="DERIVED"),
    ]


def build() -> dict:
    main = load_all_seeds(campaign="main", q=97)
    t3 = load_all_seeds(campaign="tours3x")
    records = (_advantage_records(main) + [_n110_paired_record(main)]
               + _rhf_records(main) + _tours3x_records(t3) + _figure8_records(main))
    _resolve_tex_lines(records, TEX)
    records.sort(key=lambda r: r["claim_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "description": "Paper-1 claim -> source -> method -> recomputed-value ledger. "
                       "See scripts/build_paper1_claims.py.",
        "n_records": len(records),
        "n_match": sum(1 for r in records if r["match"]),
        "records": records,
    }


def main(argv=None) -> int:
    ledger = build()
    with open(OUT, "w") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)
        f.write("\n")
    bad = [r["claim_id"] for r in ledger["records"] if not r["match"]]
    print(f"paper1_claims: {ledger['n_records']} records, {ledger['n_match']} match")
    for cid in bad:
        print(f"  MISMATCH {cid}")
    print(f"  wrote {os.path.relpath(OUT, BASE)}")
    PIPELINE.info("paper1 claims built", cat="claims", n_records=ledger["n_records"],
                  n_match=ledger["n_match"], mismatched=len(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
