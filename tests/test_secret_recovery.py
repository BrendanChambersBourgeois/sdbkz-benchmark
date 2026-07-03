"""Cancellation-free secret-recovery readout (_bkz_core._secret_recovery).

Validates the INC-51 fix: detect NTRU crack from the EXACT integer reduced
basis (immune to the high-n GSO -345 cancellation), using the planted secret.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from _bkz_core import _secret_recovery  # noqa: E402
from fpylll import IntegerMatrix  # noqa: E402


def _matrix(rows):
    B = IntegerMatrix(len(rows), len(rows[0]))
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            B[i, j] = v
    return B


def test_secret_norm2_and_exact_match():
    # n=2 toy: secret f=(1,-1), g=(0,1); short vector s=(g,f)=(0,1,1,-1).
    f, g = [1, -1], [0, 1]
    big = [100, 0, 0, 0]
    B = _matrix([list(g) + list(f), big])  # row 0 IS the secret vector
    rec = _secret_recovery(B, f, g, n=2)
    assert rec["secret_norm2"] == 0 + 1 + 1 + 1  # ||g||^2+||f||^2 = 3
    assert rec["min_norm2"] == 3
    assert rec["recovered"] is True
    assert rec["exact_match"] is True


def test_rotation_match():
    # A cyclic rotation x^1 * s must still be detected.
    f, g = [1, -1, 0], [0, 1, 1]
    # rotation by 1: rot[k]=v[(k-1)%n] -> g'=(1,0,1), f'=(0,1,-1)
    rot = [1, 0, 1, 0, 1, -1]
    B = _matrix([rot, [99, 0, 0, 0, 0, 0]])
    rec = _secret_recovery(B, f, g, n=3)
    assert rec["exact_match"] is True
    assert rec["recovered"] is True


def test_sign_flip_match():
    f, g = [1, 0], [1, -1]
    neg = [-1, 1, -1, 0]  # -(g,f)
    B = _matrix([neg, [50, 0, 0, 0]])
    rec = _secret_recovery(B, f, g, n=2)
    assert rec["exact_match"] is True


def test_no_recovery_when_basis_long():
    # No row as short as the secret -> not recovered, no exact match.
    f, g = [1, -1], [0, 1]
    B = _matrix([[10, 10, 0, 0], [0, 0, 9, 9]])  # min_norm2=162 >> 3
    rec = _secret_recovery(B, f, g, n=2)
    assert rec["recovered"] is False
    assert rec["exact_match"] is False
    assert rec["min_norm2"] == min(200, 162)


def test_recovered_via_norm_without_exact_match():
    # A different short vector (not a secret rotation) still flags recovered
    # via the norm test, but exact_match stays False.
    f, g = [1, -1], [0, 1]  # secret_norm2 = 3
    B = _matrix([[1, 1, 0, 0], [80, 0, 0, 0]])  # min_norm2=2 <= 3, not a rotation
    rec = _secret_recovery(B, f, g, n=2)
    assert rec["recovered"] is True
    assert rec["exact_match"] is False


def test_run_single_additive_only():
    # Without secret_f/g, run_single emits NO recovery keys (byte-identical
    # contract for the LWE-Kannan path and pre-fix reproducibility).
    from _bkz_core import run_single
    from generators import build_ntru, get_metric_span
    n, q = 59, 97
    L, f, g = build_ntru(n, q, seed=1)
    ms, me = get_metric_span("ntru")(n, len(L))
    kw = dict(L=L, n=n, active_block_start=ms, active_block_end=me, beta=20,
              seed=1, q=q, precision=250, max_tours=5, log_clamp_fn=None)
    r_plain = run_single(**kw)
    NEW = {"secret_norm2", "min_actual_norm2_bkz", "min_actual_norm2_sdbkz",
           "secret_recovered_bkz", "secret_recovered_sdbkz",
           "secret_exact_match_bkz", "secret_exact_match_sdbkz"}
    assert not (set(r_plain) & NEW)
    # With the secret, exactly those keys appear and nothing else changes
    r_sec = run_single(**kw, secret_f=f, secret_g=g)
    assert set(r_sec) - set(r_plain) == NEW
    for k in r_plain:
        if k in ("timestamp", "bkz_time", "sdbkz_time"):
            continue
        assert r_plain[k] == r_sec[k], f"field {k} changed"
