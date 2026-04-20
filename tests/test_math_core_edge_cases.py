"""Unit tests for scripts/_math_core.py — edge cases beyond the
per-sweep-script parity grid covered by scripts/test_math_core_parity.py.

Intent: catch regressions in corner cases the parity test does not
exercise (small q, small n, large β, None log_clamp_fn, clamp counter
semantics). Fast; no fpylll required for the pure-math tests.
"""
import math

import numpy as np
import pytest

from _math_core import (
    CLAMP_FLOOR_R,
    build_lwe_kannan,
    ln_fixed_point,
    log_clamp,
    metrics_from_gso,
)


# ---------------------------------------------------------------------------
# build_lwe_kannan
# ---------------------------------------------------------------------------

def test_build_lwe_kannan_dim():
    """Output matrix is (n+m+1) × (n+m+1)."""
    L, s, e = build_lwe_kannan(n=5, m=10, q=97, seed=1)
    dim = 5 + 10 + 1
    assert len(L) == dim
    assert all(len(row) == dim for row in L)
    assert len(s) == 5
    assert len(e) == 10


def test_build_lwe_kannan_determinism():
    """Same seed → same matrix."""
    A1 = build_lwe_kannan(n=10, m=20, q=97, seed=42)
    A2 = build_lwe_kannan(n=10, m=20, q=97, seed=42)
    assert A1[0] == A2[0]
    assert (A1[1] == A2[1]).all()
    assert (A1[2] == A2[2]).all()


def test_build_lwe_kannan_different_seeds_differ():
    L1, _, _ = build_lwe_kannan(n=10, m=20, q=97, seed=1)
    L2, _, _ = build_lwe_kannan(n=10, m=20, q=97, seed=2)
    assert L1 != L2


def test_build_lwe_kannan_small_q():
    """q=2 boundary — A entries {0, 1}."""
    L, s, e = build_lwe_kannan(n=5, m=10, q=2, seed=1)
    # Upper-left q-block diagonal = q = 2
    for i in range(10):
        assert L[i][i] == 2
    # Secret entries binary
    assert set(s.tolist()).issubset({0, 1})


def test_build_lwe_kannan_n_gt_m():
    """n > m: unusual but not forbidden. Check dim math still works."""
    L, s, e = build_lwe_kannan(n=20, m=5, q=97, seed=1)
    assert len(L) == 26
    assert len(s) == 20


def test_build_lwe_kannan_embedding_row_b():
    """Last row of L (the embedded target) starts with entries from
    `b = A·s + e mod q` followed by an all-zero block and a 1."""
    n, m = 10, 15
    q = 97
    L, s, e = build_lwe_kannan(n=n, m=m, q=q, seed=7)
    last_row = L[m + n]
    assert last_row[m + n] == 1
    # First m entries are b
    A = np.array([[L[m + j][i] for j in range(n)] for i in range(m)])
    b_expected = (A @ s + e) % q
    assert [last_row[i] for i in range(m)] == list(b_expected.astype(int))


# ---------------------------------------------------------------------------
# ln_fixed_point
# ---------------------------------------------------------------------------

def test_ln_fixed_point_length():
    for size in [10, 50, 100, 200]:
        assert len(ln_fixed_point(size, beta=30)) == size


def test_ln_fixed_point_shape_unimodal():
    """LN fixed-point profile is unimodal: monotone increasing up to
    a peak near the middle, then monotone decreasing. Matches the
    Li-Nguyen closed form; catches any sign-flip in the quadratic
    coefficients."""
    p = ln_fixed_point(100, 30)
    diffs = [p[i + 1] - p[i] for i in range(len(p) - 1)]
    rising = [i for i, d in enumerate(diffs) if d > 0]
    falling = [i for i, d in enumerate(diffs) if d < 0]
    # All rising indices precede all falling indices (unimodal)
    assert rising and falling, "profile must have both rising and falling segments"
    assert max(rising) < min(falling), (
        f"non-unimodal: max rising idx {max(rising)} >= min falling idx "
        f"{min(falling)}"
    )


def test_ln_fixed_point_beta_scaling():
    """Larger β → lower (more negative) log_v_beta → each entry shifts."""
    p30 = ln_fixed_point(100, 30)
    p40 = ln_fixed_point(100, 40)
    # Not asserting element-wise order — only that they differ.
    assert p30 != p40


