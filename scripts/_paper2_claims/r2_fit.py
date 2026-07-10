#!/usr/bin/env python3
"""Paper-2 claims ledger slice 4a: R^2 = 0.957 per-position slope-flattening fit.

Claim (sdbkz_paper2.tex:604 + fig caption :621): the per-position SD-BKZ vs BKZ
profile-difference redistribution at n=89, beta=40 is "~96% predicted by slope
flattening alone (R^2=0.957)".

This is a PROSE/CAPTION-ONLY number. `analysis/plots/ntru_per_position.py` reads
the same gs_lognorms_{bkz,sdbkz} data but computes NO fit and holds NO literal
0.957 (finding 6 item 7.6). This module reproduces the exact data selection of
ntru_per_position.py (`_per_position_mean`: same glob, same `_fat` exclusion,
same shape guard, per-position mean over seeds of sd-bkz), then attempts to
reproduce 0.957 via the documented "pure slope-flattening" single-parameter
linear-in-position model d_i ~ a*(i - ibar) (intercept ~0 by determinant
conservation), plus the two refinements the plan lists (tail-restrict i>=n;
BKZ-profile-slope predictor).

RESULT: no principled recipe reproduces 0.957 to <=0.001. The number is
underdetermined -- engine choice / q-band / tail-restriction each swing it
across 0.94-0.96. See build_records()[0]["note"] for the full candidate table.
Per the plan Step 4a mandate, this is recorded match=false / DERIVED-UNRESOLVED
rather than shipping a different R^2 as if it were the paper value.

Exposes build_records() -> list[dict] (ledger schema). Read-only on
results/seeds/. Run directly to print the candidate landscape + the record.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

# Repo root: this module lives in a scratchpad; the seed tree is the live repo.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (scripts/_paper2_claims/ -> up 3)
N, BETA = 89, 40

# The figure's q-sweep (ntru_per_position.QS) and the text's pre-onset band.
FIG_QS = [97, 127, 137, 149, 157, 181, 211]        # ntru_per_position.py:23
PREONSET_BAND = [127, 131, 137, 139, 149, 151, 157]  # text: q in [127,157]
PREONSET_IN_FIG = [127, 137, 149, 157]               # band members shown in fig
ENGINE_TREE = {"fplll": "ntru", "g6k": "ntru_g6k"}


def _per_position_mean(tag: str, q: int):
    """Byte-identical to analysis/plots/ntru_per_position._per_position_mean:
    mean over seeds of (gs_lognorms_sdbkz - gs_lognorms_bkz) per position.
    Returns (mean_diff, mean_bkz, nseed) or (None, None, 0)."""
    paths = [p for p in glob.glob(
        os.path.join(REPO, "results", "seeds", tag, f"q{q}", "*",
                     f"n{N:03d}_beta{BETA}", "seed*.json"))
        if "_fat" not in p]
    diffs, bkzs = [], []
    for p in paths:
        d = json.load(open(p))
        if "gs_lognorms_bkz" in d and "gs_lognorms_sdbkz" in d:
            bkz = np.asarray(d["gs_lognorms_bkz"], dtype=float)
            sd = np.asarray(d["gs_lognorms_sdbkz"], dtype=float)
            if bkz.shape == sd.shape:
                diffs.append(sd - bkz)
                bkzs.append(bkz)
    if not diffs:
        return None, None, 0
    return (np.mean(np.vstack(diffs), axis=0),
            np.mean(np.vstack(bkzs), axis=0), len(diffs))


def _r2(d: np.ndarray, pred: np.ndarray) -> float:
    """R^2 = 1 - SS_res/SS_tot, SS_tot about the mean of d."""
    d = np.asarray(d, float)
    return 1.0 - ((d - pred) ** 2).sum() / ((d - d.mean()) ** 2).sum()


def _fit_r2(d, i, b=None, predictor="position", tail=False):
    """Fit the single-parameter slope-flattening model and return R^2.

    predictor='position'  -> d_i ~ a*(i - ibar) + c   (plain linear-in-i)
    predictor='bkzslope'  -> d_i ~ a*(bkz_i - mean)+c (BKZ-profile predictor)
    tail=True             -> restrict to reduced tail i >= n
    Free intercept c is fit but ~0 by determinant conservation (checked in
    __main__); it does not change R^2 vs a zero-intercept fit to >4 decimals.
    """
    d = np.asarray(d, float)
    i = np.asarray(i, float)
    if tail:
        m = i >= N
        d, i = d[m], i[m]
        if b is not None:
            b = np.asarray(b, float)[m]
    if predictor == "position":
        x = i - i.mean()
    else:
        b = np.asarray(b, float)
        x = b - b.mean()
    A = np.vstack([x, np.ones_like(x)]).T
    coef, *_ = np.linalg.lstsq(A, d, rcond=None)
    return _r2(d, A @ coef)


def _band_average(tags, qs):
    """Average the per-position mean-difference curves over engines x q into a
    single 'per-position signal' curve of length 2n, plus the matching mean BKZ
    profile. Returns (curve, bkz_curve)."""
    diffs, bkzs = [], []
    for t in tags:
        for q in qs:
            m, b, ns = _per_position_mean(t, q)
            if m is not None:
                diffs.append(m)
                bkzs.append(b)
    return np.mean(np.vstack(diffs), axis=0), np.mean(np.vstack(bkzs), axis=0)


def candidate_landscape() -> dict[str, float]:
    """Enumerate the documented recipes for the R^2 and return {label: value}.
    Every recipe uses the exact ntru_per_position data path; they differ only
    in engine selection, q-band, predictor, and tail-restriction -- all of
    which are left unspecified by the prose."""
    out = {}
    engsel = {"fplll": ["ntru"], "g6k": ["ntru_g6k"],
              "both": ["ntru", "ntru_g6k"]}
    qsel = {"band[127,157]": PREONSET_BAND, "band-in-fig": PREONSET_IN_FIG,
            "q137": [137], "fig-QS(all)": FIG_QS}
    for en, tags in engsel.items():
        for qn, qs in qsel.items():
            curve, bkz = _band_average(tags, qs)
            i = np.arange(len(curve), dtype=float)
            for pred in ("position", "bkzslope"):
                for tail in (False, True):
                    lbl = f"{en} | {qn} | {pred} | tail={int(tail)}"
                    out[lbl] = round(
                        _fit_r2(curve, i, bkz, predictor=pred, tail=tail), 5)
    return out


# --- the primary, most-defensible "plain" recipe -----------------------------
# Plan Step 4a first recipe: per-position mean difference over the q-sweep,
# both engines (the fig/text emphasise both engines AGREE), full pre-onset band,
# plain linear-in-position d_i ~ a*(i - ibar), free intercept, R^2 about mean.
PRIMARY_LABEL = "both | band[127,157] | position | tail=0"

PAPER_VALUE = 0.957
TOL = 0.001


def build_records() -> list[dict]:
    land = candidate_landscape()
    primary = land[PRIMARY_LABEL]
    # closest principled candidate to the paper value, for the honesty note
    closest_lbl = min(land, key=lambda k: abs(land[k] - PAPER_VALUE))
    closest_val = land[closest_lbl]
    match = bool(abs(primary - PAPER_VALUE) <= TOL)

    # candidate table sorted by distance to target, top few
    ranked = sorted(land.items(), key=lambda kv: abs(kv[1] - PAPER_VALUE))
    table = "; ".join(f"{lbl}={val:.4f}" for lbl, val in ranked)

    note = (
        "PROSE/CAPTION-ONLY number (sdbkz_paper2.tex:604,621); no code or "
        "committed file contains 0.957 (finding 6 item 7.6). Data path is "
        "byte-identical to analysis/plots/ntru_per_position._per_position_mean "
        "(same glob, _fat exclusion, shape guard, per-position mean over 100 "
        "seeds/cell of gs_sdbkz-gs_bkz). The 'pure slope-flattening' model "
        "d_i ~ a*(i - ibar) (intercept ~0 by determinant conservation) does "
        "NOT reproduce 0.957 to <=0.001 under any documented recipe: the value "
        "is underdetermined and scatters across 0.94-0.96 with engine/q-band/"
        "tail choice. Closest principled candidate: "
        f"'{closest_lbl}'={closest_val:.4f} (rounds to "
        f"{closest_val:.3f}, |delta|={abs(closest_val-PAPER_VALUE):.4f}). "
        f"Primary plain recipe ('{PRIMARY_LABEL}')={primary:.4f}. Tried both "
        "documented refinements (i) tail-restrict i>=n and (ii) BKZ-profile-"
        "slope predictor -- neither lands within tol. Full candidate landscape "
        f"[{table}]. Per plan Step 4a, recording DERIVED-UNRESOLVED rather "
        "than shipping a different R^2 as the paper number; needs a human call "
        "on the exact engine/band the author used (or the tex value is an "
        "unbacked ~ estimate)."
    )

    rec = {
        "claim_id": "per_position_slope_flatten_r2",
        "tex_lines": [604, 621],
        "verbatim": ("a fit to pure slope-flattening explains ~96% of the "
                     "per-position signal (R^2=0.957)"),
        "paper_value": PAPER_VALUE,
        "source": {
            "kind": "seeds",
            "glob": ("results/seeds/{ntru,ntru_g6k}/q*/*/n089_beta40/"
                     "seed*.json"),
            "field": "gs_lognorms_sdbkz - gs_lognorms_bkz (per-position mean "
                     "over seeds)",
            "data_path": "analysis/plots/ntru_per_position._per_position_mean",
        },
        "method": ("per-position mean diff d_i over q-sweep; single-parameter "
                   "slope-flattening fit d_i ~ a*(i - ibar); "
                   "R^2 = 1 - SS_res/SS_tot"),
        "recomputed_value": round(primary, 4),
        "match": match,
        "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED",
        "note": note,
    }
    return [rec]


if __name__ == "__main__":
    print("Candidate R^2 landscape (all use the ntru_per_position data path):")
    land = candidate_landscape()
    for lbl, val in sorted(land.items(), key=lambda kv: -kv[1]):
        flag = "  <== target 0.957" if abs(val - PAPER_VALUE) <= TOL else ""
        print(f"  {val:.4f}  {lbl}{flag}")
    # intercept sanity: confirm det-conservation makes intercept ~0
    curve, bkz = _band_average(["ntru", "ntru_g6k"], PREONSET_BAND)
    i = np.arange(len(curve), dtype=float)
    x = i - i.mean()
    A = np.vstack([x, np.ones_like(x)]).T
    coef, *_ = np.linalg.lstsq(A, curve, rcond=None)
    print(f"\nintercept of primary plain fit = {coef[1]:.5f} (mean d_i = "
          f"{curve.mean():.5f}); ~0 confirms determinant conservation")
    print()
    for r in build_records():
        print(json.dumps(r, indent=2))
