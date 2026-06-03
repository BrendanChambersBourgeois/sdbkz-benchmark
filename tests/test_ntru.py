"""Shape + correctness tests for scripts/generators/ntru.build_ntru.

Greenfield generator, no locked seeds — this is the gate that the NTRU
lattice is built correctly. Asserts, over a small (N, q, seed) grid:

  - dimension is 2N (NTRU has no separate m),
  - the top-left q·I_N block is exact and the top-right block is zero,
  - the bottom-right block is I_N,
  - key consistency H·f ≡ g (mod q) — the real correctness check, that
    H is the rotation matrix of h = g·f⁻¹,
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

# Small grid: N ∈ {16, 32}, prime q (3329 ML-KEM + smaller), seeds 1-3.
GRID = [(N, q, seed)
        for N in (16, 32)
        for q in (3329, 257)
        for seed in (1, 2, 3)]


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_dim_is_2n(N, q, seed):
    L, _, _ = build_ntru(N, q, seed=seed)
    assert len(L) == 2 * N
    assert all(len(row) == 2 * N for row in L)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_top_left_is_qI_and_top_right_zero(N, q, seed):
    L, _, _ = build_ntru(N, q, seed=seed)
    for i in range(N):
        for j in range(2 * N):
            expected = q if i == j else 0
            assert L[i][j] == expected, (i, j)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_bottom_right_is_identity(N, q, seed):
    L, _, _ = build_ntru(N, q, seed=seed)
    for i in range(N):
        for j in range(N):
            assert L[N + i][N + j] == (1 if i == j else 0), (i, j)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_key_consistency_H_f_equals_g(N, q, seed):
    # H·f ≡ g (mod q): H is the rotation matrix of h = g·f⁻¹, so this is
    # the structural guarantee that the public key is correct.
    L, f, g = build_ntru(N, q, seed=seed)
    H = np.array([[L[N + i][j] for j in range(N)] for i in range(N)])
    assert np.array_equal((H @ f) % q, g % q)


@pytest.mark.parametrize("N,q,seed", GRID)
def test_ntru_secrets_are_ternary(N, q, seed):
    _, f, g = build_ntru(N, q, seed=seed)
    assert set(np.unique(f)).issubset({-1, 0, 1})
    assert set(np.unique(g)).issubset({-1, 0, 1})


def test_ntru_deterministic_same_seed():
    a, fa, ga = build_ntru(16, 3329, seed=7)
    b, fb, gb = build_ntru(16, 3329, seed=7)
    assert a == b
    assert np.array_equal(fa, fb) and np.array_equal(ga, gb)


def test_ntru_seed_sensitive():
    a, _, _ = build_ntru(16, 3329, seed=1)
    b, _, _ = build_ntru(16, 3329, seed=2)
    assert a != b


def test_lwe_metric_block_start_is_2n():
    # LWE-Kannan declares m=2n (the projected sublattice with the target).
    fn = get_metric_block_start("lwe_kannan")
    assert fn(50) == kannan_m(50) == 100


def test_ntru_metric_block_start_is_full_basis():
    # R* decision: full basis [0, 2N) — the engine measures the whole NTRU
    # profile, so the active-block start is 0 for any N.
    fn = get_metric_block_start("ntru")
    assert fn(16) == 0
    assert fn(32) == 0


def test_ntru_registry_adapter_returns_basis_only():
    L = get_generator("ntru")(16, 3329, 1)
    assert len(L) == 32 and len(L[0]) == 32
    # Matches build_ntru's basis exactly (adapter just drops f, g).
    L_full, _, _ = build_ntru(16, 3329, seed=1)
    assert L == L_full
