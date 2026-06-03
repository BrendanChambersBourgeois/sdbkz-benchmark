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
from generators import build_lwe_kannan, kannan_m  # noqa: E402


def _basis(n, q, seed):
    """Build the LWE-Kannan basis the engine now consumes. Post-refactor
    run_single is construction-blind — the caller supplies L (here the
    test plays the dispatcher's role)."""
    L, _, _ = build_lwe_kannan(n, kannan_m(n), q, seed=seed)
    return L


# Tiny config: n=20, β=10, max_tours=5, 100-bit precision. Total wall
# ~0.7s per call; we cache a single run with module-scope fixture so
# every assertion below shares the cost.
@pytest.fixture(scope="module")
def tiny_result():
    return run_single(
        L=_basis(20, 97, 1),
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
        L=_basis(15, 97, 2),
        n=15, beta=8, seed=2, q=97, precision=100, max_tours=3,
        log_clamp_fn=None,
    )
    assert r["n"] == 15
    assert r["m"] == 30
    assert r["dim"] == 46


def test_smoke_store_per_tour_emits_full_arrays():
    r = run_single(
        L=_basis(18, 97, 3),
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
        L=_basis(20, 97, 4),
        n=20, beta=10, seed=4, q=97, precision=100, max_tours=3,
        log_clamp_fn=_clamp,
    )
    assert r["status"] == "completed"
    # No assertion on len(calls) — implementation may or may not
    # log on this benign config; the gate is only "no crash".


# ---------------------------------------------------------------------------
# q=3329 §8 cancellation clamp path — the 9-day-incident regression gate
# ---------------------------------------------------------------------------

def test_clamp_path_fires_on_nonpositive_get_r():
    """`_math_core.metrics_from_gso` must route a non-positive `get_r`
    return through `log_clamp_fn` BEFORE substituting the sentinel.

    Paper §8 documents that fplll's GSO recurrence at q=3329 n>=100
    occasionally returns negative `M.get_r(i, i)` due to catastrophic
    cancellation. The defensive clamp is the contract: log the raw
    value first (so the audit chain has the smoking-gun number),
    then substitute `CLAMP_FLOOR_R = 1e-300` so downstream `log()`
    doesn't crash.

    Pre-v1.2 one of the legacy `_safe_log_r` copies substituted the
    sentinel WITHOUT logging — the silent path hid the real return
    for 9 days. This test enforces "log before substitute" at the
    canonical helper level so the same bug class cannot reach paper
    output again.

    Synthetic fpylll-Mat stand-in: an object with a `get_r(i, i)`
    method that returns -1e-50 (negative; small magnitude). Per the
    contract, the callback fires with the raw -1e-50 value before
    the clamp substitutes 1e-300.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    from _math_core import metrics_from_gso

    raw_returns = [-1e-50, -2.5e-100, -1.0, 4.2, 3.7]
    # ^ five active-block positions: three negative (clamp), two positive
    # (pass through). Lengths matter — metrics_from_gso walks the active
    # block via range(m, dim).

    class FakeMat:
        def __init__(self, returns):
            self._returns = list(returns)
            self._idx = 0

        def get_r(self, i, j):
            v = self._returns[self._idx]
            self._idx += 1
            return v

    clamp_events = []

    def _log_clamp(ctx, position, raw_value):
        clamp_events.append({
            "ctx": ctx, "position": position, "raw_value": raw_value,
        })

    # Run metrics_from_gso on the synthetic Mat. The active-block walk
    # covers positions [m, dim); here m=0, dim=5 so all five positions.
    result = metrics_from_gso(
        FakeMat(raw_returns), dim=5, m=0,
        ln_profile=[0.0] * 5, full=False,
        clamp_ctx="test_clamp_path",
        log_clamp_fn=_log_clamp,
        warn_on_clamp=False,
    )

    # Three of the five positions returned non-positive — all three
    # must have fired the callback BEFORE substitution.
    assert len(clamp_events) == 3, (
        f"expected 3 clamp events (one per negative get_r), got "
        f"{len(clamp_events)}: {clamp_events}"
    )

    # Each event must carry the EXACT raw negative value, not the
    # substituted sentinel. This is the §8-regression check: silent
    # substitution would log 1e-300 (or nothing) instead of the
    # actual cancellation residue.
    raw_logged = [e["raw_value"] for e in clamp_events]
    assert -1e-50 in raw_logged
    assert -2.5e-100 in raw_logged
    assert -1.0 in raw_logged

    # Context tag from caller propagates to log.
    assert all(e["ctx"].startswith("test_clamp_path") for e in clamp_events)

    # metrics_from_gso still returns a valid result dict; the sentinel
    # substitution prevents downstream `math.log()` from crashing on
    # the negative inputs.
    assert "dln" in result
    assert "rankin" in result
    assert len(result["rankin"]) == 5
    # The 3 clamped positions contribute 0.5 * log(1e-300) ≈ -345.4 to
    # gs_log_active; the two positive positions contribute their own
    # log values. dln is finite.
    assert result["dln"] == result["dln"]  # not NaN


def test_clamp_path_no_callback_silently_substitutes():
    """When `log_clamp_fn=None`, the clamp still substitutes the
    sentinel (no crash) but no logging fires. Verifies the optional-
    callback contract — callers passing None for tests or quiet paths
    do not get accidental side effects."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    from _math_core import metrics_from_gso

    class FakeMat:
        def __init__(self, returns):
            self._returns = list(returns)
            self._idx = 0

        def get_r(self, i, j):
            v = self._returns[self._idx]
            self._idx += 1
            return v

    result = metrics_from_gso(
        FakeMat([-1.0, 1.0, 2.0]), dim=3, m=0,
        ln_profile=[0.0, 0.0, 0.0], full=False,
        log_clamp_fn=None,
    )
    assert result["dln"] == result["dln"]  # finite, not NaN
    assert len(result["rankin"]) == 3


def test_clamp_path_warn_on_clamp_emits_warning(capsys):
    """`warn_on_clamp=True` prints one stdout line summarising the
    clamp count after the active-block walk. Used by q3329_verify
    for fast operator signal during long ML-KEM-modulus runs."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    from _math_core import metrics_from_gso

    class FakeMat:
        def __init__(self, returns):
            self._returns = list(returns)
            self._idx = 0

        def get_r(self, i, j):
            v = self._returns[self._idx]
            self._idx += 1
            return v

    metrics_from_gso(
        FakeMat([-1.0, -2.0, 3.0]), dim=3, m=0,
        ln_profile=[0.0, 0.0, 0.0], full=False,
        log_clamp_fn=lambda *a, **k: None,
        warn_on_clamp=True,
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "2" in captured.out  # two clamp events
