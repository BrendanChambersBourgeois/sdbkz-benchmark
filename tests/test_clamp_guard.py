"""Track 2 C: the clamp-poison guard in analysis._data drops sentinel seeds
from advantage aggregates (deep audit 2026-07-04 finding 2)."""
import importlib
import warnings

import numpy as np

_data = importlib.import_module("analysis._data")


def _seed(adv, gs_bkz=None):
    return {"advantage": adv, "gs_lognorms_bkz": gs_bkz or [2.0, 2.0, 2.0],
            "gs_lognorms_sdbkz": [2.0, 2.0, 2.0]}


def test_sentinel_detected():
    assert _data._seed_has_sentinel(_seed(5.0, gs_bkz=[2.0, -345.4, 2.0])) is True
    assert _data._seed_has_sentinel(_seed(5.0)) is False


def test_group_advantages_drops_poisoned():
    groups = {("k",): [
        _seed(1.0), _seed(3.0),
        _seed(999.0, gs_bkz=[2.0, -345.4]),   # poisoned -> dropped
    ]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = _data._group_advantages(groups)
    assert np.array_equal(out[("k",)], np.array([1.0, 3.0]))


def test_group_advantages_clean_group_unchanged():
    groups = {("k",): [_seed(1.0), _seed(2.0), _seed(3.0)]}
    out = _data._group_advantages(groups)
    assert np.array_equal(out[("k",)], np.array([1.0, 2.0, 3.0]))
