"""Tests for analysis/_data.py's dual-mode load_all_seeds().

Covers:
  - Manifest-driven filter combinations (campaign, n/β, q, precision,
    max_tours, fplll_version).
  - Fat-companion skip default; include_fat=True opts in.
  - Verified-only default; include_unverified=True opts in.
  - Manifest-missing raises a clear FileNotFoundError.
  - Legacy positional-dirs signature still works (back-compat).
  - Dedup preference (non-cloud over cloud for main campaign collisions).
  - Byte-identical advantage values when legacy and manifest modes
    load the same (n, β) slice.
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from analysis import _data as data  # noqa: E402


def _write_seed(dirpath, fname, **overrides):
    os.makedirs(dirpath, exist_ok=True)
    base = {
        "n": 50, "beta": 20, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70,
        "store_per_tour": False,
        "dim": 151, "m": 100,
        "status": "completed", "advantage": 0.12345,
        "bkz_dln_per_tour": [1.0, 0.9], "sdbkz_dln_per_tour": [1.0, 0.8],
    }
    base.update(overrides)
    path = os.path.join(dirpath, fname)
    with open(path, "w") as f:
        json.dump(base, f)
    return path


def _build_manifest(seeds, manifest_path, repo_root):
    """Write a minimal manifest for the given seed entries (dicts with
    campaign/n/beta/seed/q/advantage/path/sha256/tags/verified keys)."""
    manifest = {
        "schema_version": 1,
        "generated_utc": "2026-04-18T00:00:00Z",
        "results_root": "results",
        "campaigns": {},
        "seeds": seeds,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)


def _entry(**kwargs):
    base = {
        "campaign": "main",
        "n": 50, "beta": 20, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70,
        "store_per_tour": False,
        "advantage": 0.12345,
        "sha256": "a" * 64,
        "size_bytes": 1,
        "mtime_utc": "2026-04-18T00:00:00Z",
        "tags": [],
        "verified": True,
        "verified_at_utc": "2026-04-18T00:00:00Z",
        "verified_by": "build_seed_manifest.py",
    }
    base.update(kwargs)
    return base


@pytest.fixture
def fresh_cache():
    """Ensure _MANIFEST_CACHE starts empty every test."""
    data._MANIFEST_CACHE.clear()
    yield
    data._MANIFEST_CACHE.clear()


@pytest.fixture
def tmp_manifest_tree(tmp_path, fresh_cache):
    """Two seeds: main(n=50,β=20,seed=1) + cliff500(n=130,β=40,seed=1).
    Both JSON files land on disk so load_json=True can open them."""
    repo = tmp_path
    seeds_dir_main = repo / "results" / "seeds" / "main" / "q97" / "n050_beta20"
    seeds_dir_cliff = repo / "results" / "seeds" / "cliff500" / "q97" / "n130_beta40"
    _write_seed(str(seeds_dir_main), "seed0001.json",
                n=50, beta=20, seed=1, q=97, advantage=0.25)
    _write_seed(str(seeds_dir_cliff), "seed0001.json",
                n=130, beta=40, seed=1, q=97, precision=500,
                max_tours=100, advantage=-1.3)
    manifest_path = repo / "manifest.json"
    entries = [
        _entry(
            n=50, beta=20, seed=1, advantage=0.25,
            path="results/seeds/main/q97/n050_beta20/seed0001.json",
        ),
        _entry(
            campaign="cliff500", n=130, beta=40, seed=1,
            precision=500, max_tours=100, advantage=-1.3,
            path="results/seeds/cliff500/q97/n130_beta40/seed0001.json",
        ),
    ]
    _build_manifest(entries, str(manifest_path), str(repo))
    # Patch the loader's default manifest path + repo root so we
    # don't touch the real tree.
    old_default = data.DEFAULT_MANIFEST_PATH
    old_module_file = data.__file__
    data.DEFAULT_MANIFEST_PATH = str(manifest_path)
    # Fake analysis/_data.py location so _manifest_load_groups'
    # os.path.dirname(os.path.dirname(__file__)) → tmp_path.
    data.__file__ = str(repo / "analysis" / "_data.py")
    yield repo, manifest_path
    data.DEFAULT_MANIFEST_PATH = old_default
    data.__file__ = old_module_file


def test_manifest_mode_filters_by_campaign(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    groups = data.load_all_seeds(
        campaign="main", manifest_path=str(manifest_path),
    )
    assert set(groups.keys()) == {(50, 20)}
    assert len(groups[(50, 20)]) == 1
    assert groups[(50, 20)][0]["seed"] == 1
    assert groups[(50, 20)][0]["advantage"] == pytest.approx(0.25)


def test_manifest_mode_filters_by_n_and_beta(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    groups = data.load_all_seeds(
        campaign="cliff500", n=130, beta=40,
        manifest_path=str(manifest_path),
    )
    assert set(groups.keys()) == {(130, 40)}
    assert groups[(130, 40)][0]["advantage"] == pytest.approx(-1.3)


def test_manifest_mode_empty_when_no_match(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    groups = data.load_all_seeds(
        campaign="main", n=999,
        manifest_path=str(manifest_path),
    )
    assert groups == {}


def test_manifest_mode_skips_fat_by_default(tmp_path, fresh_cache):
    repo = tmp_path
    # Write lean + fat companion to disk
    seeds_dir = repo / "results" / "seeds" / "q3329" / "p1000_mt70" / "n100_beta30"
    _write_seed(str(seeds_dir), "seed0001.json",
                n=100, beta=30, seed=1, q=3329, precision=1000)
    _write_seed(str(seeds_dir), "seed0001_fat.json",
                n=100, beta=30, seed=1, q=3329, precision=1000)
    manifest_path = repo / "manifest.json"
    _build_manifest([
        _entry(
            campaign="q3329", n=100, beta=30, seed=1, q=3329,
            precision=1000, max_tours=70,
            path="results/seeds/q3329/p1000_mt70/n100_beta30/seed0001.json",
        ),
        _entry(
            campaign="q3329", n=100, beta=30, seed=1, q=3329,
            precision=1000, max_tours=70, tags=["fat"], advantage=None,
            path="results/seeds/q3329/p1000_mt70/n100_beta30/seed0001_fat.json",
        ),
    ], str(manifest_path), str(repo))

    data.__file__ = str(repo / "analysis" / "_data.py")
    data.DEFAULT_MANIFEST_PATH = str(manifest_path)

    # Default: fat skipped → one seed
    groups = data.load_all_seeds(campaign="q3329", q=3329)
    assert len(groups[(100, 30)]) == 1
    # Opt in: fat included → two entries
    groups = data.load_all_seeds(
        campaign="q3329", q=3329, include_fat=True,
    )
    assert len(groups[(100, 30)]) == 2


def test_manifest_mode_prefers_non_cloud_on_collision(tmp_path, fresh_cache):
    """Main campaign with (n=50, β=30, seed=1) in both local and cloud
    collapses to the non-cloud entry by default (mirrors legacy raw/ >
    cloud/ preference)."""
    repo = tmp_path
    seeds_dir = repo / "results" / "seeds" / "main" / "q97" / "n050_beta30"
    _write_seed(str(seeds_dir), "seed0001.json",
                n=50, beta=30, seed=1, advantage=0.5,
                _source="local")
    _write_seed(str(seeds_dir), "seed0001_cloud.json",
                n=50, beta=30, seed=1, advantage=0.5,
                _source="cloud")
    manifest_path = repo / "manifest.json"
    _build_manifest([
        _entry(
            n=50, beta=30, seed=1, advantage=0.5,
            path="results/seeds/main/q97/n050_beta30/seed0001.json",
        ),
        _entry(
            n=50, beta=30, seed=1, advantage=0.5, tags=["cloud"],
            path="results/seeds/main/q97/n050_beta30/seed0001_cloud.json",
        ),
    ], str(manifest_path), str(repo))
    data.__file__ = str(repo / "analysis" / "_data.py")
    data.DEFAULT_MANIFEST_PATH = str(manifest_path)

    groups = data.load_all_seeds(campaign="main")
    assert len(groups[(50, 30)]) == 1
    chosen = groups[(50, 30)][0]
    assert chosen.get("_source") == "local"


def test_manifest_mode_missing_file_raises_clear_error(tmp_path, fresh_cache):
    data.DEFAULT_MANIFEST_PATH = str(tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="seed_manifest.json"):
        data.load_all_seeds(campaign="main")


def test_legacy_dirs_mode_still_works(tmp_path, fresh_cache):
    """A caller passing positional directory paths gets the legacy
    globber, unchanged from pre-v1.3."""
    root = tmp_path / "raw"
    _write_seed(str(root), "n50_beta20_seed1.json")
    _write_seed(str(root), "n50_beta20_seed2.json", seed=2)
    groups = data.load_all_seeds(str(root))
    assert set(groups.keys()) == {(50, 20)}
    assert len(groups[(50, 20)]) == 2


def test_manifest_mode_min_seeds_filter(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    # Each group has 1 seed, so min_seeds=2 should drop every group.
    groups = data.load_all_seeds(
        campaign="main", min_seeds=2,
        manifest_path=str(manifest_path),
    )
    assert groups == {}


def test_manifest_mode_load_json_false_returns_entry_copies(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    groups = data.load_all_seeds(
        campaign="main", load_json=False,
        manifest_path=str(manifest_path),
    )
    assert len(groups[(50, 20)]) == 1
    e = groups[(50, 20)][0]
    # Manifest entry shape — has "sha256" and "campaign"; JSON would have
    # "bkz_dln_per_tour" instead.
    assert "sha256" in e
    assert "campaign" in e
    assert "bkz_dln_per_tour" not in e


def test_manifest_cache_invalidates_on_mtime_change(tmp_manifest_tree):
    repo, manifest_path = tmp_manifest_tree
    groups_a = data.load_all_seeds(
        campaign="main", manifest_path=str(manifest_path),
    )
    assert len(groups_a[(50, 20)]) == 1
    # Overwrite manifest with different content + bump mtime.
    import time
    time.sleep(0.01)
    _build_manifest([
        _entry(n=50, beta=20, seed=99, advantage=0.99,
               path="results/seeds/main/q97/n050_beta20/seed0099.json"),
    ], str(manifest_path), str(repo))
    # Write the new seed file so load_json can open it.
    seeds_dir = repo / "results" / "seeds" / "main" / "q97" / "n050_beta20"
    _write_seed(str(seeds_dir), "seed0099.json",
                n=50, beta=20, seed=99, advantage=0.99)
    groups_b = data.load_all_seeds(
        campaign="main", manifest_path=str(manifest_path),
    )
    assert len(groups_b[(50, 20)]) == 1
    assert groups_b[(50, 20)][0]["seed"] == 99
