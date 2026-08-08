"""INC-53 — tour-count check validates against the seed's OWN max_tours budget,
not a hardcoded per-beta convention cap.

The old check `max_tours = {20:50,30:70,40:100}.get(beta)` froze the onset
convention as a hard cap, so deliberate deep-tour campaigns (the mt580 β=40
wall-control, mt1000 anchors) were flagged as schema errors and failed the daily
offsite sync on 8 legitimate seeds. The fix checks bkz_tours_run against the
seed's declared max_tours, falling back to the convention only for legacy seeds
that predate the field. The over-budget test also guards that section 5f actually
runs (if it were skipped, that test would fail).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from validate_seeds import SeedValidator  # noqa: E402

# A GS-bearing β=40 record complete enough to reach the tour-count check (5f).
_BASE = {
    "n": 167, "beta": 40, "seed": 1, "status": "completed",
    "advantage": 0.1, "q": 3061, "bkz_final_dln": 1.0, "sdbkz_final_dln": 0.9,
    "dim": 334,
    "initial_gs_lognorms": [0.0] * 334,
    "gs_lognorms_bkz": [0.0] * 334,
    "gs_lognorms_sdbkz": [0.0] * 334,
}


def _tour_errors(tmp_path, payload):
    d = tmp_path / "main" / "q3061" / "n167_beta40"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "seed0001.json"
    p.write_text(json.dumps(payload))
    v = SeedValidator()
    v.check_seed(str(p), "main")
    return [e for e in v.errors if "bkz_tours=" in e]


def test_deep_tour_within_own_budget_passes(tmp_path):
    # mt580 wall-control shape: 580 tours, declared budget 580 -> OK.
    assert _tour_errors(tmp_path, dict(_BASE, bkz_tours_run=580, max_tours=580)) == []


def test_over_own_budget_errors(tmp_path):
    # 581 tours vs a declared 580 budget -> real over-budget error (also proves 5f runs).
    errs = _tour_errors(tmp_path, dict(_BASE, bkz_tours_run=581, max_tours=580))
    assert any("bkz_tours=581" in e for e in errs), errs


def test_legacy_no_maxtours_within_convention_passes(tmp_path):
    # No max_tours field -> fall back to the β=40 convention cap (100); 100 <= 100 OK.
    assert _tour_errors(tmp_path, dict(_BASE, bkz_tours_run=100)) == []


def test_legacy_no_maxtours_over_convention_errors(tmp_path):
    # No max_tours field, 150 tours > convention cap 100 -> error preserved.
    errs = _tour_errors(tmp_path, dict(_BASE, bkz_tours_run=150))
    assert any("bkz_tours=150" in e for e in errs), errs


def test_standard_onset_seed_passes(tmp_path):
    assert _tour_errors(tmp_path, dict(_BASE, bkz_tours_run=50, max_tours=50)) == []
