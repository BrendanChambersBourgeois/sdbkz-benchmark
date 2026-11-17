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

from analysis._data import (  # noqa: E402
    _decompose_seed,
    _load_convergence_files,
    _per_position_group_stats,
    gsa_fixed_point,
    load_all_seeds,
)

PIPELINE = get_logger("build_paper1_claims")
OUT = os.path.join(BASE, "results", "paper_claims", "paper1_claims.json")
TEX = os.path.join(BASE, "paper1", "latex", "sdbkz_paper_latex.tex")
SIDE_MANIFEST = os.path.join(BASE, "results", "side_seed_manifest.json")
SCHEMA_VERSION = 1

DIMS = tuple(range(50, 151, 10))
HF_OUTLIER = 1e-3      # a seed whose two HFs differ by more is an outlier seed
SLOPE_POSITIONS = 75   # leading active positions the Figure 8 slopes are fitted on
FAVOURABLE_MAX_N = 110  # "favourable" groups in the paper are n=50..110
MAIN = {"kind": "seeds", "campaign": "main", "q": 97, "field": "advantage"}
FLOOR_LOGNORM = -100.0  # a q=3329 double-measured seed below this hit the floor
# Captions that restate a prose claim word for word: second anchor, same record.
CAPTION_ECHO = {
    "tours3x_gaps_closed": r"0/400 gaps closed across four dimensions",
    "tours3x_beta20_closure": r"closes 67\% of the gap and wins 26/100 seeds",
}


def _matches(got, paper, decimals) -> bool:
    """got rounds to paper at the printed number of decimals (lists elementwise;
    decimals may be one int or one per element)."""
    if isinstance(paper, (list, tuple)):
        decs = decimals if isinstance(decimals, (list, tuple)) else [decimals] * len(paper)
        return len(got) == len(paper) and all(
            _matches(g, p, d) for g, p, d in zip(got, paper, decs, strict=True))
    return abs(got - paper) <= 0.5 * 10 ** -decimals + 1e-12


def _p_matches(cell: str, got: float) -> bool:
    """A printed p-value cell agrees with got: a bound ('<10^{-15}') holds, a value
    ('3.3\\times 10^{-8}', '0.007') equals got at its printed significant digits."""
    m = re.fullmatch(r"(<)?([\d.]+)?(?:\\times)?(?:10\^\{(-?\d+)\})?", cell.replace(" ", ""))
    mant = m.group(2) or "1"
    val = float(f"{mant}e{m.group(3) or 0}")
    if m.group(1):
        return got < val
    sig = len(mant.replace(".", "").lstrip("0"))
    return float(f"{got:.{sig - 1}e}") == val


def _sci_matches(cell: str, got: float) -> bool:
    """A signed cell ('-7.4\\times 10^{-11}') or a bound on the size ('<10^{-6}')
    agrees with got."""
    if cell.startswith("<"):
        return _p_matches(cell, abs(got))
    return cell.startswith("-") == (got < 0) and _p_matches(cell.lstrip("-"), abs(got))


def _num(cell: str) -> float:
    return float(re.sub(r"\{,\}|\\times", "", cell))


def _rec(cid, anchor, paper, got, decimals, source, method, status="RECOMPUTED",
         match=None):
    return {
        "claim_id": cid, "tex_anchors": [anchor], "verbatim": anchor,
        "paper_value": paper, "recomputed_value": got,
        "match": bool(_matches(got, paper, decimals) if match is None else match),
        "status": status, "source": source, "method": method, "note": "",
    }


def _rows(label: str) -> list[tuple[str, list[str]]]:
    """(row text, cell strings) for each numeric row of the tabular under a label."""
    with open(TEX, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, line in enumerate(lines) if f"\\label{{{label}}}" in line)
    rows = []
    for line in lines[start:]:
        if "\\end{table}" in line:
            break
        m = re.match(r"\s*(\d+\s*&.*?)\s*\\\\", line)
        if m:
            cells = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", m.group(1))
            cells = re.sub(r"\$|\\%|\\,|\\ast", "", cells)
            rows.append((line.strip(), [c.strip() for c in cells.split("&")]))
    if not rows:
        raise SystemExit(f"{label}: no rows parsed")
    return rows


def _table_rows(label: str) -> dict[int, tuple[str, list[float]]]:
    """{beta: (row text, printed values)} for a table keyed by its first column."""
    return {int(c[0]): (row, [float(x) for x in c[1:]]) for row, c in _rows(label)}


def _floats(cell: str) -> list[float]:
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", cell)]


def _t_interval(a) -> list[float]:
    half = float(stats.t.ppf(0.975, len(a) - 1)) * a.std(ddof=1) / math.sqrt(len(a))
    return [float(a.mean() - half), float(a.mean() + half)]


def _group_stats(main) -> dict:
    out = {}
    for key, seeds in main.items():
        a = np.array([s["advantage"] for s in seeds])
        out[key] = {
            "a": a, "seeds": len(a), "mean": float(a.mean()), "std": float(a.std(ddof=1)),
            "win": 100 * float((a > 0).mean()), "ci": _t_interval(a),
            "d": float(a.mean() / a.std(ddof=1)),
            "t_p": float(stats.ttest_1samp(a, 0).pvalue),
            "w_p": float(stats.wilcoxon(a).pvalue),
            "shapiro_p": float(stats.shapiro(a).pvalue),
            "bkz_margin": float(-a[a < 0].mean()) if (a < 0).any() else 0.0,
        }
    return out


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


