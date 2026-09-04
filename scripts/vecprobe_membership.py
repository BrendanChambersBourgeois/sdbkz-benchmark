#!/usr/bin/env python3
"""Vecprobe membership: are the stored short vectors inside the secret's rotation span?

Pure analysis -- reads seeds written with ``store_short_vectors = true`` (the
``ntru_g6k_vecprobe`` tree), never runs a reduction.

Question answered (the "DSD without SKR" reading): a non-exact leg at the
n>=173 frontier ends with basis rows of norm^2 in the 10-20k band, far below
q^2 and far above the secret. Are those rows integer combinations of the
cyclic rotations of the planted secret s = (g, f) -- i.e. vectors of the dense
sublattice L(g, f) that just are not the key itself -- or are they unrelated
lattice vectors outside that sublattice?

Method (exact arithmetic throughout):
  * Regenerate (f, g) from the seed's (n, q, seed) via generators.build_ntru
    and check ||(g, f)||^2 against the seed's recorded secret_norm2.
  * For each stored row v = (v_g | v_f), the rotation span is
    {(a*g, a*f) : a in Z[x]/(x^n - 1)}. Solve a = v_g * g^-1 over Q[x]/(x^n-1)
    (falling back to f^-1, then to an exact rational rref on the 2n x n rotation
    matrix when neither is invertible over Q). Then
      in_qspan  <=>  a*f == v_f            (v lies in the Q-span of the rotations)
      in_zspan  <=>  in_qspan and a integral (v lies in the Z-span, i.e. L(g, f))
    is_secret_rotation is the same +/- cyclic-rotation test _bkz_core uses.
  * cross_norm2 = ||v_g*f - v_f*g mod (x^n-1)||^2 (integer; 0 iff in_qspan when
    g or f is invertible over Q) and qspan_residual_frac (float least squares,
    ||v - proj(v)||^2 / ||v||^2) say how far an outside vector is from the span.

Output: a human table on stdout, a byte-stable JSON (sorted keys, no
timestamps) at --output, and pipeline.jsonl events via scripts/log.py.

Usage:
  python3 scripts/vecprobe_membership.py                      # whole vecprobe tree
  python3 scripts/vecprobe_membership.py --n 179 --q 4591     # one cell
  python3 scripts/vecprobe_membership.py --no-write           # table only
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from fractions import Fraction
from typing import Any

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("vecprobe_membership")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RESULTS_ROOT = os.path.join(REPO, "results", "seeds")
DEFAULT_TREE = "ntru_g6k_vecprobe"
DEFAULT_OUTPUT = os.path.join(REPO, "results", "analysis", "vecprobe_membership.json")
LEGS = ("bkz", "sdbkz")


# --- exact polynomial arithmetic in Q[x]/(x^n - 1) ---------------------------

def _cyc_mul(a: list, b: list, n: int) -> list:
    """Cyclic convolution (product mod x^n - 1); exact for int or Fraction."""
    out = [0] * n
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            if bj == 0:
                continue
            out[(i + j) % n] += ai * bj
    return out


def _rotate(vec: list[int], n: int, i: int) -> list[int]:
    """Multiply by x^i in Z[x]/(x^n - 1): index k takes vec[(k - i) mod n]."""
    return [vec[(k - i) % n] for k in range(n)]


def _rotate_pair(g: list[int], f: list[int], n: int, i: int) -> list[int]:
    """x^i * (g, f): both halves rotated together (the _bkz_core convention)."""
    return _rotate(g, n, i) + _rotate(f, n, i)


def _is_unit(p: list[int], n: int) -> bool:
    """True iff p is invertible in Q[x]/(x^n - 1), i.e. gcd(p, x^n - 1) = 1."""
    from sympy import ZZ, Poly, gcd, symbols

    x = symbols("x")
    P = Poly(list(reversed([int(c) for c in p])), x, domain=ZZ)
    M = Poly([1] + [0] * (n - 1) + [-1], x, domain=ZZ)
    return gcd(P, M).degree() == 0


def _cyc_inverse(p: list[int], n: int) -> list[Fraction] | None:
    """Exact inverse of p in Q[x]/(x^n - 1) as Fractions, or None if not a unit.

    Slow (tens of seconds at n=179): call only through RotationSpan, which
    caches it per key and needs it only for a Q-span vector whose float
    solution did not round to an exact integer certificate.
    """
    from sympy import QQ, Poly, symbols
    from sympy.polys.polyerrors import NotInvertible

    x = symbols("x")
    P = Poly(list(reversed([int(c) for c in p])), x, domain=QQ)
    M = Poly([1] + [0] * (n - 1) + [-1], x, domain=QQ)
    try:
        inv = P.invert(M)
    except NotInvertible:
        return None
    coeffs = [Fraction(int(c.numerator), int(c.denominator))
              for c in reversed(inv.all_coeffs())]
    return coeffs + [Fraction(0)] * (n - len(coeffs))


def _solve_rref(g: list[int], f: list[int], v: list[int], n: int) -> dict[str, Any]:
    """General fallback: exact rational rref on the 2n x n rotation matrix.

    Used only when neither g nor f is a unit over Q (for prime n that means
    g(1) = f(1) = 0, where the n rotations are linearly dependent). Returns
    in_qspan, in_zspan (None = undetermined), a (Fractions) and kernel_dim.
    """
    from sympy import QQ
    from sympy.polys.matrices import DomainMatrix

    rows = []
    for k in range(2 * n):
        src, kk = (g, k) if k < n else (f, k - n)
        rows.append([QQ(src[(kk - i) % n]) for i in range(n)] + [QQ(v[k])])
    rref, pivots = DomainMatrix(rows, (2 * n, n + 1), QQ).rref()
    if n in pivots:
        return {"in_qspan": False, "in_zspan": False, "a": None, "kernel_dim": None}
    a = [Fraction(0)] * n
    rr = rref.to_Matrix()
    for r, c in enumerate(pivots):
        a[c] = Fraction(int(rr[r, n].p), int(rr[r, n].q))
    kernel_dim = n - len(pivots)
    if kernel_dim == 0:
        integral: bool | None = all(x.denominator == 1 for x in a)
    elif kernel_dim == 1 and sum(g) == 0 and sum(f) == 0:
        # Kernel is the all-ones direction: a + t*1 is integral for some t iff
        # all pairwise differences are integers. Pick the shortest such a.
        integral = all((x - a[0]).denominator == 1 for x in a)
        if integral:
            best = [x - a[0] for x in a]
            for i in range(n):
                cand = [x - a[i] for x in a]
                if sum(c * c for c in cand) < sum(c * c for c in best):
                    best = cand
            a = best
    else:
        integral = None
    return {"in_qspan": True, "in_zspan": integral, "a": a, "kernel_dim": kernel_dim}


class RotationSpan:
    """Per-key precompute for membership tests against L(g, f) = Z-span of x^i (g, f)."""

    def __init__(self, g: list[int], f: list[int], n: int):
        self.n = n
        self.g = [int(c) for c in g]
        self.f = [int(c) for c in f]
        self.s = self.g + self.f
        rots: set[tuple[int, ...]] = set()
        for i in range(n):
            r = _rotate_pair(self.g, self.f, n, i)
            rots.add(tuple(r))
            rots.add(tuple(-c for c in r))
        self.rots = rots
        # Which polynomial to invert: g first (a = v_g * g^-1), else f, else rref.
        if _is_unit(self.g, n):
            self.unit, self.unit_poly = "g", self.g
        elif _is_unit(self.f, n):
            self.unit, self.unit_poly = "f", self.f
        else:
            self.unit, self.unit_poly = None, None
        self.unit_fft = np.fft.fft(np.array(self.unit_poly, dtype=float)) if self.unit else None
        self._unit_inv: list[Fraction] | None = None
        # 2n x n float matrix of rotations (columns) for the least-squares residual.
        self.R = np.array([_rotate_pair(self.g, self.f, n, i) for i in range(n)],
                          dtype=float).T

    def exact_inverse(self) -> list[Fraction]:
        if self._unit_inv is None:
            self._unit_inv = _cyc_inverse(self.unit_poly, self.n)
        return self._unit_inv

    def float_solve(self, v_half: list[int]) -> tuple[list[int], float]:
        """Round(a) from the FFT solve a = v_half * unit^-1, and its max distance to Z."""
        a = np.fft.ifft(np.fft.fft(np.array(v_half, dtype=float)) / self.unit_fft).real
        return [int(x) for x in np.round(a)], float(np.max(np.abs(a - np.round(a))))


def classify(v: list[int], g: list[int], f: list[int], n: int,
             span: RotationSpan | None = None) -> dict[str, Any]:
    """Exact membership verdict for one lattice vector v = (v_g | v_f).

    in_zspan is True only with an integer certificate a verified by exact
    convolution; it is False only after an exact rational solve showed a
    non-integral a (or an exact test showed v outside the Q-span).
    """
    if len(v) != 2 * n:
        raise ValueError(f"vector length {len(v)} != 2n = {2 * n}")
    span = span or RotationSpan(g, f, n)
    g, f = span.g, span.f
    v = [int(c) for c in v]
    v_g, v_f = v[:n], v[n:]
    norm2 = sum(c * c for c in v)
    is_rot = tuple(v) in span.rots

    # cross = v_g*f - v_f*g mod (x^n - 1); zero on the Q-span when g or f is a unit.
    cross = [p - q for p, q in zip(_cyc_mul(v_g, f, n), _cyc_mul(v_f, g, n), strict=True)]
    cross_norm2 = sum(c * c for c in cross)

    a: list | None = None
    kernel_dim: int | None = 0
    frac_dist: float | None = None
    if span.unit is not None:
        in_qspan = cross_norm2 == 0
        if in_qspan:
            a_int, frac_dist = span.float_solve(v_g if span.unit == "g" else v_f)
            if _cyc_mul(a_int, g, n) == v_g and _cyc_mul(a_int, f, n) == v_f:
                a, in_zspan = a_int, True                       # exact certificate
            else:
                inv = span.exact_inverse()
                a = _cyc_mul(v_g if span.unit == "g" else v_f, inv, n)
                in_zspan = all(x.denominator == 1 for x in a)
                if in_zspan:
                    a = [int(x) for x in a]
        else:
            in_zspan = False
    else:
        sol = _solve_rref(g, f, v, n)
        in_qspan, in_zspan, kernel_dim = sol["in_qspan"], sol["in_zspan"], sol["kernel_dim"]
        a = sol["a"]
        if in_zspan and a is not None:
            a = [int(x) for x in a]

    # Float distance to the rotation span (0 on members); least squares on R.
    vf = np.array(v, dtype=float)
    coef, *_ = np.linalg.lstsq(span.R, vf, rcond=None)
    resid = vf - span.R @ coef
    resid_frac = float(resid @ resid / (vf @ vf)) if norm2 else 0.0

    rec: dict[str, Any] = {
        "norm2": norm2,
        "is_secret_rotation": is_rot,
        "in_qspan": bool(in_qspan),
        "in_zspan": in_zspan,
        "kernel_dim": kernel_dim,
        "cross_norm2": cross_norm2,
        "qspan_residual_frac": round(resid_frac, 9),
        "float_frac_dist": None if frac_dist is None else round(frac_dist, 9),
        "a_nnz": None, "a_norm2": None, "a_maxabs": None, "a_sum": None,
        "a_denominator_lcm": None,
    }
    if a is not None and in_zspan:
        rec["a_nnz"] = sum(1 for x in a if x)
        rec["a_norm2"] = sum(x * x for x in a)
        rec["a_maxabs"] = max(abs(x) for x in a)
        rec["a_sum"] = sum(a)
    elif a is not None and in_qspan:
        lcm = 1
        for x in a:
            lcm = lcm * x.denominator // math.gcd(lcm, x.denominator)
        rec["a_denominator_lcm"] = lcm
    return rec


# --- seed-level driver ---------------------------------------------------------

def analyze_seed(path: str) -> dict[str, Any] | None:
    """Classify every stored short vector of one seed JSON; None if it stores none."""
    from generators import build_ntru

    with open(path) as fh:
        sj = json.load(fh)
    legs = [leg for leg in LEGS if f"short_vectors_{leg}" in sj]
    if not legs:
        return None
    n, q, seed = int(sj["n"]), int(sj["q"]), int(sj["seed"])
    _, f_np, g_np = build_ntru(n, q, seed=seed)
    f = [int(c) for c in f_np]
    g = [int(c) for c in g_np]
    secret_norm2 = sum(c * c for c in g) + sum(c * c for c in f)
    rec: dict[str, Any] = {
        "path": os.path.relpath(path, REPO),
        "n": n, "q": q, "beta": int(sj.get("beta", 0)), "seed": seed,
        "secret_norm2": secret_norm2,
        "secret_norm2_json": sj.get("secret_norm2"),
        "g_sum": sum(g), "f_sum": sum(f),
        "vectors": [],
    }
    if sj.get("secret_norm2") is not None and int(sj["secret_norm2"]) != secret_norm2:
        # Regeneration disagrees with the run: never classify against the wrong key.
        PIPELINE.error("secret regeneration mismatch", cat="analysis", path=rec["path"],
                       regenerated=secret_norm2, recorded=sj["secret_norm2"])
        rec["secret_mismatch"] = True
        return rec
    span = RotationSpan(g, f, n)
    for leg in legs:
        for rank, (norm2_json, coords) in enumerate(sj[f"short_vectors_{leg}"]):
            c = classify(coords, g, f, n, span)
            if c["norm2"] != int(norm2_json):
                PIPELINE.error("stored norm2 disagrees with coords", cat="analysis",
                               path=rec["path"], leg=leg, rank=rank,
                               stored=norm2_json, computed=c["norm2"])
            c.update({"leg": leg, "rank": rank,
                      "norm2_over_secret": round(c["norm2"] / secret_norm2, 4)})
            rec["vectors"].append(c)
    return rec


def _summarise(seeds: list[dict[str, Any]]) -> dict[str, Any]:
    vecs = [v for s in seeds for v in s.get("vectors", [])]
    non_exact = [v for v in vecs if not v["is_secret_rotation"]]
    return {
        "seeds": len(seeds),
        "seeds_secret_mismatch": sum(1 for s in seeds if s.get("secret_mismatch")),
        "vectors": len(vecs),
        "secret_rotations": sum(1 for v in vecs if v["is_secret_rotation"]),
        "non_exact_vectors": len(non_exact),
        "non_exact_in_zspan": sum(1 for v in non_exact if v["in_zspan"] is True),
        "non_exact_in_qspan_only": sum(1 for v in non_exact
                                       if v["in_qspan"] and v["in_zspan"] is not True),
        "non_exact_outside_qspan": sum(1 for v in non_exact if not v["in_qspan"]),
        "non_exact_undetermined": sum(1 for v in non_exact if v["in_zspan"] is None),
    }


def _print_table(seeds: list[dict[str, Any]]) -> None:
    hdr = ("seed", "leg", "rk", "norm2", "x_sec", "rot", "Qspan", "Zspan",
           "a_nnz", "a_max", "a_sum", "cross2", "resid_frac")
    print(" ".join(f"{h:>8}" for h in hdr))
    for s in seeds:
        for v in s.get("vectors", []):
            row = (s["seed"], v["leg"], v["rank"], v["norm2"], v["norm2_over_secret"],
                   int(v["is_secret_rotation"]), int(v["in_qspan"]),
                   "?" if v["in_zspan"] is None else int(v["in_zspan"]),
                   v["a_nnz"] if v["a_nnz"] is not None else "-",
                   v["a_maxabs"] if v["a_maxabs"] is not None else "-",
                   v["a_sum"] if v["a_sum"] is not None else "-",
                   v["cross_norm2"], v["qspan_residual_frac"])
            print(" ".join(f"{str(c):>8}" for c in row))


def _find_seeds(root: str, tree: str, n: int | None, q: int | None,
                beta: int | None) -> list[str]:
    pat = os.path.join(root, tree, f"q{q}" if q else "q*", "p*_mt*",
                       f"n{n:03d}_beta{beta:02d}" if (n and beta) else
                       (f"n{n:03d}_beta*" if n else "n*_beta*"), "seed*.json")
    return sorted(glob.glob(pat))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", default=DEFAULT_RESULTS_ROOT)
    ap.add_argument("--tree", default=DEFAULT_TREE)
    ap.add_argument("--n", type=int)
    ap.add_argument("--q", type=int)
    ap.add_argument("--beta", type=int)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--no-write", action="store_true", help="table only, no JSON")
    args = ap.parse_args(argv)

    paths = _find_seeds(args.results_root, args.tree, args.n, args.q, args.beta)
    PIPELINE.info("membership start", cat="analysis", tree=args.tree, candidates=len(paths))
    seeds: list[dict[str, Any]] = []
    for p in paths:
        rec = analyze_seed(p)
        if rec is None:
            continue
        seeds.append(rec)
        vs = rec.get("vectors", [])
        PIPELINE.info("seed classified", cat="analysis", path=rec["path"], seed=rec["seed"],
                      vectors=len(vs),
                      in_zspan=sum(1 for v in vs if v["in_zspan"] is True),
                      rotations=sum(1 for v in vs if v["is_secret_rotation"]))
    summary = _summarise(seeds)
    _print_table(seeds)
    print("summary:", json.dumps(summary, sort_keys=True))
    PIPELINE.info("membership done", cat="analysis", tree=args.tree, **summary)
    if not args.no_write:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as fh:
            json.dump({"tree": args.tree, "summary": summary, "seeds": seeds},
                      fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {os.path.relpath(args.output, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
