"""Tests for scripts/migrate_seeds_to_new_layout.py.

Coverage:
  - new_path_for() per-campaign path rules match the design spec
  - fat companion co-locates with lean sibling under the same leaf dir
  - dry-run changes nothing on disk
  - --execute moves + symlinks + crosswalk writes
  - --execute is idempotent (re-run no-ops on already-migrated tree)
  - preflight rejects manifests that reference missing files
  - collisions on the new_path are surfaced as preflight problems
"""

import csv
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_seed_manifest as bsm  # noqa: E402
import migrate_seeds_to_new_layout as mig  # noqa: E402


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


def _build_manifest(results_root, manifest_path):
    entries, rejects = bsm.walk(str(results_root))
    manifest = {
        "schema_version": 1,
        "generated_utc": "2026-04-18T00:00:00Z",
        "results_root": "results",
        "campaigns": bsm.summarise(entries),
        "seeds": entries,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    return manifest, rejects


# ---------------- new_path_for(): per-campaign spec ------------------------


def test_new_path_main_sweep():
    entry = {
        "campaign": "main", "n": 100, "beta": 30, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70, "tags": [],
    }
    assert mig.new_path_for(entry) == os.path.join(
        "results", "seeds", "main", "q97", "n100_beta30", "seed0001.json"
    )


def test_new_path_q3329_embeds_precision_and_max_tours():
    entry = {
        "campaign": "q3329", "n": 100, "beta": 30, "seed": 11, "q": 3329,
        "precision": 1000, "max_tours": 70, "tags": [],
    }
    assert mig.new_path_for(entry) == os.path.join(
        "results", "seeds", "q3329",
        "p1000_mt70", "n100_beta30", "seed0011.json"
    )


def test_new_path_q3329_fat_uses_fat_suffix():
    entry = {
        "campaign": "q3329", "n": 100, "beta": 30, "seed": 56, "q": 3329,
        "precision": 1000, "max_tours": 70, "tags": ["fat"],
    }
    assert mig.new_path_for(entry).endswith("seed0056_fat.json")


def test_new_path_cliff500():
    entry = {
        "campaign": "cliff500", "n": 130, "beta": 40, "seed": 1, "q": 97,
        "precision": 500, "max_tours": 100, "tags": [],
    }
    assert mig.new_path_for(entry) == os.path.join(
        "results", "seeds", "cliff500", "q97",
        "n130_beta40", "seed0001.json"
    )


def test_new_path_fplll_sensitivity_version_slug():
    entry = {
        "campaign": "fplll_sensitivity", "n": 100, "beta": 30,
        "seed": 3, "q": 97, "precision": 250, "max_tours": 70,
        "tags": ["v5.4.3"], "fplll_version": "5.4.3",
    }
    assert mig.new_path_for(entry) == os.path.join(
        "results", "seeds", "fplll_sensitivity",
        "v5_4_3", "q97", "n100_beta30", "seed0003.json"
    )


def test_new_path_fplll_sensitivity_rejects_missing_version():
    entry = {
        "campaign": "fplll_sensitivity", "n": 100, "beta": 30,
        "seed": 1, "q": 97, "tags": ["v5.4.3"],
    }
    import pytest
    with pytest.raises(ValueError, match="fplll_version"):
        mig.new_path_for(entry)


def test_new_path_tours3x():
    entry = {
        "campaign": "tours3x", "n": 60, "beta": 30, "seed": 45, "q": 97,
        "precision": 250, "max_tours": None, "tags": ["3x"],
    }
    assert mig.new_path_for(entry).endswith(
        os.path.join("tours3x", "q97", "n060_beta30", "seed0045.json")
    )


def test_new_path_convergence_embeds_max_tours_in_leaf():
    entry = {
        "campaign": "convergence", "n": 140, "beta": 30, "seed": 10,
        "q": 97, "precision": 250, "max_tours": 500, "tags": [],
    }
    assert mig.new_path_for(entry).endswith(
        os.path.join("convergence", "q97", "n140_beta30_mt500", "seed0010.json")
    )


def test_new_path_main_cloud_vs_local_coexist_via_suffix():
    """results/raw/ and results/cloud/ share (n, β, seed) triples for
    the paper's §3.7 cross-environment verification; both copies must
    survive migration under distinct filenames at the same leaf dir."""
    local = {
        "campaign": "main", "n": 50, "beta": 30, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70, "tags": [],
    }
    cloud = dict(local, tags=["cloud"])
    lp = mig.new_path_for(local)
    cp = mig.new_path_for(cloud)
    assert lp != cp
    assert os.path.dirname(lp) == os.path.dirname(cp)
    assert lp.endswith("seed0001.json")
    assert cp.endswith("seed0001_cloud.json")


def test_new_path_rejects_unknown_campaign():
    import pytest
    with pytest.raises(ValueError, match="unknown campaign"):
        mig.new_path_for({
            "campaign": "portfolio", "n": 1, "beta": 1, "seed": 1,
            "q": 97, "tags": [],
        })


# ---------------- plan_moves + fat co-location -----------------------------


def test_plan_moves_pairs_fat_with_lean_in_same_leaf(tmp_path):
    root = tmp_path / "results"
    q_dir = root / "q3329"
    q_dir.mkdir(parents=True)
    _write_seed(
        str(q_dir), "n100_beta30_q3329_seed1.json",
        n=100, beta=30, seed=1, q=3329, precision=1000,
    )
    _write_seed(
        str(q_dir), "n100_beta30_q3329_seed1_fat.json",
        n=100, beta=30, seed=1, q=3329, precision=1000,
    )
    manifest, _ = _build_manifest(str(root), str(tmp_path / "manifest.json"))
    moves = mig.plan_moves(manifest)

    assert len(moves) == 2
    lean = [m for m in moves if not m.is_fat][0]
    fat = [m for m in moves if m.is_fat][0]
    assert os.path.dirname(lean.new_path) == os.path.dirname(fat.new_path)
    assert lean.new_path.endswith("seed0001.json")
    assert fat.new_path.endswith("seed0001_fat.json")


# ---------------- preflight ----------------------------------------------


def test_preflight_blocks_missing_source(tmp_path):
    root = tmp_path / "results"
    raw = root / "raw"
    raw.mkdir(parents=True)
    _write_seed(str(raw), "n50_beta20_seed1.json")
    manifest, _ = _build_manifest(str(root), str(tmp_path / "manifest.json"))
    moves = mig.plan_moves(manifest)
    # Remove the source file after the plan is built.
    os.unlink(os.path.join(str(root), "raw", "n50_beta20_seed1.json"))
    problems = mig.preflight_checks(moves)
    assert len(problems) == 1
    assert "missing source" in problems[0]


def test_preflight_detects_new_path_collision(tmp_path):
    mv1 = mig.Move(
        old_path="a.json",
        new_path="results/seeds/main/q97/n050_beta20/seed0001.json",
        sha256="a" * 64, campaign="main",
        n=50, beta=20, seed=1, is_fat=False, size_bytes=100,
    )
    mv2 = mig.Move(
        old_path="b.json",
        new_path="results/seeds/main/q97/n050_beta20/seed0001.json",
        sha256="b" * 64, campaign="main",
        n=50, beta=20, seed=1, is_fat=False, size_bytes=100,
    )
    # Both source paths need to exist for the missing-source check to
    # not mask the collision check.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.json")
        b = os.path.join(td, "b.json")
        open(a, "w").close()
        open(b, "w").close()
        mv1 = mig.Move(
            old_path=a, new_path=mv1.new_path, sha256=mv1.sha256,
            campaign=mv1.campaign, n=mv1.n, beta=mv1.beta, seed=mv1.seed,
            is_fat=mv1.is_fat, size_bytes=mv1.size_bytes,
        )
        mv2 = mig.Move(
            old_path=b, new_path=mv2.new_path, sha256=mv2.sha256,
            campaign=mv2.campaign, n=mv2.n, beta=mv2.beta, seed=mv2.seed,
            is_fat=mv2.is_fat, size_bytes=mv2.size_bytes,
        )
        problems = mig.preflight_checks([mv1, mv2])
        assert any("collision" in p for p in problems)


# ---------------- dry-run is a no-op --------------------------------------


def test_dry_run_changes_nothing(tmp_path, capsys):
    root = tmp_path / "results"
    raw = root / "raw"
    raw.mkdir(parents=True)
    _write_seed(str(raw), "n50_beta20_seed1.json")
    manifest_path = tmp_path / "manifest.json"
    _build_manifest(str(root), str(manifest_path))

    before = {
        os.path.relpath(os.path.join(d, f), str(root))
        for d, _, files in os.walk(str(root)) for f in files
    }
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        argv = [
            "migrate",
            "--manifest", str(manifest_path),
            "--crosswalk-out", str(tmp_path / "crosswalk.csv"),
            "--dry-run",
        ]
        old_argv = sys.argv
        try:
            sys.argv = argv
            rc = mig.main()
        finally:
            sys.argv = old_argv
        assert rc == 0
    finally:
        os.chdir(old_cwd)

    after = {
        os.path.relpath(os.path.join(d, f), str(root))
        for d, _, files in os.walk(str(root)) for f in files
    }
    assert before == after
    # Crosswalk must not be written during --dry-run.
    assert not os.path.exists(str(tmp_path / "crosswalk.csv"))
    out = capsys.readouterr().out
    assert "DRY-RUN complete" in out
    assert "No filesystem changes" in out


# ---------------- --execute: move + symlink + crosswalk --------------------


def _make_tree_and_manifest(tmp_path):
    root = tmp_path / "results"
    raw = root / "raw"
    q3329 = root / "q3329"
    raw.mkdir(parents=True)
    q3329.mkdir(parents=True)
    _write_seed(str(raw), "n50_beta20_seed1.json")
    _write_seed(
        str(q3329), "n100_beta30_q3329_seed1.json",
        n=100, beta=30, seed=1, q=3329, precision=1000,
    )
    manifest_path = tmp_path / "manifest.json"
    _build_manifest(str(root), str(manifest_path))
    return root, manifest_path


def _run_migrate(tmp_path, manifest_path, extra=()):
    argv = [
        "migrate",
        "--manifest", str(manifest_path),
        "--crosswalk-out", str(tmp_path / "crosswalk.csv"),
    ] + list(extra)
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        sys.argv = argv
        os.chdir(str(tmp_path))
        return mig.main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


def test_execute_moves_files_and_writes_crosswalk(tmp_path):
    root, manifest_path = _make_tree_and_manifest(tmp_path)
    assert _run_migrate(tmp_path, manifest_path, ["--execute"]) == 0

    # Old paths are now symlinks pointing into the new tree.
    old_raw = root / "raw" / "n50_beta20_seed1.json"
    assert old_raw.is_symlink()
    resolved = (root / "raw" / os.readlink(old_raw)).resolve()
    assert resolved.exists()
    assert "seeds/main/q97/n050_beta20/seed0001.json" in str(resolved)

    # New path holds the actual content.
    new_main = root / "seeds" / "main" / "q97" / "n050_beta20" / "seed0001.json"
    assert new_main.is_file()
    with open(new_main) as f:
        assert json.load(f)["seed"] == 1

    # q3329 entry ends up in p1000_mt70 bucket.
    new_q3329 = (
        root / "seeds" / "q3329" / "p1000_mt70"
        / "n100_beta30" / "seed0001.json"
    )
    assert new_q3329.is_file()

    # Crosswalk CSV complete + well-formed.
    cw_path = tmp_path / "crosswalk.csv"
    assert cw_path.exists()
    with open(cw_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    for row in rows:
        assert row["old_path"]
        assert row["new_path"]
        assert len(row["sha256"]) == 64
        assert row["campaign"] in ("main", "q3329")
        # SHA-256 on disk matches the crosswalk record.
        with open(os.path.join(str(tmp_path), row["new_path"]), "rb") as f:
            on_disk = hashlib.sha256(f.read()).hexdigest()
        assert on_disk == row["sha256"]


def test_execute_is_idempotent(tmp_path):
    _, manifest_path = _make_tree_and_manifest(tmp_path)
    assert _run_migrate(tmp_path, manifest_path, ["--execute"]) == 0
    # Second --execute call must no-op without raising.
    assert _run_migrate(tmp_path, manifest_path, ["--execute"]) == 0


def test_execute_no_symlinks_flag_skips_symlink_creation(tmp_path):
    root, manifest_path = _make_tree_and_manifest(tmp_path)
    assert _run_migrate(
        tmp_path, manifest_path, ["--execute", "--no-symlinks"]
    ) == 0
    old_raw = root / "raw" / "n50_beta20_seed1.json"
    # No symlink left behind (file genuinely moved away).
    assert not old_raw.exists()


def test_execute_blocks_on_missing_source(tmp_path, capsys):
    root, manifest_path = _make_tree_and_manifest(tmp_path)
    # Delete a source AFTER the manifest has been built — simulates
    # "someone modified results/ between manifest build and migrate".
    os.unlink(str(root / "raw" / "n50_beta20_seed1.json"))
    rc = _run_migrate(tmp_path, manifest_path, ["--execute"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "BLOCKED" in err


def test_execute_refuses_to_run_without_manifest(tmp_path, capsys):
    argv = [
        "migrate",
        "--manifest", str(tmp_path / "nope.json"),
        "--execute",
    ]
    old_argv = sys.argv
    try:
        sys.argv = argv
        rc = mig.main()
    finally:
        sys.argv = old_argv
    assert rc == 2
    err = capsys.readouterr().err
    assert "manifest not found" in err


# ---------------- CLI smoke via subprocess --------------------------------


def test_cli_dry_run_subprocess(tmp_path):
    """Invoke the script via subprocess to catch import / argparse bugs."""
    root, manifest_path = _make_tree_and_manifest(tmp_path)
    script = os.path.join(ROOT, "scripts", "migrate_seeds_to_new_layout.py")
    proc = subprocess.run(
        [
            sys.executable, script,
            "--manifest", str(manifest_path),
            "--crosswalk-out", str(tmp_path / "crosswalk.csv"),
            "--dry-run",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DRY-RUN complete" in proc.stdout
    assert not os.path.exists(str(tmp_path / "crosswalk.csv"))
