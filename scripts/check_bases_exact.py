#!/usr/bin/env python3
"""Exact (all-integer) checks on per-tour bases saved by q3329_verify --store-bases.

For every basis B in each .npz (init, every bkz and
sdbkz tour) the integral Gram-Schmidt of B (Cohen, Alg. 2.6.7) gives exact
integers d_0 = 1, d_{i+1} = d_i * |b_i*|^2 and lambda_ij = d_{j+1} * mu_ij.
No floating point is involved, so each verdict below is exact:

  full_rank   every d_i > 0 (no r_ii <= 0; the floors came from a double
              measurement GSO, so a stock-fplll basis must pass)
  det_eq      d_n(B) == d_n(L), i.e. |det B| == |det L| (BKZ kept the lattice volume)
  size_ok     |mu_ij| <= eta for j < i:  100 |lambda_ij| <= 51 d_{j+1}  (eta = 0.51)
  lovasz_ok   delta r_{k-1} <= r_k + mu_{k,k-1}^2 r_{k-1}:
              99 d_k^2 <= 100 (d_{k+1} d_{k-1} + lambda_{k,k-1}^2)    (delta = 0.99)

eta and delta are fplll's LLL defaults, the values the run's meta records. Each
record also carries the margins as floats (max_mu, lovasz_min = min over k of
(r_k + mu^2 r_{k-1}) / r_{k-1}) so near-misses are visible, not just verdicts.
A failure is data to read, not automatically an fplll bug: an SD-BKZ dual tour
need not end LLL-reduced.

usage: check_bases_exact.py PATH [PATH ...] --out OUT.jsonl [--workers N] [--final-only]
PATH is an .npz or a directory searched recursively. OUT gets one record per
basis and one {"file_done": ...} per file; files already done in OUT are skipped,
so an interrupted run resumes. --final-only checks just the last bkz and sdbkz
basis of each file; give it its own OUT, since a file it marks done
would be skipped by a later full run on the same OUT.
"""
import argparse
import json
import os
import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("check_bases_exact")
ETA = Fraction(51, 100)
DELTA = Fraction(99, 100)


def _gram(B):
    """Exact Gram matrix as Python ints (int64 only when it cannot overflow)."""
    B = np.asarray(B, dtype=np.int64)
    if int(np.abs(B).max()) ** 2 * B.shape[1] < 2**62:
        return (B @ B.T).tolist()
    rows = [[int(x) for x in r] for r in B]
    return [[sum(a * b for a, b in zip(ri, rj, strict=True)) for rj in rows] for ri in rows]


def integral_gso(B):
    """(d, lam): d[0] = 1, d[i+1] = det of the leading (i+1)x(i+1) Gram minor,
    lam[i][j] = d[j+1] * mu_ij for j < i. Exact; stops at the first d <= 0
    (rank defect), returning the d computed so far."""
    G = _gram(B)
    n = len(G)
    d = [1]
    lam = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            u = G[i][j]
            for k in range(j):
                u = (d[k + 1] * u - lam[i][k] * lam[j][k]) // d[k]
            if j < i:
                lam[i][j] = u
            else:
                d.append(u)
                if u <= 0:
                    return d, lam
    return d, lam


def check_basis(B, dn_ref):
    """Exact verdicts plus float margins for one basis against the reference
    d_n (= det(L)^2)."""
    d, lam = integral_gso(B)
    n = len(B)
    rec = {"full_rank": len(d) == n + 1 and d[-1] > 0}
    if not rec["full_rank"]:
        rec["first_nonpos_row"] = len(d) - 2
        return rec
    rec["det_eq"] = d[n] == dn_ref
    max_mu, size_bad = Fraction(0), 0
    for i in range(n):
        for j in range(i):
            if 100 * abs(lam[i][j]) > 51 * d[j + 1]:
                size_bad += 1
            mu = Fraction(abs(lam[i][j]), d[j + 1])
            if mu > max_mu:
                max_mu = mu
    lov_min, lov_at, lov_bad = None, None, 0
    for k in range(1, n):
        lhs = d[k + 1] * d[k - 1] + lam[k][k - 1] ** 2   # (r_k + mu^2 r_{k-1}) d_k d_{k-1}
        if 100 * lhs < 99 * d[k] ** 2:
            lov_bad += 1
        ratio = Fraction(lhs, d[k] ** 2)
        if lov_min is None or ratio < lov_min:
            lov_min, lov_at = ratio, k
    rec.update(size_ok=size_bad == 0, size_violations=size_bad, max_mu=float(max_mu),
               lovasz_ok=lov_bad == 0, lovasz_violations=lov_bad,
               lovasz_min=float(lov_min), lovasz_min_at=lov_at)
    return rec


def check_file(path, final_only=False):
    """All bases in one .npz (or only the last bkz/sdbkz tour); returns (records, summary)."""
    z = np.load(path)
    meta = json.loads(str(z["meta"]))
    L = z["L"]
    d_ref, _ = integral_gso(L)
    if not (len(d_ref) == len(L) + 1 and d_ref[-1] > 0):
        raise ValueError(f"{path}: reference L is rank-deficient")
    dn_ref = d_ref[-1]
    recs = []
    for leg in ("bkz", "sdbkz") if final_only else ("init", "bkz", "sdbkz"):
        bases = list(enumerate(z[leg]))
        for i, B in bases[-1:] if final_only else bases:
            r = check_basis(B, dn_ref)
            recs.append({"file": path, "n": meta["n"], "beta": meta["beta"],
                         "seed": meta["seed"], "leg": leg, "tour": 0 if leg == "init" else i + 1,
                         **r})
    bad = [r for r in recs if not (r["full_rank"] and r["det_eq"] and r["size_ok"] and r["lovasz_ok"])]
    return recs, {"file_done": path, "bases": len(recs), "failing": len(bad),
                  "failing_legs": sorted({r["leg"] for r in bad})}


def _files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                out += [os.path.join(root, f) for f in names if f.endswith(".npz")
                        and not f.endswith(".tmp.npz")]
        else:
            out.append(p)
    return sorted(out)


def _safe_check(path, final_only=False):
    try:
        return path, check_file(path, final_only), None
    except Exception as e:  # noqa: BLE001
        return path, None, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--final-only", action="store_true", help="last bkz and sdbkz basis per file only")
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            done = {json.loads(line).get("file_done") for line in f if '"file_done"' in line}
    todo = [p for p in _files(a.paths) if p not in done]
    PIPELINE.info("exact basis check start", cat="analysis", files=len(todo),
                  skipped_done=len(done), out=a.out, workers=a.workers, final_only=a.final_only)
    totals = {"files": 0, "bases": 0, "failing": 0, "errors": 0}
    import functools
    import multiprocessing as mp
    with open(a.out, "a") as out, mp.get_context("fork").Pool(max(1, a.workers)) as pool:
        for path, res, err in pool.imap_unordered(functools.partial(_safe_check, final_only=a.final_only), todo):
            if err is not None:
                totals["errors"] += 1
                PIPELINE.error("exact basis check failed", cat="analysis", file=path, error=err)
                continue
            recs, summ = res
            for r in recs:
                out.write(json.dumps(r) + "\n")
            out.write(json.dumps(summ) + "\n")
            out.flush()
            totals["files"] += 1
            totals["bases"] += summ["bases"]
            totals["failing"] += summ["failing"]
            if summ["failing"]:
                PIPELINE.warning("bases fail exact check", cat="analysis", **summ)
    PIPELINE.info("exact basis check done", cat="analysis", out=a.out, **totals)
    print(json.dumps(totals))
    return 1 if totals["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
