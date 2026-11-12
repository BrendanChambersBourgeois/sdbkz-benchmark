"""spatial_decomposition: magnitude shares and largest_region hold for loss groups."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis import tables  # noqa: E402


def test_loss_group_uses_magnitudes(monkeypatch):
    fake = {1: (0.2, -0.6, -0.2), 2: (0.0, -0.4, -0.2)}
    monkeypatch.setattr(tables, "_decompose_seed", lambda s: fake[s["seed"]])
    groups = {(130, 40): [{"seed": 1}, {"seed": 2}]}
    (rec,) = tables.spatial_decomposition(groups, min_seeds=1)
    assert rec["largest_region"] == "MID"
    assert [rec[f"pct_{r}"] for r in ("head", "mid", "tail")] == pytest.approx([12.5, 62.5, 25.0])
    assert rec["head_win_rate"] == 50.0 and rec["mid_win_rate"] == 0.0
    assert tables.table_spatial(groups, min_seeds=1) == []
