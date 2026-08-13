#!/usr/bin/env python3
"""Deterministic G6K sieve probe — the byte-identity unit the g6k path
SHA-locks against.

Generates a fixed q-ary lattice from FPLLL.set_random_seed(seed), LLL-
reduces it, runs ONE pump_n_jump_bkz_tour under the Phase-0 determinism
contract, and emits SHA-256 of the reduced basis + the GSO r-profile.

Determinism contract (Phase 0 verdict, 2026-06-04 — non-negotiable):

    threads == 1                      # MT sieve is a nondeterministic race
    FPLLL.set_random_seed(seed)       # fixes the input basis
    FPLLL.set_random_seed(seed) again # before the sieve: the g6k sampler
                                      # draws from fplll's global RNG, so
                                      # this fixes the sieve RNG. (There is
                                      # NO SieverParams["seed"] knob in this
                                      # build — it is a no-op; see below.)
    same machine / -march=x86-64-v2 build
    default sieve params

threads > 1 is REJECTED (SystemExit 3), not warned: a multi-threaded run
that happened to be hashed would silently poison the reference. This is
NOT the science path (no advantage/d(LN) metric here) — it is the
reproducibility tripwire for the engine itself.

CLI:
    python3 g6k_probe.py --n 80 --beta 60 --seed 42 [--json]
Exit: 0 ok · 2 import/build failure · 3 threads>1 contract violation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("g6k_probe")

# Sieve params held at library defaults; pinned here so the determinism
# contract is self-describing rather than implicit in upstream defaults.
DEFAULT_BITS = 20  # q-ary bit size for IntegerMatrix.random


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def probe(n: int, beta: int, seed: int, threads: int = 1,
          tours: int = 1, reseed: str = "once") -> dict:
    """Run the contract-locked probe and return its hash record.

    Raises SystemExit(3) if threads != 1 — the contract forbids it.

    ``tours`` runs that many pump_n_jump_bkz tours (default 1 = the original
    single-tour contract; tours=1, reseed="once" reproduces the locked
    reference cf22519d… / d4faf05a…). ``tours>1`` is the multi-tour
    determinism gate (ADR-007 Gate 1): a real reduction is N tours, not one.

    ``reseed`` is the multi-tour re-seed POLICY under test:
      - "once"     — FPLLL.set_random_seed(seed) once, before tour 1 (the
                     backend does this at construction). The RNG stream then
                     runs continuously across tours, like a normal reduction.
      - "per-tour" — re-seed before EVERY tour. Resets the sampler stream
                     each tour. Artificial, but tested for completeness.
    Determinism = a policy reproduces its own SHA across independent runs.
    """
    if threads != 1:
        PIPELINE.error(
            "threads>1 rejected (G6K MT sieve is nondeterministic)",
            cat="integrity", threads=threads,
        )
        raise SystemExit(3)
    if reseed not in ("once", "per-tour"):
        raise SystemExit(f"unknown reseed policy {reseed!r}")

    try:
        from _engine_backends import make_backend
        from fpylll import FPLLL, LLL, IntegerMatrix
    except ImportError as e:
        PIPELINE.error("g6k/fpylll import failed", cat="integrity", err=str(e))
        raise SystemExit(2)

    # Fixed input basis.
    FPLLL.set_random_seed(seed)
    A = IntegerMatrix.random(n, "qary", k=n // 2, bits=DEFAULT_BITS)
    LLL.reduction(A)

    # Contract-locked sieve, driven through the SAME backend the science
    # engine (_bkz_core.run_single) uses — so this exact-SHA gate covers the
    # backend code path. The g6k backend re-seeds FPLLL immediately before
    # constructing the Siever (the sampler draws from fplll's global RNG)
    # and runs pump_n_jump_bkz_tour under threads=1. (SieverParams has
    # NO "seed" key in fpylll e25ade8 / g6k c71e084 — a no-op; do not
    # reintroduce. Verified 2026-06-04.)
    engine = make_backend("g6k", B_init=A, beta=beta, variant="bkz",
                          seed=seed, precision=0)
    for t in range(tours):
        # Backend __init__ already re-seeded before tour 0. Under "per-tour"
        # re-seed again before each subsequent tour.
        if reseed == "per-tour" and t > 0:
            engine.reseed(seed)
        engine.tour()

    # Hash basis + r-profile independently (either drifting is a failure).
    M = engine.gso()  # update_gso() already applied by the backend
    B = M.B
    basis_bytes = str(
        [[B[i][j] for j in range(B.ncols)] for i in range(B.nrows)]
    ).encode()
    rprof = [M.get_r(i, i) for i in range(n)]
    rprof_bytes = json.dumps([f"{x:.10e}" for x in rprof]).encode()

    rec = {
        "engine": "g6k",
        "n": n, "beta": beta, "seed": seed, "threads": 1,
        "tours": tours, "reseed": reseed,
        "march": "x86-64-v2",
        "basis_sha256": _sha(basis_bytes),
        "rprof_sha256": _sha(rprof_bytes),
        "r0": f"{rprof[0]:.10e}",
    }
    PIPELINE.info("probe done", cat="integrity",
                  n=n, beta=beta, seed=seed, tours=tours, reseed=reseed,
                  basis_sha=rec["basis_sha256"][:12],
                  rprof_sha=rec["rprof_sha256"][:12])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=80, help="lattice dimension")
    ap.add_argument("--beta", type=int, default=60, help="BKZ blocksize")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=1,
                    help="contract requires 1; >1 is rejected")
    ap.add_argument("--tours", type=int, default=1,
                    help="pump_n_jump tours (1 = single-tour reference)")
    ap.add_argument("--reseed", choices=("once", "per-tour"), default="once",
                    help="multi-tour re-seed policy (ADR-007 Gate 1)")
    ap.add_argument("--json", action="store_true",
                    help="print only the JSON record to stdout")
    args = ap.parse_args()

    rec = probe(args.n, args.beta, args.seed, args.threads,
                tours=args.tours, reseed=args.reseed)
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
