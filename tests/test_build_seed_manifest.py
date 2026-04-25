"""Edge-case tests for scripts/build_seed_manifest.py.

Covers the five minimum scenarios called out in the v1.3 plan:
empty dir, single seed, fat+lean pair, q3329 with a fat companion,
and schema validation rejects.
"""

import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import build_seed_manifest as bsm  # noqa: E402


def _write_seed(dirpath, fname, **overrides):
    os.makedirs(dirpath, exist_ok=True)
    base = {
        "n": 50,
        "beta": 20,
        "seed": 1,
        "q": 97,
        "precision": 250,
        "max_tours": 70,
        "store_per_tour": False,
        "dim": 151,
        "m": 100,
        "status": "completed",
        "advantage": 0.12345,
    }
    base.update(overrides)
    path = os.path.join(dirpath, fname)
    with open(path, "w") as f:
        json.dump(base, f)
    return path


def _minimal_tree(root, **seeds_by_campaign_dir):
    """Build a minimal results/ skeleton with only the dirs requested."""
    os.makedirs(root, exist_ok=True)
    for dirname, files in seeds_by_campaign_dir.items():
        d = os.path.join(root, dirname)
        os.makedirs(d, exist_ok=True)
        for fname, overrides in files:
            _write_seed(d, fname, **overrides)


def test_walk_empty_results_returns_empty(tmp_path):
    """No seed dirs present → manifest.seeds == []."""
    root = tmp_path / "results"
    root.mkdir()
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert rejects == []


def test_walk_single_seed_in_raw(tmp_path):
    """One seed in results/raw/ → one entry tagged campaign=main."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {})],
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 1
    e = entries[0]
    assert e["campaign"] == "main"
    assert (e["n"], e["beta"], e["seed"], e["q"]) == (50, 20, 1, 97)
    assert e["tags"] == []
    assert e["verified"] is True
    assert len(e["sha256"]) == 64


def test_walk_fat_lean_pair_in_q3329(tmp_path):
    """A seed with a fat companion → two entries, fat gets the tag."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        q3329=[
            ("n100_beta30_q3329_seed1.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 3329, "precision": 1000}),
            ("n100_beta30_q3329_seed1_fat.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 3329, "precision": 1000}),
        ],
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 2
    fat = [e for e in entries if "fat" in e["tags"]]
    lean = [e for e in entries if "fat" not in e["tags"]]
    assert len(fat) == 1 and len(lean) == 1
    assert all(e["campaign"] == "q3329" for e in entries)
    assert all(e["q"] == 3329 for e in entries)


def test_walk_rejects_incomplete_status(tmp_path):
    """status != 'completed' is rejected with a reason, not silently indexed."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {"status": "running"})],
    )
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 1
    _, reason = rejects[0]
    assert "status" in reason


def test_walk_rejects_missing_required_key(tmp_path):
    """Seed missing a required key rejected with explanatory reason."""
    root = tmp_path / "results"
    d = root / "raw"
    d.mkdir(parents=True)
    fp = d / "n50_beta20_seed1.json"
    with open(fp, "w") as f:
        json.dump({"n": 50, "beta": 20, "seed": 1, "status": "completed"}, f)
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 1
    _, reason = rejects[0]
    assert "missing" in reason.lower()


def test_walk_rejects_non_finite_advantage(tmp_path):
    """NaN / infinite advantage rejected — the paper's finiteness invariant."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[
            ("n50_beta20_seed1.json", {"advantage": float("nan")}),
            ("n50_beta20_seed2.json", {"seed": 2, "advantage": float("inf")}),
        ],
    )
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 2
    for _, reason in rejects:
        assert "finite" in reason


def test_walk_rejects_filename_content_mismatch(tmp_path):
    """JSON says seed=9 but filename says seed=1 → reject."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {"seed": 9})],
    )
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 1
    assert "mismatch" in rejects[0][1]


def test_walk_rejects_q_mismatch(tmp_path):
    """Filename says q=3329 but content says q=97 → reject."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        q3329=[
            ("n100_beta30_q3329_seed1.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 97}),
        ],
    )
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 1
    assert "q mismatch" in rejects[0][1]


def test_walk_fplll_sensitivity_populates_version(tmp_path):
    """Each fplll dir surfaces its version via the fplll_version field."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        fplll543_sensitivity=[
            ("n100_beta30_q97_seed1.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 97}),
        ],
        fplll544_sensitivity=[
            ("n100_beta30_q97_seed1.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 97}),
        ],
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 2
    versions = {e["fplll_version"] for e in entries}
    assert versions == {"5.4.3", "5.4.4"}
    assert all(e["campaign"] == "fplll_sensitivity" for e in entries)


def test_walk_3x_tours_tags_3x_files(tmp_path):
    """3x_tours/n60_beta30_3x_seed45.json → tag includes '3x'."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        **{"3x_tours": [
            ("n60_beta30_3x_seed45.json",
                {"n": 60, "beta": 30, "seed": 45, "max_tours": None,
                 "advantage_equal_tours": 0.15, "advantage_3x": 0.21}),
            ("n60_beta30_seed46.json",
                {"n": 60, "beta": 30, "seed": 46}),
        ]},
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 2
    tagged_3x = [e for e in entries if "3x" in e["tags"]]
    assert len(tagged_3x) == 1
    assert tagged_3x[0]["advantage"] == pytest.approx(0.15)


