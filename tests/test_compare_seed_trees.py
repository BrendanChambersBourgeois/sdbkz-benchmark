"""Tests for scripts/compare_seed_trees.py — cross-arch ntru_xarch vs ntru.

Builds isomorphic tmp trees and checks the three buckets (matched / mismatched /
topup-no-baseline) and the verdict rule (PASS iff >=1 matched and 0 mismatched).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import compare_seed_trees as cmp  # noqa: E402

_BASE = {
    "n": 73, "beta": 20, "seed": 1, "q": 97, "precision": 250, "max_tours": 50,
    "advantage": 8.6437, "bkz_final_dln": 28.4, "sdbkz_final_dln": 19.756,
    "gs_lognorms_bkz": [1.0, 2.0, 3.0],
    "bkz_time": 120.1, "sdbkz_time": 259.5,
    "timestamp": "2026-06-03T07:35:16+00:00", "status": "completed",
}


def _write(root, rel, **over):
    d = dict(_BASE)
    d.update(over)
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)
    return path


def _trees(tmp_path):
    return (str(tmp_path / "ntru_xarch"), str(tmp_path / "ntru"))


_REL = "q97/p250_mt50/n073_beta20/seed0001.json"


def test_identical_science_is_matched_and_pass(tmp_path):
    xr, cr = _trees(tmp_path)
    # Same science, but different env fields (timing/timestamp) -> still matched.
    _write(xr, _REL, bkz_time=1.0, timestamp="2030-01-01T00:00:00+00:00")
    _write(cr, _REL)
    res = cmp.compare(xr, cr, tol=1e-4)
    assert res["verdict"] == "PASS"
    assert res["n_matched"] == 1
    assert res["n_mismatched"] == 0
    assert res["n_topup_no_baseline"] == 0


def test_science_drift_is_mismatch_and_fail(tmp_path):
    xr, cr = _trees(tmp_path)
    _write(xr, _REL, advantage=9.0)
    _write(cr, _REL, advantage=8.6437)
    res = cmp.compare(xr, cr, tol=1e-4)
    assert res["verdict"] == "FAIL"
    assert res["n_mismatched"] == 1
    m = res["mismatched"][0]
    assert "advantage" in m["fields"]
    assert m["within_tol"] is False
    assert m["max_abs_diff"] > 0.1


def test_near_miss_flagged_within_tol(tmp_path):
    xr, cr = _trees(tmp_path)
    _write(xr, _REL, advantage=8.6437 + 1e-6)
    _write(cr, _REL, advantage=8.6437)
    res = cmp.compare(xr, cr, tol=1e-4)
    # different hash -> mismatch bucket, but flagged as within tolerance
    assert res["n_mismatched"] == 1
    assert res["mismatched"][0]["within_tol"] is True


def test_extra_seed_is_topup_not_error(tmp_path):
    xr, cr = _trees(tmp_path)
    _write(xr, _REL)                       # has counterpart
    _write(cr, _REL)
    _write(xr, "q97/p250_mt50/n073_beta20/seed0099.json", seed=99)  # no baseline
    res = cmp.compare(xr, cr, tol=1e-4)
    assert res["n_matched"] == 1
    assert res["n_mismatched"] == 0
    assert res["n_topup_no_baseline"] == 1
    assert res["verdict"] == "PASS"


def test_no_matched_pairs_is_not_pass(tmp_path):
    xr, cr = _trees(tmp_path)
    _write(xr, "q97/p250_mt50/n073_beta20/seed0099.json", seed=99)  # topup only
    res = cmp.compare(xr, cr, tol=1e-4)
    assert res["n_matched"] == 0
    assert res["verdict"] == "FAIL"  # nothing verified -> not a pass