def test_ln_fixed_point_beta_boundary():
    """β=2 is the LLL boundary; function should still return finite values.
    β=1 would zero-div; assert it raises."""
    p = ln_fixed_point(20, beta=2)
    assert all(math.isfinite(x) for x in p)
    with pytest.raises(ZeroDivisionError):
        ln_fixed_point(20, beta=1)


# ---------------------------------------------------------------------------
# metrics_from_gso — via a fpylll-free MockGSO so tests stay fast
# ---------------------------------------------------------------------------

class MockGSO:
    """Stand-in for fpylll.GSO.Mat that returns canned get_r values.

    Used to exercise metrics_from_gso's clamp handling without
    pulling in fpylll's real BKZ pipeline.
    """

    def __init__(self, r_values):
        self._r = list(r_values)

    def get_r(self, i, j):
        assert i == j, "metrics_from_gso only uses the diagonal"
        return self._r[i]


def test_metrics_from_gso_all_positive_no_clamp():
    """Happy path: all r values positive, no clamp fires."""
    dim = 10
    m = 3
    r = [float(1.0 / (i + 1) ** 2) for i in range(dim)]  # positive, decreasing
    clamp_events = []
    ln_p = [0.0] * (dim - m)

    result = metrics_from_gso(
        MockGSO(r), dim, m, ln_p, full=False,
        log_clamp_fn=lambda *a, **kw: clamp_events.append(a),
    )
    assert "rankin" in result
    assert "dln" in result
    assert len(result["rankin"]) == dim - m
    assert clamp_events == []


def test_metrics_from_gso_clamp_fires_on_negative():
    """Non-positive r → clamp fires + CLAMP_FLOOR_R substituted."""
    dim = 10
    m = 3
    r = [1.0] * dim
    r[5] = -1e-20  # deliberate negative in the active block (idx 5 = m+2)
    clamp_events = []

    result = metrics_from_gso(
        MockGSO(r), dim, m, [0.0] * (dim - m), full=False,
        log_clamp_fn=lambda *a, **kw: clamp_events.append(a),
    )
    assert len(clamp_events) == 1
    assert "active" in clamp_events[0][0]
    # dln still finite; the clamp floor -> 0.5 * log(CLAMP_FLOOR_R)
    assert math.isfinite(result["dln"])


def test_metrics_from_gso_none_log_clamp_fn():
    """log_clamp_fn=None must not crash on clamp — silent substitution."""
    dim = 10
    m = 3
    r = [1.0] * dim
    r[4] = 0.0  # zero triggers the r > 0 check
    result = metrics_from_gso(
        MockGSO(r), dim, m, [0.0] * (dim - m), full=False,
        log_clamp_fn=None,
    )
    assert math.isfinite(result["dln"])


def test_metrics_from_gso_full_adds_rhf_and_gs():
    dim = 10
    m = 3
    r = [1.0 / (i + 1) for i in range(dim)]
    result = metrics_from_gso(
        MockGSO(r), dim, m, [0.0] * (dim - m), full=True,
        log_clamp_fn=None,
    )
    assert "gs_lognorms" in result
    assert "rhf" in result
    assert len(result["gs_lognorms"]) == dim
    assert result["rhf"] > 0


def test_metrics_from_gso_warn_on_clamp_prints(capsys):
    """warn_on_clamp=True → stdout line on clamp."""
    dim = 10
    m = 3
    r = [1.0] * dim
    r[4] = -1.0
    metrics_from_gso(
        MockGSO(r), dim, m, [0.0] * (dim - m),
        log_clamp_fn=None, warn_on_clamp=True,
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "get_r" in captured.out


# ---------------------------------------------------------------------------
# log_clamp side-log
# ---------------------------------------------------------------------------

def test_log_clamp_writes_expected_fields(tmp_path):
    log_path = tmp_path / "clamp_events.jsonl"
    log_clamp("n100_beta30_seed5 active", 42, -1.23e-5,
              script_name="test_unit", log_path=str(log_path))
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    import json as _json
    rec = _json.loads(lines[0])
    assert rec["script"] == "test_unit"
    assert rec["ctx"] == "n100_beta30_seed5 active"
    assert rec["position"] == 42
    assert rec["raw_value"] == pytest.approx(-1.23e-5)


def test_log_clamp_never_raises_on_permission_error(tmp_path, monkeypatch):
    """Locked-down fs path → log_clamp swallows OSError silently."""
    bad_path = "/root/definitely_not_writable/clamp.jsonl"
    # Must not raise
    log_clamp("ctx", 0, 0.0, script_name="t", log_path=bad_path)