def test_sha256_matches_file_bytes(tmp_path):
    """Per-entry SHA-256 must match the exact file contents."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {})],
    )
    entries, _ = bsm.walk(str(root))
    e = entries[0]
    with open(e["path"], "rb") as f:
        expected = hashlib.sha256(f.read()).hexdigest()
    assert e["sha256"] == expected


def test_summarise_counts_per_campaign(tmp_path):
    """summarise() produces correct per-campaign totals + tag rollups."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {})],
        cloud=[("n50_beta20_seed2.json", {"seed": 2})],
        q3329=[
            ("n100_beta30_q3329_seed1.json",
                {"n": 100, "beta": 30, "seed": 1, "q": 3329}),
        ],
    )
    entries, _ = bsm.walk(str(root))
    summary = bsm.summarise(entries)
    assert summary["main"]["total_seeds"] == 2
    assert "cloud" in summary["main"]["tags"]
    assert summary["q3329"]["total_seeds"] == 1
    assert summary["q3329"]["q_values"] == [3329]


# ---------------- v1.3 native-layout walker --------------------------------


def _write_v13_seed(root, rel, **overrides):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    base = {
        "n": 50, "beta": 20, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70,
        "store_per_tour": False,
        "status": "completed", "advantage": 0.12345,
    }
    base.update(overrides)
    with open(full, "w") as f:
        json.dump(base, f)
    return full


def test_walk_v13_direct_main_seed(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root), "seeds/main/q97/n050_beta20/seed0001.json",
        n=50, beta=20, seed=1,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 1
    e = entries[0]
    assert e["campaign"] == "main"
    assert (e["n"], e["beta"], e["seed"]) == (50, 20, 1)
    assert e["tags"] == []


def test_walk_v13_q3329_parses_precision_and_max_tours(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/q3329/p1000_mt70/n090_beta30/seed0021.json",
        n=90, beta=30, seed=21, q=3329, precision=1000, max_tours=70,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 1
    e = entries[0]
    assert e["campaign"] == "q3329"
    assert e["precision"] == 1000
    assert e["max_tours"] == 70


def test_walk_v13_fplll_sensitivity_parses_version(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/fplll_sensitivity/v5_4_3/q97/n100_beta30/seed0001.json",
        n=100, beta=30, seed=1,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert entries[0]["fplll_version"] == "5.4.3"


def test_walk_v13_convergence_parses_max_tours_from_leaf(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/convergence/q97/n140_beta30_mt500/seed0010.json",
        n=140, beta=30, seed=10, max_tours=500,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert entries[0]["max_tours"] == 500


def test_walk_v13_cloud_suffix_tagged(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/main/q97/n050_beta20/seed0001_cloud.json",
        n=50, beta=20, seed=1,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert "cloud" in entries[0]["tags"]


def test_walk_v13_fat_companion_tagged(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/q3329/p1000_mt70/n100_beta30/seed0001.json",
        n=100, beta=30, seed=1, q=3329, precision=1000, max_tours=70,
    )
    _write_v13_seed(
        str(root),
        "seeds/q3329/p1000_mt70/n100_beta30/seed0001_fat.json",
        n=100, beta=30, seed=1, q=3329, precision=1000, max_tours=70,
    )
    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 2
    fat = [e for e in entries if "fat" in e["tags"]]
    assert len(fat) == 1


def test_walk_v13_dedup_symlink_and_canonical(tmp_path):
    root = tmp_path / "results"
    canonical = _write_v13_seed(
        str(root), "seeds/main/q97/n050_beta20/seed0001.json",
        n=50, beta=20, seed=1,
    )
    legacy_dir = root / "raw"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_link = legacy_dir / "n50_beta20_seed1.json"
    rel = os.path.relpath(canonical, str(legacy_dir))
    os.symlink(rel, str(legacy_link))

    entries, rejects = bsm.walk(str(root))
    assert rejects == []
    assert len(entries) == 1


def test_walk_v13_rejects_unknown_campaign(tmp_path):
    root = tmp_path / "results"
    _write_v13_seed(
        str(root),
        "seeds/portfolio/q97/n050_beta20/seed0001.json",
        n=50, beta=20, seed=1,
    )
    entries, rejects = bsm.walk(str(root))
    assert entries == []
    assert len(rejects) == 1
    _, reason = rejects[0]
    assert "v1.3 layout" in reason


def test_cli_writes_manifest_and_is_idempotent(tmp_path):
    """End-to-end CLI: builds manifest, re-run produces identical content."""
    root = tmp_path / "results"
    _minimal_tree(
        str(root),
        raw=[("n50_beta20_seed1.json", {})],
    )
    out = tmp_path / "manifest.json"
    argv = [
        "build_seed_manifest",
        "--results-root", str(root),
        "--output", str(out),
    ]
    old_argv = sys.argv
    try:
        sys.argv = argv
        rc = bsm.main()
        assert rc == 0
        m1 = json.load(open(out))
        sys.argv = argv
        rc = bsm.main()
        assert rc == 0
        m2 = json.load(open(out))
    finally:
        sys.argv = old_argv
    # generated_utc differs between runs (top-level field) and so does
    # per-entry verified_at_utc (re-stamped on every walk), so strip both
    # before content comparison. The remaining fields — n, beta, sha256,
    # mtime_utc (file mtime, not walk time), advantage, etc. — are
    # deterministic for an unchanged seed file.
    def _strip_volatile(seeds):
        return [{k: v for k, v in s.items() if k != "verified_at_utc"} for s in seeds]
    assert _strip_volatile(m1["seeds"]) == _strip_volatile(m2["seeds"])
    assert m1["campaigns"] == m2["campaigns"]
    assert m1["schema_version"] == bsm.SCHEMA_VERSION
