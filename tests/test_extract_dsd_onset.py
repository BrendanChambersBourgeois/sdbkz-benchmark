"""Tests for the recovery-first scoring in extract_dsd_onset (track 2 A/B).

Pins two behaviours the deep audit (2026-07-04, finding 3) required:
  * a contaminated-but-RECOVERED seed counts as a fire (the cancellation-free
    recovery field wins over the GSO _is_dsd verdict, which false-nulls it);
  * a pre-fix seed with no recovery field routes through _is_dsd unchanged
    (this is what keeps the committed n<=113 tab:dsdgap trend byte-identical).
All I/O is against a tmp seed tree (BASE monkeypatched); no real cell is read.
"""
import importlib
import json

import pytest

ed = importlib.import_module("extract_dsd_onset")


def _seed(recovered=None, gs=None, variant="sdbkz"):
    j = {}
    if recovered is not None:
        j[f"secret_recovered_{variant}"] = recovered
    if gs is not None:
        j[f"gs_lognorms_{variant}"] = gs
    return j


# --- _seed_fires: recovery-first, _is_dsd fallback ---------------------------

def test_recovered_true_fires_regardless_of_gs():
    # poisoned GS (would _is_dsd->False) but recovery True => FIRE. The fix.
    s = _seed(recovered=True, gs=[-345.4] * 50)
    assert ed._seed_fires(s, "sdbkz", 157) is True


def test_recovered_false_is_no_fire():
    s = _seed(recovered=False, gs=[2.0] * 50)   # gs would _is_dsd->True
    assert ed._seed_fires(s, "sdbkz", 157) is False


def test_prefix_seed_routes_through_is_dsd():
    # no recovery field => must equal _is_dsd exactly (byte-identity guarantee).
    for gs in ([2.0] * 30, [1.0] * 30, [3.0] * 5 + [0.4] * 40):
        s = _seed(gs=gs)
        assert ed._seed_fires(s, "sdbkz", 89) == ed._is_dsd(s, "sdbkz", 89)


def test_seed_is_poisoned_detects_sentinel():
    assert ed._seed_is_poisoned(_seed(gs=[2.0, 2.0, -345.4]), "sdbkz") is True
    assert ed._seed_is_poisoned(_seed(gs=[2.0, 2.0, 1.9]), "sdbkz") is False


# --- _cell_rate end to end ---------------------------------------------------

@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "BASE", str(tmp_path))
    return tmp_path


def _write(base, tree, n, beta, q, seeds):
    d = base / "results" / "seeds" / tree / f"q{q}" / "p500_mt50" / \
        f"n{n:03d}_beta{beta:02d}"
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(seeds):
        (d / f"seed{i:04d}.json").write_text(json.dumps(s))


def test_cell_rate_counts_recovered_frontier(base):
    seeds = [_seed(recovered=True, gs=[-345.4] * 314) for _ in range(13)] + \
            [_seed(recovered=False, gs=[-345.4] * 314) for _ in range(7)]
    _write(base, "ntru", 157, 40, 2411, seeds)
    assert ed._cell_rate("ntru", 157, 40, 2411, "sdbkz") == (13, 20)


def test_cell_rate_missing_cell_is_none(base):
    assert ed._cell_rate("ntru", 157, 40, 9999, "sdbkz") is None


def test_cell_rate_prefix_cell_matches_is_dsd(base):
    # pre-fix (no recovery field): fires must equal a direct _is_dsd tally.
    seeds = [_seed(gs=[2.0] * 40) for _ in range(3)] + \
            [_seed(gs=[1.0] * 40) for _ in range(2)]
    _write(base, "ntru", 89, 20, 200, seeds)
    fires, total = ed._cell_rate("ntru", 89, 20, 200, "sdbkz")
    expect = sum(ed._is_dsd(s, "sdbkz", 89) for s in seeds)
    assert (fires, total) == (expect, 5)