def _group_table_records(gs) -> list[dict]:
    recs = []
    for row, c in _rows("tab:main"):
        n, beta = int(c[0]), int(c[1])
        g = gs[(n, beta)]
        recs.append(_rec(f"main_n{n:03d}_beta{beta}", row,
                         [int(c[2]), float(c[4]), float(c[5]), float(c[6])],
                         [g["seeds"], g["mean"], g["std"], g["win"]], [0, 3, 3, 0], MAIN,
                         "seed count, mean, sample std and SD-BKZ win % of the advantage"))
    for row, c in _rows("tab:peak"):
        n, beta = int(c[0]), int(c[1])
        g = gs[(n, beta)]
        recs.append(_rec(f"peak_n{n:03d}_beta{beta}", row,
                         [int(c[2])] + [float(x) for x in c[3:]],
                         [g["seeds"], beta / n, g["mean"], g["std"], g["win"]],
                         [0, 2, 3, 3, 0], MAIN,
                         "seed count, beta/n, mean, sample std and SD-BKZ win % of the advantage"))
    return recs


def _stats_records(gs) -> list[dict]:
    recs = []
    for row, c in _rows("tab:stats"):
        n, beta = int(c[0]), int(c[1])
        g = gs[(n, beta)]
        recs.append(_rec(f"stats_n{n:03d}_beta{beta}_ci_d", row,
                         _floats(c[2]) + [float(c[3])], g["ci"] + [g["d"]], [3, 3, 2], MAIN,
                         "t-interval on the mean advantage; Cohen's d = mean / sample std"))
        recs.append(_rec(f"stats_n{n:03d}_beta{beta}_p", row, [c[4], c[5]],
                         [g["t_p"], g["w_p"]], 0, MAIN,
                         "two-sided one-sample t-test and Wilcoxon signed-rank on the advantage; "
                         "a printed bound must hold, a printed value must round to it",
                         match=_p_matches(c[4], g["t_p"]) and _p_matches(c[5], g["w_p"])))

    fav = {k: g for k, g in gs.items() if k[0] <= FAVOURABLE_MAX_N}
    lo, hi = min(fav, key=lambda k: fav[k]["d"]), max(fav, key=lambda k: fav[k]["d"])
    non_normal = sorted(k for k, g in gs.items() if g["shapiro_p"] <= 0.05)
    low_n = [g["bkz_margin"] for k, g in gs.items() if k[0] <= 100 and g["bkz_margin"]]
    sd30 = [gs[(n, 30)]["std"] for n in DIMS]
    g130 = gs[(130, 20)]
    cliff = gs[(130, 40)]
    recs += [
        _rec("stats_t_p_below_1e-15", r"$p<10^{-15}$ for 28 of the 33 complete groups",
             [28, 33], [sum(g["t_p"] < 1e-15 for g in gs.values()), len(gs)], 0, MAIN,
             "groups whose paired t-test p is below 1e-15", status="DERIVED"),
        _rec("stats_cohen_d_range",
             r"Cohen's $d=1.31$ ($n=50$, $\beta=40$) to $9.60$ ($n=100$, $\beta=40$)",
             [1.31, 9.60], [fav[lo]["d"], fav[hi]["d"]], 2, MAIN,
             "smallest and largest Cohen's d over n=50..110, and the groups they sit in",
             status="DERIVED",
             match=_matches([fav[lo]["d"], fav[hi]["d"]], [1.31, 9.60], 2)
             and (lo, hi) == ((50, 40), (100, 40))),
        _rec("stats_ci_excludes_zero", r"exclude zero in 32 of 33 groups",
             [32, 33], [sum(g["ci"][0] > 0 or g["ci"][1] < 0 for g in gs.values()), len(gs)],
             0, MAIN, "groups whose 95% t-interval excludes zero", status="DERIVED"),
        _rec("stats_n130_beta20_ci", r"$[-0.029, +0.035]$, $p=0.85$",
             [-0.029, 0.035, 0.85], g130["ci"] + [g130["t_p"]], [3, 3, 2], MAIN,
             "t-interval and paired t-test p, n=130 beta=20"),
        _rec("stats_shapiro_exceptions",
             r"$n=100$, $\beta=20$ ($p=0.033$) and $n=110$, $\beta=40$ ($p=0.049$)",
             [0.033, 0.049], [gs[(100, 20)]["shapiro_p"], gs[(110, 40)]["shapiro_p"]], 3,
             MAIN, "Shapiro-Wilk p on the advantage; these are the only groups at or below 0.05",
             status="DERIVED",
             match=non_normal == [(100, 20), (110, 40)]
             and _matches([gs[k]["shapiro_p"] for k in non_normal], [0.033, 0.049], 3)),
        _rec("stats_bkz_margin_low_n",
             r"in the six groups at $n\leq 100$ where BKZ wins any seeds, its mean margin is below 0.04 nats",
             [6, 0.04], [len(low_n), max(low_n)], 2, MAIN,
             "groups at n<=100 with a BKZ-won seed, and the largest mean BKZ margin among them",
             status="DERIVED", match=len(low_n) == 6 and max(low_n) < 0.04),
        _rec("stats_bkz_margin_n140_beta40", r"to 1.45 nats at $n=140$, $\beta=40$",
             1.45, gs[(140, 40)]["bkz_margin"], 2, MAIN,
             "mean BKZ margin over BKZ-won seeds, n=140 beta=40"),
        _rec("std_n070_beta40", r"the standard deviation is 0.096, roughly one-quarter of the mean",
             0.096, gs[(70, 40)]["std"], 3, MAIN, "sample std of the advantage, n=70 beta=40"),
        _rec("std_range_beta30", r"the standard deviation remains stable at 0.09--0.22 across dimensions",
             [0.09, 0.22], [min(sd30), max(sd30)], 2, MAIN,
             "smallest and largest sample std of the advantage over n=50..150, beta=30",
             status="DERIVED"),
        _rec("cliff_n130_beta40_d", r"giving Cohen's $d\approx -9$: BKZ wins every seed (0/122)",
             [-9, 0, 122], [cliff["d"], int((cliff["a"] > 0).sum()), cliff["seeds"]], 0, MAIN,
             "Cohen's d, SD-BKZ wins and seed count, n=130 beta=40"),
    ]
    return recs


