"""NTRU lattice generator (Ducas–van Woerden fatigue layout).

Greenfield — no NTRU code predates this module. Builds the standard
2N×2N NTRU lattice from a public key h = g·f⁻¹ over the negacyclic ring
Z_q[x]/(x^N + 1):

    B = [[ q·I_N ,  0   ],
         [   H   ,  I_N ]]      H = negacyclic rotation matrix of h

Secrets f, g are ternary fixed-weight; f is resampled until invertible
mod q. Seeded via numpy RandomState for determinism, matching the house
style of build_lwe_kannan.

Calling convention matches the generators registry: the ring degree N is
passed as ``n``; the lattice dimension is 2N (NTRU has no separate m).

NOTE (fatigue-sensitive): the secret weight ``d`` is the knob the NTRU
fatigue phase transition is sensitive to. Default ``d = round(N/3)`` (the
NTRU d≈N/3 rule of thumb). To compare against a specific reference
(e.g. Ducas–van Woerden), match THEIR weight convention here — uniform
vs fixed-weight ternary changes the transition.
"""
import numpy as np


def _ternary_fixed_weight(N: int, d: int, rng) -> np.ndarray:
    """Ternary vector of length N: d coeffs +1, d coeffs -1, rest 0."""
    if 2 * d > N:
        raise ValueError(f"fixed weight 2d={2 * d} exceeds ring degree N={N}")
    coeffs = np.zeros(N, dtype=int)
    idx = rng.permutation(N)
    coeffs[idx[:d]] = 1
    coeffs[idx[d:2 * d]] = -1
    return coeffs


def _neg_matrix(c, q: int) -> list[list[int]]:
    """Negacyclic rotation matrix of polynomial ``c`` over Z_q[x]/(x^N+1),
    reduced to [0, q). Entry [i][j] is the coeff of x^i in x^j·c; the
    wraparound term (x^N ≡ -1) flips sign. So ``M @ v`` is the coefficient
    vector of ``c · v`` mod (x^N + 1)."""
    N = len(c)
    M = [[0] * N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            k = i - j
            if k >= 0:
                M[i][j] = int(c[k]) % q
            else:
                M[i][j] = (-int(c[k + N])) % q
    return M


def _solve_mod(M, b, q: int):
    """Solve ``M x ≡ b (mod q)`` for prime q via Gauss-Jordan elimination.
    Returns the solution vector, or None if M is singular mod q."""
    N = len(M)
    A = [[int(M[i][j]) % q for j in range(N)] + [int(b[i]) % q]
         for i in range(N)]
    for col in range(N):
        piv = next((r for r in range(col, N) if A[r][col] % q != 0), None)
        if piv is None:
            return None
        A[col], A[piv] = A[piv], A[col]
        inv = pow(A[col][col], q - 2, q)  # Fermat inverse (q prime)
        A[col] = [(x * inv) % q for x in A[col]]
        for r in range(N):
            if r != col and A[r][col]:
                fac = A[r][col]
                A[r] = [(A[r][k] - fac * A[col][k]) % q for k in range(N + 1)]
    return [A[i][N] % q for i in range(N)]


def build_ntru(n: int, q: int, seed: int = 123, d: int | None = None):
    """Construct the 2N×2N NTRU lattice (ring degree N = n).

    Returns ``(L, f, g)``: ``L`` the nested-list (2N)×(2N) integer basis,
    ``f`` and ``g`` the ternary secret polynomials (np.ndarray, entries in
    {-1, 0, 1}). ``f`` is invertible mod q, so h = g·f⁻¹ is well defined and
    ``H @ f ≡ g (mod q)`` by construction.
    """
    N = n
    if d is None:
        d = round(N / 3)
    rng = np.random.RandomState(seed)

    # Sample f until it is invertible in Z_q[x]/(x^N+1); then sample g.
    while True:
        f = _ternary_fixed_weight(N, d, rng)
        e0 = [1] + [0] * (N - 1)
        finv = _solve_mod(_neg_matrix(f, q), e0, q)  # f⁻¹ coeffs, or None
        if finv is not None:
            break
    g = _ternary_fixed_weight(N, d, rng)

    # h = g · f⁻¹ mod (x^N+1, q); H = negacyclic rotation matrix of h.
    Mg = _neg_matrix(g, q)
    h = [sum(Mg[i][j] * finv[j] for j in range(N)) % q for i in range(N)]
    H = _neg_matrix(h, q)

    dim = 2 * N
    L = [[0] * dim for _ in range(dim)]
    for i in range(N):
        L[i][i] = q                    # top-left  q·I_N
    for i in range(N):
        for j in range(N):
            L[N + i][j] = H[i][j]      # bottom-left H
        L[N + i][N + i] = 1            # bottom-right I_N
    return L, f, g
