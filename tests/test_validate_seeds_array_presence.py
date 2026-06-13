"""INC-45 Phase 3.5 — per-family array-presence assertion in validate_seeds.

Locks the hardening that turns a silently-skipped array check into a loud
failure: GS-bearing families (sweep/q3329/NTRU) MUST carry the three GS
profiles; trajectory families (convergence/tours3x) MUST carry finite
per-tour d(LN) arrays. Without these, a seed that lost its arrays to a bug
passed green — the INC-45 failure mode (pass via absence), one layer down.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from validate_seeds import SeedValidator  # noqa: E402

# A complete GS-bearing (REQUIRED_SWEEP) record minus the GS arrays — so it
# passes the required-key gate and reaches the presence check.
_SWEEP_BASE = {
    "n": 50, "beta": 20, "seed": 1, "status": "completed",
    "advantage": 0.1, "q": 97, "bkz_final_dln": 1.0, "sdbkz_final_dln": 0.9,
}


def _write(tmp_path, family, name, payload):
    d = tmp_path / family / "q97" / "n050_beta20"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(payload))
    return str(p)


def _errors_for(filepath, tag):
    v = SeedValidator()
    v.check_seed(filepath, tag)
    return v.errors


def test_gs_bearing_missing_arrays_errors(tmp_path):
    p = _write(tmp_path, "main", "seed0001.json", dict(_SWEEP_BASE))
    errs = _errors_for(p, "main")
    assert any("GS-bearing seed missing" in e for e in errs), errs


def test_gs_bearing_with_arrays_no_presence_error(tmp_path):
    payload = dict(_SWEEP_BASE, dim=151,
                   initial_gs_lognorms=[0.0] * 151,
                   gs_lognorms_bkz=[0.0] * 151,
                   gs_lognorms_sdbkz=[0.0] * 151)
    p = _write(tmp_path, "main", "seed0001.json", payload)
    errs = _errors_for(p, "main")
    assert not any("GS-bearing seed missing" in e for e in errs), errs


def test_trajectory_missing_dln_errors(tmp_path):
    # convergence schema (REQUIRED_CONV) needs only n/beta/seed.
    p = _write(tmp_path, "convergence", "seed0001.json",
               {"n": 50, "beta": 20, "seed": 1})
    errs = _errors_for(p, "convergence")
    assert sum("trajectory seed missing" in e for e in errs) == 2, errs


def test_trajectory_nonfinite_dln_errors(tmp_path):
    p = _write(tmp_path, "tours3x", "seed0001.json",
               {"n": 50, "beta": 20, "seed": 1,
                "advantage_equal_tours": 0.1, "advantage_3x": 0.2,
                "bkz_dln_per_tour": [1.0, float("nan")],
                "sdbkz_dln_per_tour": [1.0, 2.0]})
    errs = _errors_for(p, "tours3x")
    assert any("non-finite" in e and "bkz_dln_per_tour" in e for e in errs), errs


def test_trajectory_with_finite_dln_no_presence_error(tmp_path):
    p = _write(tmp_path, "convergence", "seed0001.json",
               {"n": 50, "beta": 20, "seed": 1,
                "bkz_dln_per_tour": [1.0, 0.9],
                "sdbkz_dln_per_tour": [1.0, 0.8]})
    errs = _errors_for(p, "convergence")
    assert not any("trajectory seed missing" in e for e in errs), errs
    assert not any("non-finite" in e for e in errs), errs