def _growth_records(gs) -> list[dict]:
    mean = {k: g["mean"] for k, g in gs.items()}
    recs = []
    for row, c in _rows("tab:growth"):
        beta, cells = int(c[0]), c[1:7]
        recs.append(_rec(f"growth_beta{beta}", row, [float(x) for x in cells],
                         [100 * (mean[(n + 10, beta)] / mean[(n, beta)] - 1)
                          for n in range(50, 110, 10)],
                         [1 if "." in x else 0 for x in cells], MAIN,
                         "percent change of the group mean advantage between adjacent n, n=50..110",
                         status="DERIVED"))
    step40 = (mean[(110, 40)] - mean[(130, 40)]) / 2
    drop30 = mean[(100, 30)] - mean[(150, 30)]
    drop20 = mean[(90, 20)] - mean[(150, 20)]
    recs += [
        _rec("beta30_over_beta40_ratio",
             r"$3.8{:}1$. At $n=70$, this ratio has narrowed to $1.5{:}1$, and at $n=80$ it is $1.4{:}1$",
             [3.8, 1.5, 1.4], [mean[(n, 30)] / mean[(n, 40)] for n in (50, 70, 80)], 1, MAIN,
             "beta=30 over beta=40 group mean advantage at n=50, 70, 80", status="DERIVED"),
        _rec("beta40_growth_n50_n80",
             r"($+222\%$) and continued growing to 0.408 at $n=80$ ($+20\%$)",
             [222, 0.408, 20],
             [100 * (mean[(70, 40)] / mean[(50, 40)] - 1), mean[(80, 40)],
              100 * (mean[(80, 40)] / mean[(70, 40)] - 1)], [0, 3, 0], MAIN,
             "beta=40 mean advantage growth n=50 to 70, value at n=80, growth n=70 to 80",
             status="DERIVED"),
        _rec("beta30_jump_n80_n90", r"jumps from 0.580 to 0.922 nats ($+59\%$)",
             [0.580, 0.922, 59],
             [mean[(80, 30)], mean[(90, 30)], 100 * (mean[(90, 30)] / mean[(80, 30)] - 1)],
             [3, 3, 0], MAIN, "beta=30 mean advantage at n=80 and n=90 and the percent change",
             status="DERIVED"),
        _rec("beta40_cliff_steepness",
             r"swing of 2.5 nats in two dimension steps ($n=110$ to $n=130$), $3.6\times$ steeper per step than the $\beta=30$ decline (1.74 nats over five steps) and $11\times$ the $\beta=20$ decline (0.66 nats over six steps)",
             [2.5, 3.6, 1.74, 11, 0.66],
             [2 * step40, step40 / (drop30 / 5), drop30, step40 / (drop20 / 6), drop20],
             [1, 1, 2, 0, 2], MAIN,
             "mean advantage drop n=110 to 130 at beta=40; per-step ratio to the beta=30 drop "
             "n=100 to 150 and the beta=20 drop n=90 to 150", status="DERIVED"),
    ]
    return recs


def _spatial_records(main) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97,
           "field": "rankin_profile_{bkz,sdbkz}"}
    share, mid_win = {}, {}
    for key, seeds in main.items():
        thirds = np.array([_decompose_seed(s) for s in seeds])
        size = np.abs(thirds.mean(axis=0))
        share[key] = [float(x) for x in 100 * size / size.sum()]
        mid_win[key] = 100 * float((thirds[:, 1] > 0).mean())
    recs = []
    for row, c in _rows("tab:spatial"):
        key = (int(c[0]), int(c[1]))
        recs.append(_rec(f"spatial_n{key[0]:03d}_beta{key[1]}", row, [float(x) for x in c[2:]],
                         [len(main[key])] + share[key] + [mid_win[key]], 0, src,
                         "seed count; head, middle, tail share of the summed absolute mean "
                         "improvement by profile third; % of seeds with a positive middle third"))
    shown = [share[k][1] for k in share if k[0] <= 70]
    fav = [k for k in share if k[0] <= FAVOURABLE_MAX_N]
    recs += [
        _rec("spatial_mid_share_range", r"accounts for 44--82\% of the total",
             [44, 82], [min(shown), max(shown)], 0, src,
             "smallest and largest middle-third share over n=50..70", status="DERIVED"),
        _rec("spatial_mid_win_range",
             r"The middle-region win rate is 91--100\% across all favourable groups",
             [91, 100], [min(mid_win[k] for k in fav), max(mid_win[k] for k in fav)], 0, src,
             "smallest and largest middle-third win rate over n=50..110", status="DERIVED"),
        _rec("spatial_mid_dominates", r"favourable regime (21/21 groups)",
             [21, 21], [sum(share[k][1] == max(share[k]) for k in fav), len(fav)], 0, src,
             "groups at n=50..110 whose middle third holds the largest share",
             status="DERIVED"),
    ]
    return recs


