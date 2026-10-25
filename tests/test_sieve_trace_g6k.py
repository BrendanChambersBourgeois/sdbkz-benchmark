"""The opt-in sieve trace must not move the g6k reduction.

Runs only where g6k imports (the sdbkz-g6k images), e.g.
    docker run --rm -v "$PWD:/experiment" -w /experiment \
        sdbkz-g6k:dim384-inc63 python3 -m pytest -q tests/test_sieve_trace_g6k.py
"""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("g6k")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from _bkz_core import run_single  # noqa: E402
from generators import build_ntru, get_metric_span  # noqa: E402

N, Q, BETA, SEED, TOURS = 40, 257, 30, 3, 2


def _run(**kw):
    L, f, g = build_ntru(N, Q, seed=SEED)
    m0, m1 = get_metric_span("ntru")(N, len(L))
    return run_single(L=L, n=N, active_block_start=m0, active_block_end=m1,
                      beta=BETA, seed=SEED, q=Q, precision=200,
                      max_tours=TOURS, log_clamp_fn=None, backend="g6k",
                      secret_f=f, secret_g=g, **kw)


def test_trace_on_is_bit_identical_to_trace_off():
    recs = []
    plain = _run()
    traced = _run(sieve_trace=True, tour_cb=lambda *a: recs.append(a))
    volatile = {"timestamp", "bkz_time", "sdbkz_time"}
    assert {k: v for k, v in plain.items() if k not in volatile} == \
        {k: v for k, v in traced.items() if k not in volatile}
    for variant, passes in (("bkz", {"primal"}), ("sdbkz", {"primal", "dual"})):
        rows = [r for r in recs if r[0] == variant]
        assert [r[1] for r in rows] == list(range(1, len(rows) + 1))
        for r in rows:
            assert set(r[5]) == passes
            for p in r[5].values():
                assert p["pumps"] > 0 and p["by_alg"] and p["max_db"] > 0
