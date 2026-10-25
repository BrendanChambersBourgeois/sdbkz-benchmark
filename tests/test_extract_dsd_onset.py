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
    if recovered is not None:   # real seeds carry both keys (_bkz_core writes the pair)
        j[f"secret_recovered_{variant}"] = recovered
        j[f"secret_exact_match_{variant}"] = recovered
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


def test_all_ones_leg_is_no_fire():
    # g(1)=0 key: (0, 1) has norm2 n < secret -> recovered True, exact False.
    # Exact match wins even though gs would _is_dsd->True.
    s = {"secret_recovered_sdbkz": True, "secret_exact_match_sdbkz": False,
         "gs_lognorms_sdbkz": [2.0] * 50}
    assert ed._seed_fires(s, "sdbkz", 167) is False


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


def test_cell_rate_reads_one_tour_budget(base):
    # mt580 control beside the mt50 ladder: default counts mt50 only.
    _write(base, "ntru", 167, 40, 3061, [_seed(recovered=False)] * 20)
    d = base / "results" / "seeds" / "ntru" / "q3061" / "p500_mt580" / "n167_beta40"
    d.mkdir(parents=True)
    for i in range(8):
        (d / f"seed{i:04d}.json").write_text(json.dumps(_seed(recovered=True)))
    assert ed._cell_rate("ntru", 167, 40, 3061, "sdbkz") == (0, 20)
    assert ed._cell_rate("ntru", 167, 40, 3061, "sdbkz", max_tours=580) == (8, 8)
    assert ed._q_grid("ntru", 167, 40, max_tours=200) == []


def test_cell_rate_pools_precisions_at_one_budget(base):
    # n=89 q=97 shape: p250_mt50 + p500_mt50 reruns with the same seed ids.
    # Both precisions count (5 + 4 = 9 seeds); q appears once on the grid.
    for prec, seeds in (("p250", [_seed(recovered=True)] * 3 + [_seed(recovered=False)] * 2),
                        ("p500", [_seed(recovered=True)] * 2 + [_seed(recovered=False)] * 2)):
        d = base / "results" / "seeds" / "ntru" / "q97" / f"{prec}_mt50" / "n089_beta20"
        d.mkdir(parents=True)
        for i, s in enumerate(seeds):
            (d / f"seed{i + 1:04d}.json").write_text(json.dumps(s))
    assert ed._cell_rate("ntru", 89, 20, 97, "sdbkz") == (5, 9)
    assert ed._q_grid("ntru", 89, 20) == [97]