def _trajectory_records(main, t3) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97, "field": "crossover_tour"}
    med = {(n, b): float(np.median([s["crossover_tour"] for s in main[(n, b)]]))
           for n in (50, 60, 70, 80) for b in (20, 30, 40)}
    by_beta = {b: [med[(n, b)] for n in (50, 60, 70, 80)] for b in (20, 30, 40)}
    recs = [
        _rec("crossover_tour_range", r"crossover at tour 3--23 depending on parameters",
             [3, 23], [min(med.values()), max(med.values())], 0, src,
             "group median crossover tour, smallest and largest over n=50..80",
             status="DERIVED"),
        _rec("crossover_tour_by_beta",
             r"fastest at $\beta=40$ (tour 3--6) and slowest at $\beta=20$ (tour 16--23)",
             [3, 6, 16, 23],
             [min(by_beta[40]), max(by_beta[40]), min(by_beta[20]), max(by_beta[20])], 0, src,
             "group median crossover tour range over n=50..80, beta=40 then beta=20",
             status="DERIVED"),
        _rec("crossover_tour_beta20_growth",
             r"median 16$\to$23 at $\beta=20$ from $n=50$ to $n=80$",
             [16, 23], [med[(50, 20)], med[(80, 20)]], 0, src,
             "group median crossover tour at n=50 and n=80, beta=20"),
    ]
    for r in recs[:2]:
        r["note"] = "n=50..80 only, the range the sentence discusses"

    def trend(key, var):   # change over the last five tours
        return float(np.mean([s[f"{var}_dln_per_tour"][-1] - s[f"{var}_dln_per_tour"][-5]
                              for s in main[key]]))

    def floor(seeds, var):  # mean absolute per-tour change over the last five steps
        return np.mean([np.abs(np.diff(s[f"{var}_dln_per_tour"][-6:])).mean() for s in seeds])

    ratios = [float(floor(v, "sdbkz") / floor(v, "bkz"))
              for k, v in main.items() if k[0] <= FAVOURABLE_MAX_N]
    src_tour = {"kind": "seeds", "campaign": "main", "q": 97,
                "field": "{bkz,sdbkz}_dln_per_tour"}
    recs += [
        _rec("headroom_trend",
             r"$+0.042$ at $n=100$, $\beta=30$; $+0.027$ at $n=110$, $\beta=20$), while SD-BKZ's trend is smaller ($+0.009$ and $-0.008$ respectively)",
             [0.042, 0.027, 0.009, -0.008],
             [trend((100, 30), "bkz"), trend((110, 20), "bkz"),
              trend((100, 30), "sdbkz"), trend((110, 20), "sdbkz")], 3, src_tour,
             "mean d(LN) at the last tour minus four tours earlier; BKZ then SD-BKZ",
             status="DERIVED"),
        _rec("headroom_floor_ratio", r"ranges from 1.0 to 1.4 across favourable groups",
             [1.0, 1.4], [min(ratios), max(ratios)], 1, src_tour,
             "SD-BKZ over BKZ mean absolute per-tour d(LN) change in the last five steps, "
             "n=50..110", status="DERIVED"),
    ]

    src3 = {"kind": "seeds", "campaign": "tours3x", "q": 97}
    one = {k: st.mean(s["advantage"] for s in main[k]) for k in t3}
    three = {k: st.mean(s["advantage_3x"] for s in v) for k, v in t3.items()}
    move = [100 * (three[(n, 30)] / one[(n, 30)] - 1) for n in (50, 60, 70, 80)]
    b20 = t3[(60, 20)]
    recs += [
        _rec("tours3x_gap_move_pct", r"($-6\%$ to $+5\%$)", [-6, 5], [min(move), max(move)],
             0, src3, "mean advantage_3x against the main-campaign mean advantage, beta=30, "
             "range over n=50..80", status="DERIVED"),
        _rec("tours3x_beta20_closure",
             r"closes 67\% of the gap and wins 26 of 100 seeds",
             [67, 26, 100],
             [100 * (1 - three[(60, 20)] / one[(60, 20)]),
              sum(s["gap_closed"] for s in b20), len(b20)], 0, src3,
             "1 - mean advantage_3x / main-campaign mean advantage; gap_closed count; "
             "seed count, n=60 beta=20", status="DERIVED"),
    ]
    return recs


