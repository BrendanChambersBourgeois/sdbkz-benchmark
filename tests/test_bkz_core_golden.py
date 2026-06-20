"""Golden known-answer tests for scripts/_bkz_core.run_single.

The smoke suite (test_bkz_core_smoke.py) deliberately checks only the
*structural* contract (shapes, finiteness, bookkeeping) and defers numerical
authority to verify.sh. That leaves a gap: a refactor that silently moves a
reported number (advantage, d(LN), a tour count) still produces finite,
well-shaped output and passes the smoke suite -- caught only by verify.sh,
which runs a single seed outside pytest.

This module closes that gap with a fixed-seed known-answer test. The golden
values were generated from a clean run on a tiny deterministic LWE-Kannan
config and are pinned to the project's reduction stack (fpylll==0.6.4, the
pyproject pin). They are exact like the verify.sh reference constants: a
genuine reduction-logic change should move them and SHOULD fail this test. If
a *deliberate* dependency bump changes the low bits, re-baseline these
constants the same way verify.sh's references are re-baselined -- intentionally,
with review, not by loosening the tolerance.

Config: n=20, beta=10, q=97, seed=1, precision=100, max_tours=5 (~0.7s).
"""
from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from _bkz_core import run_single  # noqa: E402
from generators import build_lwe_kannan, kannan_m  # noqa: E402

# -- the fixed tiny config -------------------------------------------------
N, BETA, Q, SEED, PREC, TOURS = 20, 10, 97, 1, 100, 5

# -- golden known-answer values (fpylll==0.6.4) ----------------------------
# Floats are matched tightly; an actual logic regression moves them far
# beyond this tolerance. crossover_tour is None here: SD-BKZ never overtakes
# BKZ on this clean tiny instance (advantage stays negative).
GOLDEN = {
    "advantage": -0.08033659217829836,
    "crossover_tour": None,
    "bkz_final_dln": 3.909623955182225,
    "sdbkz_final_dln": 3.9899605473605235,
    "initial_dln": 4.053135499495328,
    "rhf_bkz": 0.2946000966262073,
    "rhf_sdbkz": 0.2946000966262253,
    "bkz_tours_run": 5,
    "sdbkz_tours_run": 5,
    "bkz_termination": "max_tours_reached",
    "sdbkz_termination": "max_tours_reached",
    "dim": 61,
}
_FLOAT_KEYS = {"advantage", "bkz_final_dln", "sdbkz_final_dln", "initial_dln",
               "rhf_bkz", "rhf_sdbkz"}


def _basis(n, q, seed):
    L, _, _ = build_lwe_kannan(n, kannan_m(n), q, seed=seed)
    return L


def _lwe_end(n):
    return n + kannan_m(n) + 1


def _run(floor_mode="safe"):
    return run_single(
        L=_basis(N, Q, SEED), n=N,
        active_block_start=kannan_m(N), active_block_end=_lwe_end(N),
        beta=BETA, seed=SEED, q=Q, precision=PREC, max_tours=TOURS,
        log_clamp_fn=None, floor_mode=floor_mode,
    )


@pytest.fixture(scope="module")
def golden_result():
    return _run()


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_golden_value(golden_result, key):
    """Each reported field matches its pinned known-answer value."""
    got, want = golden_result[key], GOLDEN[key]
    if key in _FLOAT_KEYS:
        assert got == pytest.approx(want, rel=1e-12, abs=1e-12)
    else:
        assert got == want


def test_run_single_is_deterministic():
    """Two runs of the same fixed seed produce identical reported numbers."""
    a, b = _run(), _run()
    for k in GOLDEN:
        assert a[k] == b[k]


def test_floor_mode_safe_equals_plain_on_clean_input():
    """floor_mode only changes output under a clamp; on a clean lattice (no
    non-positive get_r) 'safe' and 'plain' must agree on every reported number.
    The clamp-path divergence itself is covered in test_bkz_core_smoke.py."""
    safe, plain = _run("safe"), _run("plain")
    skip = {"timestamp", "bkz_time", "sdbkz_time"}  # wall-clock only
    for k in GOLDEN:
        if k in skip:
            continue
        assert safe[k] == plain[k], f"floor_mode changed {k} on clean input"
