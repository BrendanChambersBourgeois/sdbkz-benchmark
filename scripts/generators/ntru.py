"""NTRU lattice generator — Ducas–van Woerden fatigue conventions.

Matches "NTRU Fatigue: How Stretched is Overstretched?" (Ducas &
van Woerden, ASIACRYPT 2021), so results compare against their fatigue
point q ≈ 0.004·n^2.484 (n > 100):

  - Ring: circulant NTRU over Z_q[x]/(x^n − 1), n PRIME (Def 2.2). The
    rotation matrix is plain circulant (x^n ≡ +1, no sign flip).
  - Secret: f, g with ternary coefficients i.i.d. uniform in {-1, 0, 1}
    — variance σ² = 2/3, the distribution their experiments use (Fig 1,
    "the ternary case is treated as a discrete Gaussian with σ² = 2/3").
    f is resampled until invertible mod q.
  - Lattice (Def 2.3): the 2n×2n basis

        L = [[ q·I_n ,  H   ],
             [   0   ,  I_n ]]      H = circulant matrix of h = g·f⁻¹

    whose secret dense sublattice contains (g, f); H·f ≡ g (mod q).

Calling convention matches the generators registry: the ring degree n is
passed as ``n`` (should be prime for DvW comparability); the lattice
dimension is 2n. Seeded numpy RandomState for determinism, house style.
"""
import numpy as np


def _ternary_uniform(n: int, rng) -> np.ndarray:
    """Ternary vector of length n, coefficients i.i.d. uniform in
    {-1, 0, 1} (σ² = 2/3) — the Ducas–van Woerden secret distribution."""
    return rng.choice([-1, 0, 1], n).astype(int)


def _circ_matrix(c, q: int) -> list[list[int]]:
    """Circulant matrix of polynomial ``c`` over Z_q[x]/(x^n − 1), reduced
    to [0, q). Entry [i][j] is the coeff of x^i in x^j·c; x^n ≡ +1 means no
    sign flip. So ``M @ v`` is the coefficient vector of ``c · v`` mod
    (x^n − 1)."""
    n = len(c)
    M = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            M[i][j] = int(c[(i - j) % n]) % q
    return M


def _solve_mod(M, b, q: int):
    """Solve ``M x ≡ b (mod q)`` for prime q via Gauss-Jordan elimination.
    Returns the solution vector, or None if M is singular mod q."""
    n = len(M)
    A = [[int(M[i][j]) % q for j in range(n)] + [int(b[i]) % q]
         for i in range(n)]
    for col in range(n):
        piv = next((r for r in range(col, n) if A[r][col] % q != 0), None)
        if piv is None:
            return None
        A[col], A[piv] = A[piv], A[col]
        inv = pow(A[col][col], q - 2, q)  # Fermat inverse (q prime)
        A[col] = [(x * inv) % q for x in A[col]]
        for r in range(n):
            if r != col and A[r][col]:
                fac = A[r][col]
                A[r] = [(A[r][k] - fac * A[col][k]) % q for k in range(n + 1)]
    return [A[i][n] % q for i in range(n)]


def build_ntru(n: int, q: int, seed: int = 123):
    """Construct the 2n×2n circulant NTRU lattice (ring degree n, prime).

    Returns ``(L, f, g)``: ``L`` the nested-list (2n)×(2n) integer basis
    (Def 2.3 layout), ``f`` and ``g`` the ternary secret polynomials
    (np.ndarray, entries in {-1, 0, 1}). ``f`` is invertible mod q, so
    h = g·f⁻¹ is well defined and ``H @ f ≡ g (mod q)`` by construction.
    """
    rng = np.random.RandomState(seed)

    # Sample f until it is invertible in Z_q[x]/(x^n − 1); then sample g.
    while True:
        f = _ternary_uniform(n, rng)
        e0 = [1] + [0] * (n - 1)
        finv = _solve_mod(_circ_matrix(f, q), e0, q)  # f⁻¹ coeffs, or None
        if finv is not None:
            break
    g = _ternary_uniform(n, rng)

    # h = g · f⁻¹ mod (x^n − 1, q); H = circulant matrix of h.
    Mg = _circ_matrix(g, q)
    h = [sum(Mg[i][j] * finv[j] for j in range(n)) % q for i in range(n)]
    H = _circ_matrix(h, q)

    dim = 2 * n
    L = [[0] * dim for _ in range(dim)]
    for i in range(n):
        L[i][i] = q                    # top-left  q·I_n
    for i in range(n):
        for j in range(n):
            L[i][n + j] = H[i][j]      # top-right H
        L[n + i][n + i] = 1            # bottom-right I_n
    # bottom-left block is 0
    return L, f, g