def _convergence_records() -> list[dict]:
    def load(n, tours):
        bkz, sd, _, _, seeds = _load_convergence_files(n=n, beta=30, max_tours=tours)
        if seeds != 20:
            raise SystemExit(f"convergence n={n} max_tours={tours}: {seeds} seeds, want 20")
        return bkz, sd

    def src(n, tours):
        return {"kind": "seeds", "campaign": "convergence", "q": 97,
                "cells": [f"n{n}_beta30"], "max_tours": tours}

    b90, s90 = load(90, 500)
    b140, s140 = load(140, 500)
    bk, sk = load(140, 1000)
    adv90, adv140, advk = b90 - s90, b140 - s140, (bk - sk)[:, 999]
    recs = [
        _rec("conv_n090_gain_past_70",
             r"improving by only $+0.042$ nats over 430 additional tours. SD-BKZ continues descending throughout, gaining $+0.448$ nats",
             [0.042, 0.448],
             [float((b90[:, 69] - b90[:, 499]).mean()), float((s90[:, 69] - s90[:, 499]).mean())],
             3, src(90, 500), "mean d(LN) at tour 70 minus tour 500, BKZ then SD-BKZ"),
        _rec("conv_n090_advantage",
             r"from $+0.925$ nats at tour 70 (the standard limit) to $+1.331$ nats at tour 500",
             [0.925, 1.331], [float(adv90[:, 69].mean()), float(adv90[:, 499].mean())], 3,
             src(90, 500), "mean BKZ minus SD-BKZ d(LN) at tours 70 and 500"),
        _rec("conv_n140_500",
             r"($+0.122$ vs $+0.099$ nats), widening the gap from $-0.052$ at tour 70 to $-0.075$ at tour 500 ($p=0.002$, 20\% SD-BKZ win rate)",
             [0.122, 0.099, -0.052, -0.075, 0.002, 20],
             [float((b140[:, 69] - b140[:, 499]).mean()),
              float((s140[:, 69] - s140[:, 499]).mean()),
              float(adv140[:, 69].mean()), float(adv140[:, 499].mean()),
              float(stats.ttest_1samp(adv140[:, 499], 0).pvalue),
              100 * float((adv140[:, 499] > 0).mean())], [3, 3, 3, 3, 3, 0], src(140, 500),
             "gain past tour 70 (BKZ, SD-BKZ); mean advantage at tours 70 and 500; paired "
             "t-test p and SD-BKZ win % at tour 500"),
        _rec("conv_n140_1000",
             r"(mean $+0.029$ nats, 95\% CI $[-0.021, +0.079]$, $12/20$",
             [0.029, -0.021, 0.079, 12, 20],
             [float(advk.mean())] + _t_interval(advk) + [int((advk > 0).sum()), len(advk)],
             [3, 3, 3, 0, 0], src(140, 1000),
             "mean advantage at tour 1000, t-interval, SD-BKZ wins and seed count"),
    ]
    gain90, a90, v140, vk = (r["recomputed_value"] for r in recs)
    recs += [
        _rec("cap_conv_n090",
             r"BKZ gains $+0.042$ nats (flat), SD-BKZ gains $+0.448$ nats. The advantage widens from $+0.925$ to $+1.331$",
             [0.042, 0.448, 0.925, 1.331], gain90 + a90, 3, src(90, 500),
             "Figure caption: gain past tour 70 (BKZ, SD-BKZ), advantage at tours 70 and 500"),
        _rec("cap_conv_n140",
             r"BKZ improves $+0.122$ nats vs SD-BKZ $+0.099$ nats; the gap widens slightly to $-0.075$ at $t=500$ (20\% SD-BKZ win); at $t=1000$ this deficit is statistically undetectable ($+0.029$, n.s.",
             [0.122, 0.099, -0.075, 20, 0.029], v140[:2] + [v140[3], v140[5], vk[0]],
             [3, 3, 3, 0, 3], src(140, 1000),
             "Figure caption: gain past tour 70 (BKZ, SD-BKZ), advantage and SD-BKZ win % "
             "at tour 500, advantage at tour 1000"),
    ]
    return recs


def _q3329_records(gs) -> list[dict]:
    src = {"kind": "seeds", "campaign": "q3329_mpfr", "q": 3329, "field": "advantage",
           "manifest": "results/side_seed_manifest.json"}
    cells = load_all_seeds(campaign="q3329_mpfr", q=3329, manifest_path=SIDE_MANIFEST,
                           include_unverified=True)
    recs, ahead, total = [], 0, 0
    for row, c in _rows("tab:q3329"):
        a = np.array([s["advantage"] for s in cells[(int(c[0]), 30)]])
        ahead, total = ahead + int((a > 0).sum()), total + len(a)
        recs.append(_rec(f"q3329_n{int(c[0]):03d}", row,
                         [float(c[1]), float(c[2])] + _floats(c[3]) + _floats(c[4]),
                         [len(a), float(a.mean())] + _t_interval(a) + [int((a > 0).sum()), len(a)],
                         [0, 3, 3, 3, 0, 0], src,
                         "seed count, mean advantage, t-interval, seeds with SD-BKZ ahead"))
    recs += [
        _rec("q3329_ahead_total", r"positive on $299$ of $300$ seeds", [299, 300],
             [ahead, total], 0, src, "seeds with a positive advantage over the three cells"),
        _rec("q3329_q97_comparison",
             r"($+0.58$, $+0.92$ and $+1.35$ nats at $n=80$, $90$ and $100$, $\beta=30$)",
             [0.58, 0.92, 1.35], [gs[(n, 30)]["mean"] for n in (80, 90, 100)], 2, MAIN,
             "q=97 group mean advantage at n=80, 90, 100, beta=30"),
    ]
    return recs


