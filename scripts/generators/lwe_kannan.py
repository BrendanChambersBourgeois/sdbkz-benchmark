"""LWE-Kannan embedding lattice generator.

Moved verbatim from ``_math_core.build_lwe_kannan`` (generators refactor,
2026-06-03). The function body is character-identical to the prior
canonical copy — same seeded RNG call order, same dtype, same matrix
layout — so existing SHA-256-locked bases stay byte-identical.

The engine is generator-agnostic; it consumes ``L`` and knows nothing
about how it was built. ``run_campaign`` dispatches generators by name.
"""
import numpy as np


def kannan_m(n: int) -> int:
    """LWE sample count for the Kannan embedding: ``m = 2n``.

    The benchmark's standing contract. Pinned in one place so no call
    site forks it — every builder/engine path derives m from here (or,
    for the engine, from the basis it receives).
    """
    return n * 2


def build_lwe_kannan(
    n: int, m: int, q: int, seed: int = 123
) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
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
