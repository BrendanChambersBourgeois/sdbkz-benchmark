"""Unit tests for scripts/seed_timing.py.

Pure synthetic-fixture tests; never reads from results/seeds/. Fixture
JSONs live at tests/fixtures/synthetic_seeds/.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import seed_timing  # noqa: E402


FIXTURE_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "synthetic_seeds")
FIXTURE_GLOB = (os.path.join(FIXTURE_DIR, "seed_*.json"),)


# ---------------------------------------------------------------------------
# per_tour_cost_table
# ---------------------------------------------------------------------------

def test_table_parses_synthetic_fixtures():
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=FIXTURE_GLOB)
    assert (50, 20) in table
    assert (60, 30) in table
    assert (90, 30) in table
    assert table[(50, 20)].sample_seeds == 2
    assert table[(60, 30)].sample_seeds == 2
    assert table[(90, 30)].sample_seeds == 1


def test_table_per_tour_costs_match_expected():
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=FIXTURE_GLOB)
    cost_50_20 = table[(50, 20)]
    assert cost_50_20.bkz_seconds_per_tour == pytest.approx((300 / 70 + 320 / 70) / 2, rel=1e-9)
    assert cost_50_20.sdbkz_seconds_per_tour == pytest.approx((600 / 70 + 620 / 70) / 2, rel=1e-9)


def test_table_handles_empty_glob(tmp_path):
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=(str(tmp_path / "*.json"),))
    assert table == {}


def test_table_skips_invalid_json(tmp_path):
    (tmp_path / "broken.json").write_text("{not valid json")
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=(str(tmp_path / "*.json"),))
    assert table == {}


def test_table_skips_seeds_with_zero_tours(tmp_path):
    (tmp_path / "zero.json").write_text(json.dumps(
        {"n": 50, "beta": 20, "bkz_time": 100.0, "sdbkz_time": 200.0,
         "bkz_tours_run": 0, "sdbkz_tours_run": 0}
    ))
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=(str(tmp_path / "*.json"),))
    assert table == {}


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------

def test_cache_round_trip():
    table = seed_timing.per_tour_cost_table(seed_glob_patterns=FIXTURE_GLOB)
    serialised = seed_timing.per_tour_cost_table_to_dict(table)
    roundtripped = seed_timing.per_tour_cost_table_from_dict(serialised)
    assert roundtripped == table


def test_cache_from_dict_tolerates_garbage():
    assert seed_timing.per_tour_cost_table_from_dict({}) == {}
    assert seed_timing.per_tour_cost_table_from_dict({"entries": [{"oops": 1}]}) == {}
    # Non-dict input: also empty (defensive)
    assert seed_timing.per_tour_cost_table_from_dict(["not a dict"]) == {}  # type: ignore[arg-type]


def test_cache_path_used_when_fresher_than_seeds(tmp_path):
    cache_payload = {
        "schema_version": 1,
        "generated_utc_epoch": time.time(),
        "entries": [{"n": 999, "beta": 99,
                     "bkz_seconds_per_tour": 1.5,
                     "sdbkz_seconds_per_tour": 2.5,
                     "sample_seeds": 7}],
    }
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(cache_payload))
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    seed_file = seed_dir / "seed_old.json"
    seed_file.write_text(json.dumps({
        "n": 50, "beta": 20, "bkz_time": 100.0, "sdbkz_time": 200.0,
        "bkz_tours_run": 70, "sdbkz_tours_run": 70,
    }))
    # Make seed file look much older than cache so cache is preferred.
    old = time.time() - 86400
    os.utime(str(seed_file), (old, old))

    table = seed_timing.per_tour_cost_table(
        seed_glob_patterns=(str(seed_dir / "*.json"),),
        cache_path=str(cache_file),
    )
    # Cache wins: only the (999, 99) entry is present, NOT the (50, 20) entry.
    assert (999, 99) in table
    assert (50, 20) not in table


def test_cache_path_rebuilt_when_seed_newer(tmp_path):
    cache_payload = {
        "schema_version": 1,
        "generated_utc_epoch": time.time() - 86400,
        "entries": [{"n": 999, "beta": 99,
                     "bkz_seconds_per_tour": 1.5,
                     "sdbkz_seconds_per_tour": 2.5,
                     "sample_seeds": 7}],
    }
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(cache_payload))
    # Backdate cache so it appears stale relative to the about-to-be-created seed.
    old = time.time() - 86400
    os.utime(str(cache_file), (old, old))

    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    seed_file = seed_dir / "seed_fresh.json"
    seed_file.write_text(json.dumps({
        "n": 50, "beta": 20, "bkz_time": 100.0, "sdbkz_time": 200.0,
        "bkz_tours_run": 70, "sdbkz_tours_run": 70,
    }))
    # Seed file mtime is "now" (fresher than cache).

    table = seed_timing.per_tour_cost_table(
        seed_glob_patterns=(str(seed_dir / "*.json"),),
        cache_path=str(cache_file),
    )
    # Stale cache rejected; table rebuilt from seeds. (999,99) gone, (50,20) present.
    assert (50, 20) in table
    assert (999, 99) not in table


# ---------------------------------------------------------------------------
# estimate_sweep_wall — naive method
# ---------------------------------------------------------------------------

def test_estimator_naive_method_no_anchor():
    cost_table = {
        (50, 20): seed_timing.PerTourCost(
            n=50, beta=20,
            bkz_seconds_per_tour=4.0, sdbkz_seconds_per_tour=8.0,
            sample_seeds=10,
        ),
    }
    est = seed_timing.estimate_sweep_wall(
        n=50, beta=20, max_tours=100,
        num_seeds=20, num_workers=22,
        cost_table=cost_table,
        seed_glob_patterns=(),
    )
    # Naive: 100 tours × (4 + 8) s/tour = 1200 s = 0.333 h. Pool fits (20 ≤ 22) so parallel_factor=1.
    assert est.predicted_wall_h_naive == pytest.approx(1200 / 3600, rel=1e-9)
    assert est.predicted_wall_h_anchored is None
    assert est.method_recommended == "naive"
    assert est.anchor_used is None


def test_estimator_naive_pool_overflow_scales():
    cost_table = {
        (50, 20): seed_timing.PerTourCost(
            n=50, beta=20,
            bkz_seconds_per_tour=4.0, sdbkz_seconds_per_tour=8.0,
            sample_seeds=10,
        ),
    }
    est = seed_timing.estimate_sweep_wall(
        n=50, beta=20, max_tours=100,
        num_seeds=66, num_workers=22,  # 3:1 oversubscribed
        cost_table=cost_table,
        seed_glob_patterns=(),
    )
    # Pool overflow factor = ceil(66/22) = 3. 0.333 h × 3 = 1.0 h.
    assert est.predicted_wall_h_naive == pytest.approx(1.0, rel=1e-9)


def test_estimator_no_data_returns_unknown():
    est = seed_timing.estimate_sweep_wall(
        n=999, beta=99, max_tours=1000,
        cost_table={},
        seed_glob_patterns=(),
    )
    assert est.predicted_wall_h_naive is None
    assert est.predicted_wall_h_anchored is None
    assert est.method_recommended == "unknown"
    assert any("insufficient data" in note.lower() or "no per-tour" in note.lower()
               for note in est.notes)


def test_estimator_missing_target_cost_naive_unavailable():
    cost_table = {
        (60, 30): seed_timing.PerTourCost(
            n=60, beta=30,
            bkz_seconds_per_tour=8.0, sdbkz_seconds_per_tour=20.0,
            sample_seeds=10,
        ),
    }
    est = seed_timing.estimate_sweep_wall(
        n=999, beta=99, max_tours=100,
        cost_table=cost_table,
        seed_glob_patterns=(),
    )
    assert est.predicted_wall_h_naive is None
    assert any("no per-tour cost data" in n.lower() for n in est.notes)


# ---------------------------------------------------------------------------
# estimate_sweep_wall — anchored method
# ---------------------------------------------------------------------------

def test_estimator_anchored_uses_fixture_anchor():
    est = seed_timing.estimate_sweep_wall(
        n=60, beta=30, max_tours=500,
        num_seeds=20, num_workers=22,
        seed_glob_patterns=FIXTURE_GLOB,
        anchor_age_warn_days=10000.0,  # disable age warn for fresh fixtures
    )
    assert est.anchor_used == (90, 30, 500)
    assert est.predicted_wall_h_anchored is not None
    assert est.method_recommended == "anchored"
    # Anchor wall = 8400 + 20700 = 29100 s. Anchor per-tour = (8400+20700)/500 = 58.2.
    # Target per-tour at (60, 30) = (560+540)/2/70 + (1400+1380)/2/70 = 7.857 + 19.857 = 27.714.
    # Cost ratio ~27.714/58.2 = 0.476. tour_ratio = 500/500 = 1.
    # Scaled wall per seed = 29100 × 0.476 = 13862 s = 3.85 h.
    assert est.predicted_wall_h_anchored == pytest.approx(3.85, rel=0.05)
    # mad_h is 0.0 for a single-seed anchor (one wall sample).
    assert est.mad_h == pytest.approx(0.0, abs=1e-9)


def test_estimator_age_warn_flips_method_to_naive(tmp_path):
    # Build fixture-equivalent in tmp so we can backdate mtimes safely.
    fx_dir = tmp_path / "seeds"
    fx_dir.mkdir()
    payloads = [
        ("seed_anchor.json", {"n": 90, "beta": 30, "max_tours": 500, "seed": 1,
                              "bkz_time": 8400.0, "sdbkz_time": 20700.0,
                              "bkz_tours_run": 500, "sdbkz_tours_run": 500}),
        ("seed_target.json", {"n": 60, "beta": 30, "max_tours": 70, "seed": 1,
                              "bkz_time": 560.0, "sdbkz_time": 1400.0,
                              "bkz_tours_run": 70, "sdbkz_tours_run": 70}),
    ]
    for fname, p in payloads:
        (fx_dir / fname).write_text(json.dumps(p))
    # Backdate the anchor seed mtime to 30 days ago.
    anchor_path = fx_dir / "seed_anchor.json"
    old = time.time() - 30 * 86400
    os.utime(str(anchor_path), (old, old))

    est = seed_timing.estimate_sweep_wall(
        n=60, beta=30, max_tours=500,
        seed_glob_patterns=(str(fx_dir / "*.json"),),
        anchor_age_warn_days=7.0,
    )
    assert est.anchor_used == (90, 30, 500)
    assert est.anchor_age_days is not None and est.anchor_age_days > 25
    assert est.method_recommended == "naive"
    assert any("anchor age" in n.lower() for n in est.notes)


# ---------------------------------------------------------------------------
# Anchor selection
# ---------------------------------------------------------------------------

def test_anchor_selection_no_anchor_returns_unknown_or_naive(tmp_path):
    # Only short-mt seeds; no anchor candidate above min_max_tours=500.
    fx_dir = tmp_path / "seeds"
    fx_dir.mkdir()
    (fx_dir / "seed_short.json").write_text(json.dumps({
        "n": 60, "beta": 30, "max_tours": 70, "seed": 1,
        "bkz_time": 560.0, "sdbkz_time": 1400.0,
        "bkz_tours_run": 70, "sdbkz_tours_run": 70,
    }))
    est = seed_timing.estimate_sweep_wall(
        n=60, beta=30, max_tours=1000,
        seed_glob_patterns=(str(fx_dir / "*.json"),),
    )
    assert est.anchor_used is None
    assert est.predicted_wall_h_anchored is None
    assert est.method_recommended == "naive"
    assert any("no suitable anchor" in note.lower() for note in est.notes)


# ---------------------------------------------------------------------------
# Adjacent-dim extrapolation helper (v1.5.2 addition)
# ---------------------------------------------------------------------------

def _make_cost(n, beta, bkz, sdb):
    return seed_timing.PerTourCost(
        n=n, beta=beta,
        bkz_seconds_per_tour=bkz,
        sdbkz_seconds_per_tour=sdb,
        sample_seeds=10,
    )


def test_lookup_cost_exact_hit_returns_no_note():
    table = {(100, 30): _make_cost(100, 30, 5.0, 10.0)}
    cost, note = seed_timing._lookup_cost(table, 100, 30)
    assert cost is table[(100, 30)]
    assert note is None


def test_lookup_cost_interpolate_between_two_neighbours():
    table = {
        (100, 40): _make_cost(100, 40, 10.0, 20.0),
        (140, 40): _make_cost(140, 40, 30.0, 60.0),
    }
    cost, note = seed_timing._lookup_cost(table, 120, 40)
    assert cost is not None
    assert note is not None and "interpolat" in note.lower()
    assert cost.bkz_seconds_per_tour == pytest.approx(20.0)
    assert cost.sdbkz_seconds_per_tour == pytest.approx(40.0)
    assert cost.sample_seeds == 0


def test_lookup_cost_extrapolate_above_target():
    table = {
        (140, 40): _make_cost(140, 40, 80.0, 200.0),
        (150, 40): _make_cost(150, 40, 80.0, 190.0),
    }
    cost, note = seed_timing._lookup_cost(table, 160, 40)
    assert cost is not None
    assert note is not None and "extrapolat" in note.lower()
    assert cost.bkz_seconds_per_tour == pytest.approx(80.0)
    assert cost.sdbkz_seconds_per_tour == pytest.approx(180.0)
    assert cost.sample_seeds == 0


def test_lookup_cost_extrapolate_below_target():
    table = {
        (100, 40): _make_cost(100, 40, 50.0, 130.0),
        (110, 40): _make_cost(110, 40, 60.0, 150.0),
    }
    cost, note = seed_timing._lookup_cost(table, 80, 40)
    assert cost is not None
    assert note is not None and "extrapolat" in note.lower()
    assert cost.bkz_seconds_per_tour == pytest.approx(30.0)
    assert cost.sdbkz_seconds_per_tour == pytest.approx(90.0)


def test_lookup_cost_extrapolation_clamps_negative_to_zero():
    table = {
        (100, 40): _make_cost(100, 40, 10.0, 30.0),
        (110, 40): _make_cost(110, 40, 60.0, 150.0),
    }
    cost, note = seed_timing._lookup_cost(table, 50, 40)
    assert cost is not None
    assert cost.bkz_seconds_per_tour >= 0.0
    assert cost.sdbkz_seconds_per_tour >= 0.0


def test_lookup_cost_single_neighbour_returns_nearest():
    table = {(140, 40): _make_cost(140, 40, 80.0, 200.0)}
    cost, note = seed_timing._lookup_cost(table, 160, 40)
    assert cost is not None
    assert note is not None and "nearest-neighbour" in note.lower()
    assert cost.bkz_seconds_per_tour == pytest.approx(80.0)
    assert cost.sdbkz_seconds_per_tour == pytest.approx(200.0)
    assert cost.sample_seeds == 0


def test_lookup_cost_no_same_beta_returns_none():
    table = {(100, 30): _make_cost(100, 30, 5.0, 10.0)}
    cost, note = seed_timing._lookup_cost(table, 100, 40)
    assert cost is None
    assert note is not None and "no per-tour cost rows" in note.lower()


def test_lookup_cost_different_beta_does_not_contaminate():
    table = {
        (100, 30): _make_cost(100, 30, 5.0, 10.0),
        (150, 40): _make_cost(150, 40, 80.0, 200.0),
    }
    cost, note = seed_timing._lookup_cost(table, 160, 40)
    assert cost is not None
    # Only one β=40 row → nearest-neighbour fallback path.
    assert "nearest-neighbour" in note.lower()
    assert cost.bkz_seconds_per_tour == pytest.approx(80.0)


def test_estimator_extrapolates_when_target_row_missing():
    table = {
        (140, 40): _make_cost(140, 40, 80.0, 200.0),
        (150, 40): _make_cost(150, 40, 80.0, 190.0),
    }
    est = seed_timing.estimate_sweep_wall(
        n=160, beta=40, max_tours=1000,
        cost_table=table,
        seed_glob_patterns=(),
    )
    # Naive method should now succeed via extrapolation.
    assert est.predicted_wall_h_naive is not None
    assert any("extrapolat" in note.lower() for note in est.notes)