def _runtime_records(main) -> list[dict]:
    """Wall time over seeds 1-100 of every group, the cell the table reports."""
    src = {"kind": "seeds", "campaign": "main", "q": 97, "field": "{bkz,sdbkz}_time",
           "seeds": "1-100"}
    t = {}
    for key, seeds in main.items():
        first = [s for s in seeds if s["seed"] <= 100]
        t[key] = [st.mean(s["bkz_time"] for s in first),
                  st.mean(s["sdbkz_time"] for s in first)]
    ratio = {k: sd / bkz for k, (bkz, sd) in t.items()}
    recs = []
    for row, c in _rows("tab:runtime"):
        key = (int(c[0]), int(c[1]))
        recs.append(_rec(f"runtime_n{key[0]:03d}_beta{key[1]}", row, [_num(x) for x in c[2:]],
                         t[key] + [ratio[key]], [0, 0, 2], src,
                         "mean BKZ and SD-BKZ wall seconds per seed and their ratio"))
    hi, lo = max(ratio, key=ratio.get), min(ratio, key=ratio.get)
    bkz50, sd50 = t[(50, 30)]
    early = [(k, var) for k, seeds in main.items() for s in seeds for var in ("bkz", "sdbkz")
             if s[f"{var}_termination"] != "max_tours_reached"]
    runs = 2 * sum(len(v) for v in main.values())
    recs += [
        _rec("runtime_ratio_range",
             r"ranges from $2.72\times$ ($n=70$, $\beta=30$) to $2.00\times$ ($n=140$, $\beta=20$)",
             [2.72, 70, 30, 2.00, 140, 20], [ratio[hi], *hi, ratio[lo], *lo],
             [2, 0, 0, 2, 0, 0], src, "largest and smallest runtime ratio and their groups",
             status="DERIVED"),
        _rec("runtime_n50_extrapolation",
             r"approximately 1{,}486 seconds, and BKZ at 210 tours extrapolates to 1{,}695 seconds ($3\times 565$), 14\% more",
             [1486, 1695, 565, 14], [sd50, 3 * bkz50, bkz50, 100 * (3 * bkz50 / sd50 - 1)],
             0, src, "SD-BKZ seconds, three times the BKZ seconds, BKZ seconds, % excess; "
             "n=50 beta=30", status="DERIVED"),
        _rec("early_exit_runs",
             r"only 1 of 6{,}776 algorithm runs (a single BKZ run at $n=50$, $\beta=20$)",
             [1, 6776, 50, 20], [len(early), runs, *(early[0][0] if early else (0, 0))], 0,
             {"kind": "seeds", "campaign": "main", "q": 97, "field": "{bkz,sdbkz}_termination"},
             "runs that stopped before the tour limit, all runs, group of the first",
             match=[len(early), runs] == [1, 6776] and early[0] == ((50, 20), "bkz")),
    ]
    return recs


def _hf_records(main, gs) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97, "field": "rhf_advantage"}
    mean = {k: st.mean(s["rhf_advantage"] for s in v) for k, v in main.items()}
    outlier = {k: any(abs(s["rhf_advantage"]) > HF_OUTLIER for s in v)
               for k, v in main.items()}
    recs = []
    for row, c in _rows("tab:main"):
        key = (int(c[0]), int(c[1]))
        recs.append(_rec(f"main_hf_n{key[0]:03d}_beta{key[1]}", row, c[3], mean[key], None, src,
                         "group mean rhf_advantage against the HF column; a star marks a "
                         "group with an outlier seed",
                         match=_sci_matches(c[3], mean[key])
                         and ("\\ast" in row) == outlier[key]))
    clean = [abs(mean[k]) for k in mean if not outlier[k]]
    rhf_win = [100 * float(np.mean([s["rhf_advantage"] > 0 for s in v])) for v in main.values()]
    fav_win = [g["win"] for k, g in gs.items() if k[0] <= FAVOURABLE_MAX_N]
    recs += [
        _rec("rhf_unstarred_bound",
             r"In the 28 unstarred groups, the mean HF difference is at most $2.2\times 10^{-6}$",
             [28, 2.2e-6], [len(clean), max(clean)], None, src,
             "groups with no outlier seed and their largest |group mean rhf_advantage|",
             status="DERIVED",
             match=len(clean) == 28 and _p_matches(r"2.2\times 10^{-6}", max(clean))),
        _rec("rhf_win_range", r"RHF win rates are 42--58\% across all groups", [42, 58],
             [min(rhf_win), max(rhf_win)], 0, src,
             "smallest and largest share of seeds with rhf_advantage > 0", status="DERIVED"),
        _rec("dln_win_range_favourable",
             r"win rates range from 90\% to 100\% at favourable dimensions", [90, 100],
             [min(fav_win), max(fav_win)], 0, MAIN,
             "smallest and largest SD-BKZ win % over n=50..110", status="DERIVED"),
    ]
    return recs


def _gsa_records(main) -> list[dict]:
    src = {"kind": "seeds", "campaign": "main", "q": 97,
           "field": "rankin_profile_{bkz,sdbkz}"}
    ln, gsa, flips = [], [], []
    for (n, beta), seeds in sorted(main.items()):
        ref = np.array(gsa_fixed_point(n + 1, beta))
        g = [float(np.mean(np.abs(np.array(s["rankin_profile_bkz"]) - ref))
                   - np.mean(np.abs(np.array(s["rankin_profile_sdbkz"]) - ref)))
             for s in seeds]
        a = [s["advantage"] for s in seeds]
        ln, gsa = ln + a, gsa + g
        if (st.mean(a) > 0) != (st.mean(g) > 0):
            flips.append((n, beta))
    method = "advantage recomputed against the GSA profile, same mean absolute distance"
    return [
        _rec("gsa_pearson",
             r"Across all 3{,}388 main-sweep seeds (33 groups), the per-seed $d(\mathrm{GSA})$ advantage correlates strongly with $d(\mathrm{LN})$ (Pearson $r=0.89$)",
             [3388, 33, 0.89], [len(ln), len(main), float(stats.pearsonr(ln, gsa)[0])],
             [0, 0, 2], src, method + "; seeds, groups, Pearson r of the per-seed pairs",
             status="DERIVED"),
        _rec("gsa_sign_agreement",
             r"Of the 33 groups, 30 agree on the sign of the mean advantage under both metrics",
             [33, 30], [len(main), len(main) - len(flips)], 0, src,
             method + "; groups whose two mean advantages share a sign", status="DERIVED"),
        _rec("gsa_reversal_groups",
             r"$n=120$ $\beta=40$, $n=140$ $\beta=30$, and $n=150$ $\beta=30$",
             [120, 40, 140, 30, 150, 30], [x for key in flips for x in key], 0, src,
             method + "; groups whose two mean advantages differ in sign", status="DERIVED"),
        _rec("gsa_core_unanimous",
             r"in the core advantage region ($n\leq 110$), agreement is unanimous",
             0, sum(n <= FAVOURABLE_MAX_N for n, _ in flips), 0, src,
             method + "; sign reversals at n<=110", status="DERIVED"),
    ]


