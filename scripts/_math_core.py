"""Canonical numerical helpers for the SD-BKZ benchmark.

v1.2 consolidation target. Holds the pure-math helpers that are
duplicated across `sweep_parallel.py`, `sweep_cloud.py`, and
`q3329_verify.py` (per the 2026-04-17 code_complexity audit).

Roadmap (each phase is its own commit on `v1.2-consolidation`):

  Phase 1 (DONE)  — Add canonical `ln_fixed_point` here. Legacy copies
                    untouched. Parity test in
                    `scripts/test_math_core_parity.py` proves
                    bit-identity across a 60-pair (n, β) grid.
  Phase 2 (DONE)  — Swap three legacy `ln_fixed_point` defs out for
                    `from _math_core import ln_fixed_point`. Verified
                    bit-identical n=50 β=20 seed 1 via `verify.sh`.
  Phase 3 (DONE)  — Add `build_lwe_kannan` here. Swap six legacy
                    copies (all six were already byte-identical per
                    SHA-256 check) out for `from _math_core import
                    build_lwe_kannan`. Same verify.sh gate.
  Phase 4 (TODO)  — `_metrics_from_gso` is not extract-clean: the
                    four legacy copies diverge materially. sweep_cloud
                    uses a distinct `_log_clamp_cloud` log target;
                    q3329_verify adds a nonlocal `n_clamped` counter;
                    overnight_experiments differs only cosmetically.
                    Extraction requires an interface parameter for the
                    log sink and a return for the clamp counter.
                    Deferred until the interface is designed — do not
                    bulk-move in its current form. `_log_clamp`,
                    `_safe_log_r` move with this phase.

CLAUDE.md §3 (q=3329 lessons): "check raw values, not derived metrics"
— if this module's output ever disagrees with a legacy copy, trust the
legacy copy and flag the bug, because the legacy copies are what
produced the paper's SHA-256-stable seed JSONs.
"""
import math

import numpy as np


def build_lwe_kannan(n, m, q, seed=123):
    """Construct an LWE-Kannan embedding lattice of dimension n+m+1.

    Pure function of (n, m, q, seed) — seeded numpy RandomState makes
    lattice generation deterministic. Returns ``(L, s, e)`` where
    ``L`` is a nested-list ``(n+m+1) x (n+m+1)`` integer matrix,
    ``s`` the secret, and ``e`` the error vector.

    Character-identical to the legacy copies in (Phase 3 swap):
      scripts/sweep_parallel.py, scripts/sweep_cloud.py,
      scripts/q3329_verify.py, scripts/overnight_experiments.py,
      scripts/run_3x_extended.py, scripts/run_convergence_test.py
    """
    rng = np.random.RandomState(seed)
    s = rng.randint(0, 2, n).astype(int)
    e = rng.choice([-1, 0, 1], m).astype(int)
    A = rng.randint(0, q, (m, n)).astype(int)
    b = (A @ s + e) % q
    dim = m + n + 1
    L = [[0] * dim for _ in range(dim)]
    for i in range(m):
        L[i][i] = q
    for j in range(n):
        for i in range(m):
            L[m + j][i] = int(A[i][j])
    for j in range(n):
        L[m + j][m + j] = 1
    for i in range(m):
        L[m + n][i] = int(b[i])
    L[m + n][m + n] = 1
    return L, s, e


def ln_fixed_point(size, beta):
    """Closed-form Li-Nguyen fixed-point GS-log-norm profile.

    Pure function of (size, beta). Returns a list of length ``size``
    giving the predicted log-norms of Gram-Schmidt vectors at the
    BKZ fixed point, per Li-Nguyen (2020).

    Character-identical to the copies in:
      scripts/sweep_parallel.py:115
      scripts/sweep_cloud.py (corresponding line)
      scripts/q3329_verify.py (corresponding line)

    Any edit to the math here MUST preserve equality with the three
    legacy copies until Phase 2 of the v1.2 consolidation removes them.
    """
    exp = (size - 1) / (2 * (beta - 1)) + (beta * (beta - 2)) / (
        2 * size * (beta - 1)
    )
    log_v_beta = math.log(beta / (2 * math.pi * math.e)) * exp
    log_delta = math.log(beta / (2 * math.pi * math.e)) / (2 * beta - 2)
    total_vol = sum((size + 1 - 2 * i) * log_delta for i in range(1, size + 1))
    profile, cum = [], 0.0
    for i in range(1, size + 1):
        cum += (size + 1 - 2 * i) * log_delta
        profile.append(cum - (i / size) * total_vol)
    return [p + log_v_beta for p in profile]
