"""Shape + correctness tests for scripts/generators/ntru.build_ntru.

Greenfield generator, no locked seeds — this is the gate that the NTRU
lattice is built correctly (Ducas–van Woerden conventions: circulant
x^n−1, n prime, uniform ternary). Asserts, over a small prime (n, q, seed)
grid:

  - dimension is 2n (NTRU has no separate m),
  - the Def 2.3 layout [[q·I_n, H],[0, I_n]]: top-left q·I_n exact,
    bottom-left block zero, bottom-right block I_n,
  - key consistency H·f ≡ g (mod q) — the real correctness check, that
    H (top-right) is the circulant matrix of h = g·f⁻¹,
  - secrets are ternary (uniform {-1,0,1}, σ²=2/3),
  - determinism (same seed → same basis) and seed-sensitivity.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from generators import (  # noqa: E402
    build_ntru,
    get_generator,
    get_metric_block_start,
    kannan_m,
)

# Small grid: prime n ∈ {17, 31} (circulant ring needs n prime), prime q
# (3329 ML-KEM + smaller), seeds 1-3.
GRID = [(N, q, seed)
        for N in (17, 31)
        for q in (3329, 257)
        for seed in (1, 2, 3)]


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_dim_is_2n(N, q, seed):
    L, _, _ = build_ntru(N, q, seed=seed)
    assert len(L) == 2 * N
    assert all(len(row) == 2 * N for row in L)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_top_left_qI_and_bottom_left_zero(N, q, seed):
    # Def 2.3 layout [[q·I_n, H],[0, I_n]]: top-left is q·I_n (H lives in
    # the top-right block, so it is NOT zero); the bottom-left block is 0.
    L, _, _ = build_ntru(N, q, seed=seed)
    for i in range(N):
        for j in range(N):
            assert L[i][j] == (q if i == j else 0), ("top-left", i, j)
            assert L[N + i][j] == 0, ("bottom-left", i, j)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_bottom_right_is_identity(N, q, seed):
    L, _, _ = build_ntru(N, q, seed=seed)
    for i in range(N):
        for j in range(N):
            assert L[N + i][N + j] == (1 if i == j else 0), (i, j)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_key_consistency_H_f_equals_g(N, q, seed):
    # H·f ≡ g (mod q): H (the top-right block, Def 2.3) is the circulant
    # matrix of h = g·f⁻¹, so this is the structural guarantee that the
    # public key is correct and (g, f) lies in the lattice.
    L, f, g = build_ntru(N, q, seed=seed)
    H = np.array([[L[i][N + j] for j in range(N)] for i in range(N)])
    assert np.array_equal((H @ f) % q, g % q)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_secrets_are_ternary(N, q, seed):
    _, f, g = build_ntru(N, q, seed=seed)
    assert set(np.unique(f)).issubset({-1, 0, 1})
    assert set(np.unique(g)).issubset({-1, 0, 1})


def test_ntru_deterministic_same_seed():
    a, fa, ga = build_ntru(17, 3329, seed=7)
    b, fb, gb = build_ntru(17, 3329, seed=7)
    assert a == b
    assert np.array_equal(fa, fb) and np.array_equal(ga, gb)


def test_ntru_seed_sensitive():
    a, _, _ = build_ntru(17, 3329, seed=1)
    b, _, _ = build_ntru(17, 3329, seed=2)
    assert a != b


def test_lwe_metric_block_start_is_2n():
    # LWE-Kannan declares m=2n (the projected sublattice with the target).
    fn = get_metric_block_start("lwe_kannan")
    assert fn(50) == kannan_m(50) == 100


def test_ntru_metric_block_start_is_full_basis():
    # R* decision: full basis [0, 2n) — the engine measures the whole NTRU
    # profile, so the active-block start is 0 for any n.
    fn = get_metric_block_start("ntru")
    assert fn(17) == 0
    assert fn(31) == 0


def test_ntru_registry_adapter_returns_basis_only():
    L = get_generator("ntru")(17, 3329, 1)
    assert len(L) == 34 and len(L[0]) == 34
    # Matches build_ntru's basis exactly (adapter just drops f, g).
    L_full, _, _ = build_ntru(17, 3329, seed=1)
    assert L == L_full
