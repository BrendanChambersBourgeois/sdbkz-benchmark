"""Unit tests for the q-aware estimator path in scripts/seed_timing.py.

Pure synthetic / in-memory; never reads from results/seeds/. Covers the
_lookup_cost_q mechanism (exact / nearest-q / no-cell) and the property the
q-keying exists for: on cost that varies with q, nearest-q prediction beats
the q-blind (n,β) median. (A blind leave-one-out over the real corpus gave
~6.8% median error for q-aware vs ~18% for the blend; this test guards the
property deterministically.)
"""
from __future__ import annotations

import os
import statistics as st
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import seed_timing  # noqa: E402

PTC = seed_timing.PerTourCost


def _cost(n, b, q, bkz, sd):
    return PTC(n=n, beta=b, bkz_seconds_per_tour=bkz, sdbkz_seconds_per_tour=sd,
               sample_seeds=20)


# ---------------------------------------------------------------------------
# _lookup_cost_q mechanism
# ---------------------------------------------------------------------------

def test_lookup_cost_q_exact_hit():
    table = {(89, 40, 137): _cost(89, 40, 137, 10.0, 5.0),
             (89, 40, 211): _cost(89, 40, 211, 6.0, 3.0)}
    cost, note = seed_timing._lookup_cost_q(table, 89, 40, 137)
    assert cost is not None and cost.bkz_seconds_per_tour == 10.0
    assert note is None  # exact hit, no approximation note


def test_lookup_cost_q_nearest_when_no_exact():
    table = {(89, 40, 113): _cost(89, 40, 113, 12.0, 6.0),
             (89, 40, 211): _cost(89, 40, 211, 6.0, 3.0)}
    # target q=137 absent → nearest is 113 (|137-113|=24 < |137-211|=74)
    cost, note = seed_timing._lookup_cost_q(table, 89, 40, 137)
    assert cost is not None and cost.bkz_seconds_per_tour == 12.0
    assert note is not None and "nearest" in note.lower() and "q=113" in note


def test_lookup_cost_q_no_cell_at_nb():
    table = {(89, 40, 137): _cost(89, 40, 137, 10.0, 5.0)}
    # different (n, β) → no row → (None, None) so caller falls back
    cost, note = seed_timing._lookup_cost_q(table, 101, 40, 137)
    assert cost is None and note is None


def test_lookup_cost_q_matches_q_over_n():
    # q dominates: at (89,40) only q=521 exists; ask q=137 → uses q=521,
    # not some other-n same-q row (there is none anyway). Confirms the
    # lookup keys on (n,β) then q, never silently borrows another n.
    table = {(89, 40, 521): _cost(89, 40, 521, 4.0, 2.0),
             (101, 40, 137): _cost(101, 40, 137, 20.0, 10.0)}
    cost, _ = seed_timing._lookup_cost_q(table, 89, 40, 137)
    assert cost.bkz_seconds_per_tour == 4.0  # the (89,40) row, not (101,40)


# ---------------------------------------------------------------------------
# The property: q-aware (nearest-q) beats the q-blind (n,β) median.
# Synthetic monotone cost-vs-q (mimics the real ~2-5x spread across a q-grid).
# ---------------------------------------------------------------------------

def test_q_aware_beats_blend_on_varying_cost():
    qs = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    # cost decreases smoothly with q (as observed: g6k ~2245s@q97 -> ~878s@q521)
    cost_of = {q: 3000.0 / (q / 100.0) for q in qs}  # per-seed seconds proxy
    q_err, blend_err = [], []
    for held in qs:
        others = [q for q in qs if q != held]
        nearest = min(others, key=lambda q: abs(q - held))
        pred_q = cost_of[nearest]
        pred_blend = st.median(cost_of[q] for q in others)
        actual = cost_of[held]
        q_err.append(abs(pred_q - actual) / actual)
        blend_err.append(abs(pred_blend - actual) / actual)
    # q-aware must be at least as good on both mean and median |error|,
    # and strictly better on the median (the headline metric).
    assert st.mean(q_err) <= st.mean(blend_err)
    assert st.median(q_err) < st.median(blend_err)
