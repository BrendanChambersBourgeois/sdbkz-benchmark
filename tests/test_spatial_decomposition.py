"""spatial_decomposition: magnitude shares and largest_region hold for loss groups."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis import tables  # noqa: E402


def test_loss_group_uses_magnitudes(monkeypatch):
    fake = {1: (0.2, -0.6, -0.2), 2: (0.0, -0.4, -0.2)}
    monkeypatch.setattr(tables, "_decompose_seed", lambda s: fake[s["seed"]])
    monkeypatch.setattr(tables, "_split_seed", lambda s: None)
    groups = {(130, 40): [{"seed": 1}, {"seed": 2}]}
    (rec,) = tables.spatial_decomposition(groups, min_seeds=1)
    assert rec["largest_region"] == "MID"
    assert [rec[f"pct_{r}"] for r in ("head", "mid", "tail")] == pytest.approx([12.5, 62.5, 25.0])
    assert rec["head_win_rate"] == 50.0 and rec["mid_win_rate"] == 0.0
    assert tables.table_spatial(groups, min_seeds=1) == []


def test_split_sums_to_advantage_and_tracks_the_differing_part():
    import numpy as np

    from analysis._data import _split_seed
    rng = np.random.default_rng(0)
    size, beta = 61, 20

    def rankin(lognorms):
        cum = np.cumsum(lognorms)
        return list(cum - np.arange(1, size + 1) / size * cum[-1])

    lb = -0.03 * np.arange(size) + rng.normal(0, 0.05, size)
    ls = lb.copy()
    x = np.arange(size - beta)
    ls[:size - beta] -= 0.004 * (x - x.mean())   # bodies differ, tails and volume equal
    from _math_core import ln_fixed_point
    fp = np.array(ln_fixed_point(size, beta))
    adv = (np.mean(np.abs(np.array(rankin(lb)) - fp))
           - np.mean(np.abs(np.array(rankin(ls)) - fp)))
    body, tail, slope_bkz, slope_sd = _split_seed(
        {"beta": beta, "rankin_profile_bkz": rankin(lb), "rankin_profile_sdbkz": rankin(ls)})
    assert body + tail == pytest.approx(adv, abs=1e-12)
    assert tail == pytest.approx(0, abs=1e-12)
    assert slope_sd - slope_bkz == pytest.approx(0.004, abs=1e-9)
