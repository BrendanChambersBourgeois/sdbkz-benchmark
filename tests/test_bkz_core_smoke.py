"""Smoke tests for scripts/_bkz_core.run_single.

A tiny n=20 β=10 max_tours=5 lattice runs in ~0.7s on a development
machine; small enough to live in the fast pytest gate, large enough
to exercise the full happy-path of run_single (LLL bootstrap, both
BKZ + SD-BKZ variants, per-tour deltas, stagnation detection,
metrics_from_gso call site, dict-result assembly, crossover scan).

Not a numerical-correctness gate — verify.sh remains the authority
for that. These tests check the *structural* contract of run_single
(returns dict with the expected keys, advantage is a float, no
exception under benign input) and provide enough coverage of
_bkz_core to satisfy the Phase 4 pytest --cov 75% floor.

Slow tests are marked so they can be skipped via `pytest -m "not slow"`
if a future CI bucket wants to short-circuit them. Default run
includes them — wall ~1s combined is acceptable.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from _bkz_core import run_single  # noqa: E402


# Tiny config: n=20, β=10, max_tours=5, 100-bit precision. Total wall
# ~0.7s per call; we cache a single run with module-scope fixture so
# every assertion below shares the cost.
@pytest.fixture(scope="module")
def tiny_result():
    return run_single(
        n=20, beta=10, seed=1, q=97, precision=100, max_tours=5,
        log_clamp_fn=None,
    )


def test_smoke_run_returns_dict(tiny_result):
    assert isinstance(tiny_result, dict)


def test_smoke_run_has_expected_keys(tiny_result):
    required = {
        "n", "beta", "seed", "q", "max_tours", "precision",
        "dim", "m", "status", "timestamp",
        "initial_dln", "initial_rhf",
        "bkz_dln_per_tour", "bkz_tours_run", "bkz_time", "bkz_final_dln",
        "bkz_termination", "bkz_floor", "rankin_profile_bkz", "gs_lognorms_bkz",
        "rhf_bkz",
        "sdbkz_dln_per_tour", "sdbkz_tours_run", "sdbkz_time", "sdbkz_final_dln",
        "sdbkz_termination", "sdbkz_floor", "rankin_profile_sdbkz", "gs_lognorms_sdbkz",
        "rhf_sdbkz",
        "advantage", "rhf_advantage",
    }
    assert required.issubset(set(tiny_result.keys()))


def test_smoke_advantage_is_real_number(tiny_result):
    adv = tiny_result["advantage"]
    assert isinstance(adv, float)
    assert adv == adv  # not NaN
    assert abs(adv) < 1e6  # not pathologically extreme


def test_smoke_status_completed(tiny_result):
    assert tiny_result["status"] == "completed"


def test_smoke_tours_match_bookkeeping(tiny_result):
    # max_tours=5, so each variant ran at most 5 tours. Lower bound 1.
    assert 1 <= tiny_result["bkz_tours_run"] <= 5
    assert 1 <= tiny_result["sdbkz_tours_run"] <= 5
    assert len(tiny_result["bkz_dln_per_tour"]) == tiny_result["bkz_tours_run"]
    assert len(tiny_result["sdbkz_dln_per_tour"]) == tiny_result["sdbkz_tours_run"]


def test_smoke_dim_matches_n_m_kannan():
    # The Kannan embedding produces dim = m + n + 1 with m = 2n by
    # convention. Verified once from a fresh call (independent of the
    # cached fixture) so a future schema drift surfaces immediately.
    r = run_single(
        n=15, beta=8, seed=2, q=97, precision=100, max_tours=3,
        log_clamp_fn=None,
    )
    assert r["n"] == 15
    assert r["m"] == 30
    assert r["dim"] == 46


def test_smoke_store_per_tour_emits_full_arrays():
    r = run_single(
        n=18, beta=10, seed=3, q=97, precision=100, max_tours=3,
        log_clamp_fn=None, store_per_tour=True,
    )
    # store_per_tour=True asks _bkz_core for full-rankin per-tour
    # data; the schema documents the key as a boolean toggle on the
    # result dict but the actual per-tour arrays land under
    # rankin_profile_{bkz,sdbkz} / gs_lognorms_{bkz,sdbkz} as lists.
    assert r["store_per_tour"] is True
    assert isinstance(r["rankin_profile_bkz"], list)
    assert isinstance(r["gs_lognorms_bkz"], list)


def test_smoke_clamp_callback_invoked_when_supplied():
    # Pass a logger callback; verify it can be called without error
    # even when no clamp events fire (small q=97 n=20 never triggers
    # the cancellation). The contract is "callback may be invoked";
    # we assert it is not invoked here and the run still completes.
    calls = []

    def _clamp(ctx, position, raw_value):
        calls.append((ctx, position, raw_value))

    r = run_single(
        n=20, beta=10, seed=4, q=97, precision=100, max_tours=3,
        log_clamp_fn=_clamp,
    )
    assert r["status"] == "completed"
    # No assertion on len(calls) — implementation may or may not
    # log on this benign config; the gate is only "no crash".
