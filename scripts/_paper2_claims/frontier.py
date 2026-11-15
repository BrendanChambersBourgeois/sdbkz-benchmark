#!/usr/bin/env python3
"""Paper-2 claims ledger -- FRONTIER slice (sec:frontier, tab:frontier).

Rebuilds the tab:frontier recovery counts, 50%-crossing onsets (in units of
q_fat(n) = 0.004 n^2.484) and the paired McNemar lines from the seed JSONs,
scored by secret_exact_match_{variant} as the tex states. Cells group by
(tree, n, beta, max_tours), so 50/200/580-tour runs at one q never pool.
Wall-capped seeds leave no JSON, so counts are over completed seeds, as in
the table. Engine g6k_reject is the reject-on-overflow G6K build (tree
ntru_g6k_reject, the table's double-dagger rows); g6k is the tolerant
build. Read-only on results/seeds/.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal
from itertools import pairwise

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "scripts"))
from extract_dsd_onset import _interp_onset  # noqa: E402

from _paper2_claims.recomputed import _sign_p_two_sided  # noqa: E402

TREE = {"fplll": "ntru", "g6k": "ntru_g6k", "g6k_reject": "ntru_g6k_reject"}

# (engine, n, beta, tours, SD, BKZ, tex anchors). Pooled "k/N" over the
# ladder, or per-cell "k/N, ..." in ascending q where the table lists cells.
COUNTS = [
    ("fplll", 167, 40, 50, "116/560", "49/560", [r"$116/560$, peak $40\%$ & $49/560$"]),
    ("fplll", 167, 40, 580, "7/8", "6/8", [r"$7/8$ (p.) & $6/8$ (p.)"]),
    ("g6k", 167, 40, 50, "9/80", "2/80", [r"$9/80$ & $2/80$"]),
    ("fplll", 173, 40, 50, "7/280", "4/280", [r"$7/280$, peak $10\%$ & $4/280$"]),
    ("g6k", 173, 40, 50, "3/80", "1/80", [r"$3/80$ & $1/80$"]),
    ("fplll", 179, 40, 50, "0/100", "0/100", [r"$0/100$ & $0/100$"]),
    ("g6k", 179, 40, 50, "0/80", "0/80", [r"$0/80$ & $0/80$", r"turn $0/80$ into $2/20$ and $0/20$"]),
    ("g6k", 179, 40, 200, "2/20", "0/20", [r"G6K$^\S$ & 2.91 (1) & 20 & $2/20$ & $0/20$", r"turn $0/80$ into $2/20$ and $0/20$"]),
    ("g6k", 179, 40, 580, "6/20", "1/20", [r"$6/20$ & $1/20$", r"then $6/20$ and $1/20$"]),   # line D (dagger); wall clause
    ("fplll", 181, 40, 50, "0/120", "0/120", [r"$0/120$ & $0/120$"]),
    ("g6k", 179, 50, 50, "33/100", "17/100", [r"179 & 50 & G6K & 2.00--3.22 (5) & 20 & onset $2.54\times$, $33/100$ & $17/100$"]),
    ("g6k", 181, 50, 50, "41/180", "17/180", [r"$41/180$, plateau $35$--$50\%$ & $17/180$"]),
    ("g6k", 183, 50, 50, "1/6", "0/6", [r"183 & 50 & G6K & 2.75 (1) & 6 & $1/6$ (p.) & $0/6$ (p.)"]),
    ("g6k", 185, 50, 50, "2/21", "1/21", [r"$2/21$ (p., 1 c.) & $1/21$ (p., 1 c.)"]),
    ("g6k", 179, 60, 50, "6/6", "6/6", [r"$6/6$ (p.) & $6/6$ (p.)"]),
    ("g6k", 181, 60, 50, "0/4, 3/20, 4/4, 5/5", "0/4, 1/20, 4/4, 5/5",
     [r"$0/4$, $3/20$, $4/4$, $5/5$", r"$0/4$, $1/20$, $4/4$, $5/5$"]),
    ("g6k", 185, 60, 50, "0/4, 18/18, 2/2", "0/4, 15/18, 2/2",
     [r"$0/4$, $18/18$, $2/2$, --", r"$0/4$, $15/18$, $2/2$, --"]),
    # Reject build: full-row anchors, since the n179/n181 rows read as the tolerant ones
    ("g6k_reject", 179, 60, 50, "6/6", "6/6",
     [r"179 & 60 & G6K$^\ddagger$ & 2.00 (1) & 6 & $6/6$ (p.) & $6/6$ (p.)"]),
    ("g6k_reject", 181, 60, 50, "0/4, 3/20, 4/4, 5/5", "0/4, 1/20, 4/4, 5/5",
     [r"181 & 60 & G6K$^\ddagger$ & 1.36--2.83 (4) & 4--20 & $0/4$, $3/20$, $4/4$, $5/5$; onset"]),
    ("g6k_reject", 185, 60, 50, "0/4, 20/20, 4/4, 4/4", "0/4, 19/20, 4/4, 4/4",
     [r"$0/4$, $20/20$, $4/4$, $4/4$", r"$0/4$, $19/20$, $4/4$, $4/4$"]),
    ("g6k_reject", 179, 50, 50, "33/100", "17/100",
     [r"179 & 50 & G6K$^\ddagger$ & 2.00--3.22 (5) & 20 & onset $2.54\times$, $33/100$ & $17/100$"]),
    ("g6k_reject", 181, 50, 50, "43/180", "15/180", [r"$43/180$, plateau $35$--$55\%$ & $15/180$"]),
    ("g6k_reject", 183, 50, 50, "1/6", "0/6",
     [r"183 & 50 & G6K$^\ddagger$ & 2.75 (1) & 6 & $1/6$ (p.) & $0/6$ (p.)"]),
    ("g6k_reject", 185, 50, 50, "1/21", "0/21", [r"$1/21$ (p.) & $0/21$ (p.)"]),
]

# (engine, n, beta, tours, variant, onset / q_fat as printed, tex anchors).
# "none" is the tex reading "no crossing" (the peak rate is printed instead).
ONSETS = [
    ("fplll", 157, 40, 50, "sdbkz", 2.06, [r"onset $2.06\times$, peak $99\%$"]),
    ("fplll", 157, 40, 50, "bkz", 2.30, [r"onset $2.30\times$, to $87\%$"]),
    ("fplll", 163, 40, 50, "sdbkz", 2.47, [r"onset $2.47\times$, peak $75\%$"]),
    ("fplll", 163, 40, 50, "bkz", "none", [r"none, peak $40\%$"]),
    ("g6k", 179, 50, 50, "sdbkz", 2.54, [r"179 & 50 & G6K & 2.00--3.22 (5) & 20 & onset $2.54\times$, $33/100$"]),
    ("g6k_reject", 179, 50, 50, "sdbkz", 2.54,
     [r"179 & 50 & G6K$^\ddagger$ & 2.00--3.22 (5) & 20 & onset $2.54\times$"]),
    ("g6k", 181, 60, 50, "sdbkz", 1.78, [r"onset $1.78\times$"]),
    ("g6k", 181, 60, 50, "bkz", 1.80, [r"onset $1.80\times$"]),
    ("g6k", 185, 60, 50, "sdbkz", 2.06, [r"onset $2.06\times$"]),
    ("g6k", 185, 60, 50, "bkz", 2.11, [r"onset $2.11\times$"]),
    ("g6k_reject", 181, 60, 50, "sdbkz", 1.78,
     [r"181 & 60 & G6K$^\ddagger$ & 1.36--2.83 (4) & 4--20 & $0/4$, $3/20$, $4/4$, $5/5$; onset $1.78\times$"]),
    ("g6k_reject", 181, 60, 50, "bkz", 1.80,
     [r"G6K$^\ddagger$ & 1.36--2.83 (4) & 4--20 & $0/4$, $3/20$, $4/4$, $5/5$; onset $1.78\times$ & $0/4$, $1/20$, $4/4$, $5/5$; onset $1.80\times$"]),
    ("g6k_reject", 185, 60, 50, "sdbkz", 2.06, [r"$4/4$, $4/4$; onset $2.06\times$"]),
    ("g6k_reject", 185, 60, 50, "bkz", 2.08, [r"onset $2.08\times$"]),
]

# (engine, n, beta, tours, "SD-only:BKZ-only", exact two-sided p as printed, tex anchors)
MCNEMAR = [
    ("fplll", 157, 40, 50, "160:9", "7e-37",
     [r"$160$:$9$ at $n=157$ (exact", r"McNemar $p=7\times10^{-37}$)"]),
    ("fplll", 163, 40, 50, "134:29", "2e-17", [r"$134$:$29$ at $n=163$", r"$p=2\times10^{-17}$"]),
    ("fplll", 167, 40, 50, "101:34", "7e-9", [r"$101$:$34$ at $n=167$ ($p=7\times10^{-9}$)"]),
    ("g6k", 167, 40, 50, "9:2", "0.065", [r"(G6K $n=167$: $9$:$2$,", r"$p=0.065$)"]),
    ("g6k", 179, 50, 50, "25:9", "0.009", [r"$25$:$9$ at $n=179$ ($p=0.009$)"]),
    ("g6k", 181, 50, 50, "34:10", "4e-4", [r"$34$:$10$ at $n=181$", r"($p=4\times10^{-4}$"]),
    ("g6k_reject", 181, 50, 50, "37:9", "4e-5", [r"become $37$:$9$ ($p=4\times10^{-5}$)"]),
]


def q_fat(n: int) -> float:
    return 0.004 * n ** 2.484


def _glob(engine, n, beta, tours):
    return (f"results/seeds/{TREE[engine]}/q*/p*_mt{tours}/"
            f"n{n:03d}_beta{beta:02d}/seed*.json")


def _ladder(engine, n, beta, tours):
    """[(q, [(sd_exact, bkz_exact) per completed seed])], ascending q."""
    cells = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(BASE, _glob(engine, n, beta, tours)))):
        with open(f) as fh:
            d = json.load(fh)
        q = int(re.search(r"/q(\d+)/", f).group(1))
        sd, bk = d["secret_exact_match_sdbkz"], d["secret_exact_match_bkz"]
        if sd is None or bk is None:  # a null is a missing readout, not a failed recovery
            raise ValueError(f"{f}: secret_exact_match field is null")
        cells[q].append((bool(sd), bool(bk)))
    return sorted(cells.items())


def _rec(cid, anchors, verbatim, paper, src, method, value, match, note):
    return {"claim_id": cid, "tex_anchors": anchors, "verbatim": verbatim,
            "paper_value": paper, "source": {"kind": "seeds", "glob": src},
            "method": method, "recomputed_value": value, "match": match,
            "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED", "note": note}


def build_records() -> list[dict]:
    recs = []
    for eng, n, beta, tours, sd_p, bkz_p, anchors in COUNTS:
        lad = _ladder(eng, n, beta, tours)
        for i, var, paper in ((0, "sd", sd_p), (1, "bkz", bkz_p)):
            if "," in paper:
                value = ", ".join(f"{sum(s[i] for s in v)}/{len(v)}" for _, v in lad)
            else:
                value = (f"{sum(s[i] for _, v in lad for s in v)}/"
                         f"{sum(len(v) for _, v in lad)}")
            recs.append(_rec(
                f"frontier_count_n{n}_b{beta}_mt{tours}_{eng}_{var}", anchors,
                f"tab:frontier n={n} beta={beta} {eng} {tours} tours {var}: {paper}",
                paper, _glob(eng, n, beta, tours),
                "secret_exact_match legs over completed seeds, "
                + ("per q-cell" if "," in paper else "pooled over the ladder"),
                value, value == paper, f"q-cells {[q for q, _ in lad]}."))
    for eng, n, beta, tours, var, paper, anchors in ONSETS:
        i = 0 if var == "sdbkz" else 1
        curve = [(q, sum(s[i] for s in v) / len(v)) for q, v in _ladder(eng, n, beta, tours)]
        onset, how = _interp_onset(curve, 0.5)
        value = round(onset / q_fat(n), 2) if onset else None
        note = f"onset q={onset} ({how})."
        if isinstance(paper, str):
            # Tex reads no crossing; match only if the tool agrees. A cell at
            # exactly 50% counts as a crossing in _interp_onset (r >= rate).
            peak = max(r for _, r in curve)
            value = {"onset_x": value, "onset_q": onset, "peak_rate": peak}
            match = onset is None
            if not match:
                note += (f" The tex reads this ladder as no crossing (peak "
                         f"{peak:.0%}); _interp_onset finds one. Rates by q: {curve}.")
        else:
            match = value == paper
        recs.append(_rec(
            f"frontier_onset_n{n}_b{beta}_{eng}_{'sd' if i == 0 else 'bkz'}", anchors,
            f"tab:frontier n={n} beta={beta} {eng} {var} onset "
            + (paper if isinstance(paper, str) else f"{paper}x q_fat"),
            paper, _glob(eng, n, beta, tours),
            "extract_dsd_onset._interp_onset (50%) over per-q exact-match rates, "
            "divided by q_fat(n)=0.004 n^2.484, 2 dp",
            value, match, note))
    for eng, n, beta, tours, paper, p_txt, anchors in MCNEMAR:
        legs = [s for _, v in _ladder(eng, n, beta, tours) for s in v]
        b = sum(1 for sd, bk in legs if sd and not bk)
        c = sum(1 for sd, bk in legs if bk and not sd)
        p = _sign_p_two_sided(b, c)
        p_paper = float(p_txt)
        half = 0.5 * 10.0 ** Decimal(p_txt).as_tuple().exponent   # half a printed unit
        recs.append(_rec(
            f"frontier_mcnemar_n{n}_b{beta}_{eng}", anchors,
            f"paired SD-only:BKZ-only {paper} at n={n} beta={beta} {eng}, p={p_txt}",
            {"counts": paper, "p": p_paper}, _glob(eng, n, beta, tours),
            "paired legs over the ladder; exact two-sided McNemar "
            "(recomputed._sign_p_two_sided)",
            {"counts": f"{b}:{c}", "p": p},
            f"{b}:{c}" == paper and abs(p - p_paper) <= half,
            f"{len(legs)} paired seeds."))
    return recs


# --- Prefix-volume collapse (not a tex claim; written beside the ledger) -----

def _collapsed(lognorms, n: int) -> bool:
    """Prefix-only dense-sublattice test: the first n Gram-Schmidt log-norms
    have mean within 0.5 of 0.5 ln(4n/3). Uses no suffix value, so a floored
    suffix cannot hide or fake a collapse."""
    return sum(lognorms[:n]) / n - 0.5 * math.log(4 * n / 3) < 0.5


def _collapse_tour(initial_dln, dln_per_tour):
    """1-based tour of the collapse step in d(LN), or None when no single step
    stands out. A clean leg has one rise of 140 nats or more and no other
    reaching a quarter of it; a leg whose per-tour values flicker (double-measured
    cells) has several of similar size and no readable collapse tour."""
    seq = [initial_dln] + list(dln_per_tour)
    steps = [b - a for a, b in pairwise(seq)]
    top = max(steps)
    if sum(s >= top / 4 for s in steps) != 1:
        return None
    return steps.index(top) + 1


def _net_sign(clusters) -> dict:
    """Sign test over (n, seed) keys: one vote per key, by its net direction."""
    a = sum(sd > bk for sd, bk in clusters.values())
    b = sum(bk > sd for sd, bk in clusters.values())
    return {"sd_net_keys": a, "bkz_net_keys": b, "p": _sign_p_two_sided(a, b)}


def prefix_volume(n_min: int = 157) -> dict:
    """Collapse discordance SD-BKZ vs BKZ on the frontier trees, every leg
    scored from its prefix (no leg dropped), per tree with no cross-build
    dedupe. Equal tours: both legs at their stored end. Equal wall: each leg
    is collapsed only if its collapse tour, at that leg's mean time per tour,
    falls inside the shorter leg's wall time; pairs with a collapsed leg whose
    collapse tour is unreadable are left out and counted; time per tour is
    taken as constant within a leg. Keys repeat across
    q, beta and build, so the sign tests vote once per (n, seed)."""
    out, vol = {}, defaultdict(list)
    for eng, tree in TREE.items():
        cells = defaultdict(lambda: defaultdict(int))
        clus = {"tours": defaultdict(lambda: [0, 0]), "wall": defaultdict(lambda: [0, 0])}
        pat = os.path.join(BASE, f"results/seeds/{tree}/q*/p*_mt*/n*_beta*/seed*.json")
        for f in sorted(glob.glob(pat)):
            n, beta = map(int, re.search(r"/n(\d+)_beta(\d+)/", f).groups())
            if n < n_min:
                continue
            with open(f) as fh:
                d = json.load(fh)
            c = cells[f"n{n}_b{beta}_mt{d['max_tours']}"]
            key = (n, d["seed"])
            col, tc, per_tour = {}, {}, {}
            for v in ("sdbkz", "bkz"):
                ln = d[f"gs_lognorms_{v}"]
                if len(ln) != 2 * n or min(ln[:n]) < -100:
                    raise ValueError(f"{f}: {v} prefix log-norms unusable")
                col[v] = _collapsed(ln, n)
                if col[v]:
                    vol[key].append(sum(ln[:n]) / n)
                    tc[v] = _collapse_tour(d["initial_dln"], d[f"{v}_dln_per_tour"])
                per_tour[v] = d[f"{v}_time"] / len(d[f"{v}_dln_per_tour"])
            c["pairs"] += 1
            c["sd_collapsed"] += col["sdbkz"]
            c["bkz_collapsed"] += col["bkz"]
            modes = {"tours": col}
            if any(col[v] and tc[v] is None for v in col):
                c["wall_pairs_dropped"] += 1
            else:
                wall = min(d["sdbkz_time"], d["bkz_time"])
                modes["wall"] = {v: col[v] and tc[v] * per_tour[v] <= wall for v in col}
            for mode, m in modes.items():
                if m["sdbkz"] != m["bkz"]:
                    side = 0 if m["sdbkz"] else 1
                    c[f"{mode}_{'sd' if side == 0 else 'bkz'}_only"] += 1
                    clus[mode][key][side] += 1
        fields = ("pairs", "sd_collapsed", "bkz_collapsed", "tours_sd_only", "tours_bkz_only",
                  "wall_pairs_dropped", "wall_sd_only", "wall_bkz_only")
        rows = {k: {x: v[x] for x in fields} for k, v in sorted(cells.items())}
        total = {x: sum(r[x] for r in rows.values()) for x in fields}
        out[eng] = {"tree": tree, "cells": rows, "total": total,
                    "tours_sign_test": _net_sign(clus["tours"]),
                    "wall_sign_test": _net_sign(clus["wall"])}
    spreads = sorted(max(v) - min(v) for v in vol.values() if len(v) > 1)
    out["volume_check"] = {  # one key, one sublattice: ln vol(prefix)/n must agree
        "keys_with_two_or_more_collapsed_legs": len(spreads),
        "max_spread": spreads[-1] if spreads else None,
        "keys_spread_above_1e-3": sum(s > 1e-3 for s in spreads)}
    return out
