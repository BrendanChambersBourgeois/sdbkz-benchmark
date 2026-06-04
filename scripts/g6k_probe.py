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
    same machine / -march=x86-64-v3 build
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


def probe(n: int, beta: int, seed: int, threads: int = 1) -> dict:
    """Run the contract-locked probe and return its hash record.

    Raises SystemExit(3) if threads != 1 — the contract forbids it.
    """
    if threads != 1:
        PIPELINE.error(
            "threads>1 rejected (G6K MT sieve is nondeterministic)",
            cat="integrity", threads=threads,
        )
        raise SystemExit(3)

    try:
        from fpylll import FPLLL, LLL, IntegerMatrix
        from fpylll.tools.bkz_stats import dummy_tracer
        from g6k import Siever, SieverParams
        from g6k.algorithms.bkz import pump_n_jump_bkz_tour
    except ImportError as e:
        PIPELINE.error("g6k/fpylll import failed", cat="integrity", err=str(e))
        raise SystemExit(2)

    # Fixed input basis.
    FPLLL.set_random_seed(seed)
    A = IntegerMatrix.random(n, "qary", k=n // 2, bits=DEFAULT_BITS)
    LLL.reduction(A)

    # Contract-locked sieve. The sieve's sampler draws from fplll's global
    # RNG, so re-seeding FPLLL immediately before the sieve is what fixes the
    # sieve RNG. (SieverParams has NO "seed" key in fpylll e25ade8 / g6k
    # c71e084 — setting one is a silently-ignored no-op that emits
    # "Attribute 'seed' unknown"; verified 2026-06-04. Do not reintroduce.)
    params = SieverParams(threads=1)
    FPLLL.set_random_seed(seed)  # re-seed immediately before the sieve
    g6k = Siever(A, params)
    pump_n_jump_bkz_tour(g6k, dummy_tracer, beta,
                         pump_params={"down_sieve": True})

    # Hash basis + r-profile independently (either drifting is a failure).
    B = g6k.M.B
    basis_bytes = str(
        [[B[i][j] for j in range(B.ncols)] for i in range(B.nrows)]
    ).encode()
    g6k.M.update_gso()
    rprof = [g6k.M.get_r(i, i) for i in range(n)]
    rprof_bytes = json.dumps([f"{x:.10e}" for x in rprof]).encode()

    rec = {
        "engine": "g6k",
        "n": n, "beta": beta, "seed": seed, "threads": 1,
        "march": "x86-64-v3",
        "basis_sha256": _sha(basis_bytes),
        "rprof_sha256": _sha(rprof_bytes),
        "r0": f"{rprof[0]:.10e}",
    }
    PIPELINE.info("probe done", cat="integrity",
                  n=n, beta=beta, seed=seed,
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
    ap.add_argument("--json", action="store_true",
                    help="print only the JSON record to stdout")
    args = ap.parse_args()

    rec = probe(args.n, args.beta, args.seed, args.threads)
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
