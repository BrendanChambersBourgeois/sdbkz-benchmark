"""Tests for the v1.5.1 stats helpers: Cliff's δ + Holm-Bonferroni.

Covers:
  - Cliff's δ edge cases (all-win, all-loss, all-tie, mixed, empty)
  - Cliff's δ ↔ sign(advantage) invariant
  - Holm-Bonferroni monotonicity, ordering preservation, edge cases
  - Holm equivalence to Bonferroni when all p-values are equal
  - Holm strict-dominance over Bonferroni for the canonical mixed case
  - `None` pass-through

Synthetic inputs only — never touches `results/seeds/`.
"""
from __future__ import annotations

import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pytest  # noqa: E402

from analysis._stats_helpers import cliffs_delta, holm_bonferroni  # noqa: E402

# ── Cliff's δ ──────────────────────────────────────────────────────────────

def test_cliffs_delta_all_wins():
    assert cliffs_delta([0.1, 0.5, 1.0, 2.0]) == pytest.approx(1.0)


def test_cliffs_delta_all_losses():
    assert cliffs_delta([-0.1, -0.5, -1.0, -2.0]) == pytest.approx(-1.0)


def test_cliffs_delta_all_ties():
    assert cliffs_delta([0.0, 0.0, 0.0]) == pytest.approx(0.0)


def test_cliffs_delta_empty():
    assert cliffs_delta([]) == pytest.approx(0.0)


def test_cliffs_delta_mixed_balanced():
    assert cliffs_delta([1.0, -1.0]) == pytest.approx(0.0)


def test_cliffs_delta_mixed_majority():
    assert cliffs_delta([1.0, 1.0, 1.0, -1.0]) == pytest.approx(0.5)


def test_cliffs_delta_ties_dilute_magnitude():
    assert cliffs_delta([1.0, 0.0, 0.0, 0.0]) == pytest.approx(0.25)


def test_cliffs_delta_sign_matches_mean_direction():
    advs = [0.4, 0.3, -0.1, 0.6, -0.2]
    delta = cliffs_delta(advs)
    assert delta > 0
    assert math.copysign(1.0, delta) == math.copysign(1.0, sum(advs))


def test_cliffs_delta_range_bounded():
    advs = [1e9, -1e9, 1e9, -1e9, 1.0]
    delta = cliffs_delta(advs)
    assert -1.0 <= delta <= 1.0


# ── Holm-Bonferroni ───────────────────────────────────────────────────────

def test_holm_monotonic_in_sorted_p_order():
    raw = [0.001, 0.01, 0.02, 0.04]
    adj = holm_bonferroni(raw)
    pairs = list(zip(sorted(raw), sorted(a for a in adj if a is not None), strict=False))
    sorted_adj = [a for _, a in pairs]
    for i in range(1, len(sorted_adj)):
        assert sorted_adj[i] >= sorted_adj[i - 1]


def test_holm_preserves_input_order():
    raw = [0.04, 0.001, 0.02, 0.01]
    adj = holm_bonferroni(raw)
    assert len(adj) == len(raw)
    smallest_idx = raw.index(min(raw))
    assert adj[smallest_idx] == min(a for a in adj if a is not None)


def test_holm_smallest_equals_bonferroni_for_smallest():
    raw = [0.001, 0.01, 0.02, 0.04]
    adj = holm_bonferroni(raw)
    assert adj[0] == pytest.approx(0.001 * 4)


def test_holm_caps_at_one():
    raw = [0.3, 0.4, 0.5, 0.6]
    adj = holm_bonferroni(raw)
    assert all(a is not None and a <= 1.0 for a in adj)
    assert max(adj) == pytest.approx(1.0)


def test_holm_equals_bonferroni_when_all_p_identical():
    raw = [0.01, 0.01, 0.01, 0.01]
    adj = holm_bonferroni(raw)
    assert adj[0] == pytest.approx(0.04)
    assert all(a == pytest.approx(0.04) for a in adj)


def test_holm_dominates_bonferroni_strictly_in_mixed_case():
    raw = [0.001, 0.04, 0.05, 0.5]
    holm = holm_bonferroni(raw)
    bonf = [min(1.0, p * len(raw)) for p in raw]
    for h, b in zip(holm, bonf, strict=True):
        assert h <= b + 1e-12
    assert any(h < b - 1e-12 for h, b in zip(holm, bonf, strict=True))


def test_holm_none_passthrough():
    raw = [0.01, None, 0.02, None]
    adj = holm_bonferroni(raw)
    assert adj[1] is None
    assert adj[3] is None
    assert adj[0] == pytest.approx(0.01 * 2)
    assert adj[2] == pytest.approx(0.02 * 1)


def test_holm_all_none_returns_all_none():
    raw = [None, None, None]
    adj = holm_bonferroni(raw)
    assert adj == [None, None, None]


def test_holm_empty_returns_empty():
    adj = holm_bonferroni([])
    assert adj == []


def test_holm_family_of_one_unchanged():
    adj = holm_bonferroni([0.03])
    assert adj == [pytest.approx(0.03)]