def _caption_records(main, gs) -> list[dict]:
    """Numbers printed only in figure captions."""
    def mean(key, field):
        return st.mean(s[field] for s in main[key])

    def thirds(key):
        return np.array([_decompose_seed(s) for s in main[key]]).mean(axis=0)

    def per_pos(key):
        means = _per_position_group_stats(main[key])[0]
        return means, np.linspace(0, 1, len(means))

    rhf = np.array([s["rhf_advantage"] for s in main[(100, 30)]])
    top = max(gs, key=lambda k: gs[k]["d"])
    full30 = [n for n in DIMS if gs[(n, 30)]["win"] == 100]
    through = max(n for n in full30 if all(m in full30 for m in DIMS if m <= n))
    peak = {b: sorted(DIMS, key=lambda n: -gs[(n, b)]["mean"]) for b in (20, 30, 40)}
    mid40 = float(np.mean([thirds((n, 40))[1] for n in (130, 140, 150)]))
    p100, x100 = per_pos((100, 20))
    p150, x150 = per_pos((150, 20))
    prof = {"kind": "seeds", "campaign": "main", "q": 97,
            "field": "rankin_profile_{bkz,sdbkz}"}
    final = {"kind": "seeds", "campaign": "main", "q": 97, "field": "{bkz,sdbkz}_final_dln"}
    recs = [
        _rec("cap_z_scores",
             r"(mean $-0.02\sigma$, coin flip); $d(\mathrm{LN})$ (green) sits $6.24\sigma$ from zero with no overlap (this group; peak effect is $9.6\sigma$ at $n=100$, $\beta=40$)",
             [-0.02, 6.24, 9.6, 100, 40],
             [float(rhf.mean() / rhf.std(ddof=1)), gs[(100, 30)]["d"], gs[top]["d"], *top],
             [2, 2, 1, 0, 0], MAIN,
             "mean over sample std of rhf_advantage and of advantage at n=100 beta=30; "
             "largest such ratio and its group", status="DERIVED"),
        _rec("cap_win_through_n130", r"shows 100\% win rate through $n=130$ before collapsing",
             130, through, 0, MAIN, "largest n up to which every beta=30 group wins 100%",
             status="DERIVED"),
        _rec("cap_hist_beta30",
             r"sits above 0.5 nats with 100\% win rate; by $n=150$, the distribution is entirely negative (0\% win)",
             [0.5, 100, 0],
             [float(gs[(100, 30)]["a"].min()), gs[(100, 30)]["win"], gs[(150, 30)]["win"]],
             0, MAIN, "smallest advantage and win % at n=100, win % at n=150, beta=30",
             status="DERIVED",
             match=gs[(100, 30)]["a"].min() > 0.5
             and [gs[(100, 30)]["win"], gs[(150, 30)]["win"]] == [100, 0]),
        _rec("cap_hist_beta40",
             r"over three times larger: $n=130$ shows mean $-1.325$ nats with no overlap with zero",
             [3, -1.325, 0],
             [gs[(130, 40)]["mean"] / gs[(150, 30)]["mean"], gs[(130, 40)]["mean"],
              float(gs[(130, 40)]["a"].max())], 3, MAIN,
             "mean at n=130 beta=40 over mean at n=150 beta=30; that mean; its largest "
             "advantage", status="DERIVED",
             match=gs[(130, 40)]["mean"] / gs[(150, 30)]["mean"] > 3
             and _matches(gs[(130, 40)]["mean"], -1.325, 3) and gs[(130, 40)]["a"].max() < 0),
        _rec("cap_spatial_mid_beta30", r"the middle peaks at $n=100$--$110$ ($+1.9$ to $+2.0$ nats)",
             [1.9, 2.0], [float(thirds((100, 30))[1]), float(thirds((110, 30))[1])], 1, prof,
             "mean middle-third improvement at n=100 and n=110, beta=30", status="DERIVED"),
        _rec("cap_spatial_mid_beta40", r"the middle carries most of the loss (about $-2.8$ nats)",
             -2.8, mid40, 1, prof,
             "mean middle-third improvement averaged over n=130, 140, 150, beta=40",
             status="DERIVED"),
        _rec("cap_profiles_n150", r"SD-BKZ is the further of the two ($-0.395$ nats)",
             -0.395, gs[(150, 30)]["mean"], 3, MAIN, "group mean advantage, n=150 beta=30"),
        _rec("cap_peak_dimensions",
             r"$\beta=20$ peaks at $n=90$, $\beta=30$ at $n=100$, and $\beta=40$ at $n=100$--$110$",
             [90, 100, 100, 110], [peak[20][0], peak[30][0], *sorted(peak[40][:2])], 0, MAIN,
             "dimension of the largest group mean at beta=20 and 30; the two largest at "
             "beta=40", status="DERIVED"),
        _rec("cap_cliff_swing", r"a swing of 2.5 nats in two dimension steps",
             2.5, gs[(110, 40)]["mean"] - gs[(130, 40)]["mean"], 1, MAIN,
             "group mean at n=110 minus n=130, beta=40", status="DERIVED"),
        _rec("cap_abs_dln_beta20", r"(${\sim}15$ nats at $n=120$)", [15, 15],
             [mean((120, 20), "bkz_final_dln"), mean((120, 20), "sdbkz_final_dln")], 0, final,
             "mean final d(LN), BKZ then SD-BKZ, n=120 beta=20"),
        _rec("cap_abs_dln_beta40", r"(SD-BKZ ${\sim}12.4$ vs BKZ ${\sim}11.1$)", [12.4, 11.1],
             [mean((150, 40), "sdbkz_final_dln"), mean((150, 40), "bkz_final_dln")], 1, final,
             "mean final d(LN), SD-BKZ then BKZ, n=150 beta=40"),
        _rec("cap_abs_dln_cross", r"the curves cross at $n=120$", 120,
             min(n for n in DIMS if gs[(n, 40)]["mean"] < 0), 0, MAIN,
             "smallest n with a negative group mean advantage at beta=40", status="DERIVED"),
        _rec("cap_scatter_cliff",
             r"$n=110$ ($+1.16$ at $\beta/n=0.36$) drops to $n=130$ ($-1.32$ at $\beta/n=0.31$) and $n=140$ ($-1.45$ at $\beta/n=0.29$)",
             [1.16, 0.36, -1.32, 0.31, -1.45, 0.29],
             [x for n in (110, 130, 140) for x in (gs[(n, 40)]["mean"], 40 / n)], 2, MAIN,
             "group mean advantage and beta/n at n=110, 130, 140, beta=40"),
        _rec("cap_perpos_dip_position", r"the dip (position $0.88$ at $n=100$, $0.59$ at $n=150$)",
             [0.88, 0.59], [float(x100[p100.argmin()]), float(x150[p150.argmin()])], 2, prof,
             "fractional position of the smallest mean per-position improvement, beta=20",
             status="DERIVED"),
        _rec("cap_perpos_beta30",
             r"the peak improvement reaches $+2.5$~nats at $n=100$ while the dip reaches $-2.3$~nats at $n=150$",
             [2.5, -2.3], [float(per_pos((100, 30))[0].max()), float(per_pos((150, 30))[0].min())],
             1, prof, "largest mean per-position improvement at n=100, smallest at n=150, "
             "beta=30", status="DERIVED"),
        _rec("cap_q3329_q97_panel", r"122 seeds, mean $+1.349$ nats", [122, 1.349],
             [gs[(100, 30)]["seeds"], gs[(100, 30)]["mean"]], [0, 3], MAIN,
             "seed count and group mean advantage, q=97 n=100 beta=30"),
    ]

    cell = load_all_seeds(campaign="q3329", n=100, beta=30, q=3329, precision=1000,
                          max_tours=70)[(100, 30)]
    floored = [s for s in cell if s["seed"] <= 100 and min(
        min(s["gs_lognorms_bkz"]), min(s["gs_lognorms_sdbkz"])) < FLOOR_LOGNORM]
    adv = [s["advantage"] for s in floored]
    worst = max(floored, key=lambda s: max(s["bkz_dln_per_tour"] + s["sdbkz_dln_per_tour"]))
    spikes = [x for x in worst["bkz_dln_per_tour"] + worst["sdbkz_dln_per_tour"] if x > 20]
    src = {"kind": "seeds", "campaign": "q3329", "q": 3329, "cells": ["n100_beta30"],
           "seeds": "1-100", "measurement": "double"}
    recs += [
        _rec("cap_q3329_floored",
             r"the 38 seeds with a measurement floor scatter across $\pm 170$ nats",
             [38, -170, 170], [len(floored), min(adv), max(adv)], [0, -1, -1], src,
             f"seeds with a stored log-norm below {FLOOR_LOGNORM}; their smallest and "
             "largest advantage", status="DERIVED"),
        _rec("cap_q3329_spikes", r"it spikes to 105--337 nats", [105, 337],
             [min(spikes), max(spikes)], 0, src,
             "per-tour d(LN) above 20 nats, smallest and largest, in the floored seed "
             "with the highest spike", status="DERIVED"),
    ]
    return recs


def build() -> dict:
    main = load_all_seeds(campaign="main", q=97)
    t3 = load_all_seeds(campaign="tours3x")
    gs = _group_stats(main)
    records = (_advantage_records(main) + [_n110_paired_record(main)]
               + _rhf_records(main) + _tours3x_records(t3) + _figure8_records(main)
               + _group_table_records(gs) + _stats_records(gs) + _growth_records(gs)
               + _spatial_records(main) + _trajectory_records(main, t3)
               + _convergence_records() + _q3329_records(gs)
               + _runtime_records(main) + _hf_records(main, gs) + _gsa_records(main)
               + _caption_records(main, gs))
    for r in records:
        if r["claim_id"] in CAPTION_ECHO:
            r["tex_anchors"].append(CAPTION_ECHO[r["claim_id"]])
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
