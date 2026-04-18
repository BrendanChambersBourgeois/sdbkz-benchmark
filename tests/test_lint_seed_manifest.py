"""Tests for scripts/lint_seed_manifest.py.

Covers all three violation classes (orphan / ghost / sha-drift), the
allowlist and symlink-skip paths, and the three exit codes
(0 clean, 1 violation, 2 manifest-missing/parse).
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import lint_seed_manifest as lint  # noqa: E402


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_seed_file(path: str, contents: dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(contents, f)
    with open(path, "rb") as f:
        return _sha256_bytes(f.read())


def _build_tree(tmp_path, *, with_orphan=False, with_ghost=False, with_drift=False,
                with_symlink=False):
    """Construct a small v1.3 layout under tmp_path with optional
    injected defects."""
    results = tmp_path / "results"
    seeds_main = results / "seeds" / "main" / "q97" / "n050_beta20"
    seed_path = seeds_main / "seed0001.json"
    sha = _write_seed_file(str(seed_path), {
        "n": 50, "beta": 20, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70,
        "status": "completed", "advantage": 0.1,
    })

    entries = [{
        "campaign": "main", "n": 50, "beta": 20, "seed": 1, "q": 97,
        "path": "results/seeds/main/q97/n050_beta20/seed0001.json",
        "sha256": sha, "size_bytes": 42,
        "mtime_utc": "2026-04-18T00:00:00Z",
        "tags": [], "verified": True,
        "verified_at_utc": "2026-04-18T00:00:00Z",
        "verified_by": "build_seed_manifest.py",
    }]

    if with_orphan:
        # A stray file under results/seeds/ not in manifest → error.
        orphan_path = seeds_main / "seed9999.json"
        _write_seed_file(str(orphan_path), {
            "n": 50, "beta": 20, "seed": 9999, "q": 97,
            "status": "completed", "advantage": 0.2,
        })

    if with_ghost:
        # A manifest entry whose file is not on disk → error.
        entries.append({
            "campaign": "main", "n": 50, "beta": 20, "seed": 2, "q": 97,
            "path": "results/seeds/main/q97/n050_beta20/seed0002.json",
            "sha256": "b" * 64, "size_bytes": 42,
            "mtime_utc": "2026-04-18T00:00:00Z",
            "tags": [], "verified": True,
            "verified_at_utc": "2026-04-18T00:00:00Z",
            "verified_by": "build_seed_manifest.py",
        })

    if with_drift:
        # Replace the file with different bytes without touching the
        # manifest; --sha-check should flag.
        with open(seed_path, "w") as f:
            json.dump({
                "n": 50, "beta": 20, "seed": 1, "q": 97,
                "status": "completed", "advantage": 0.9999,  # different
            }, f)

    if with_symlink:
        # Back-compat symlink at old path pointing at the v1.3 file.
        legacy_dir = results / "raw"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_link = legacy_dir / "n50_beta20_seed1.json"
        rel = os.path.relpath(str(seed_path), str(legacy_dir))
        os.symlink(rel, str(legacy_link))

    manifest = {
        "schema_version": 1,
        "generated_utc": "2026-04-18T00:00:00Z",
        "results_root": "results",
        "campaigns": {},
        "seeds": entries,
    }
    manifest_path = results / "seed_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    return manifest_path, results


def _run_lint(manifest_path, results_root, *, sha_check=False, cwd=None):
    argv = [
        sys.executable,
        os.path.join(ROOT, "scripts", "lint_seed_manifest.py"),
        "--manifest", str(manifest_path),
        "--results-root", str(results_root),
    ]
    if sha_check:
        argv.append("--sha-check")
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=30,
        cwd=str(cwd) if cwd else None,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_clean_tree_exits_zero(tmp_path):
    manifest_path, results = _build_tree(tmp_path)
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 0, (out, err)
    assert "0 orphan" in out
    assert "0 ghost" in out
    assert "0 drift" in out


def test_orphan_triggers_exit_one(tmp_path):
    manifest_path, results = _build_tree(tmp_path, with_orphan=True)
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 1, (out, err)
    assert "ORPHAN" in out
    assert "seed9999.json" in out


def test_ghost_triggers_exit_one(tmp_path):
    manifest_path, results = _build_tree(tmp_path, with_ghost=True)
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 1, (out, err)
    assert "GHOST" in out
    assert "seed0002.json" in out


def test_drift_triggers_exit_one_only_under_sha_check(tmp_path):
    manifest_path, results = _build_tree(tmp_path, with_drift=True)
    # Fast mode doesn't recompute SHAs → clean.
    rc, out, err = _run_lint(manifest_path, results, sha_check=False)
    assert rc == 0, (out, err)
    # --sha-check surfaces the mutation.
    rc, out, err = _run_lint(manifest_path, results, sha_check=True)
    assert rc == 1, (out, err)
    assert "DRIFT" in out


def test_manifest_missing_exits_two(tmp_path):
    rc, out, err = _run_lint(
        tmp_path / "does_not_exist.json", tmp_path / "results",
    )
    assert rc == 2, (out, err)
    assert "manifest not found" in err.lower()


def test_manifest_parse_error_exits_two(tmp_path):
    m = tmp_path / "broken.json"
    with open(m, "w") as f:
        f.write("this is not JSON {[")
    rc, out, err = _run_lint(m, tmp_path / "results")
    assert rc == 2, (out, err)
    assert "parse" in err.lower() or "read" in err.lower()


def test_symlink_at_legacy_path_not_reported_as_orphan(tmp_path):
    manifest_path, results = _build_tree(tmp_path, with_symlink=True)
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 0, (out, err)
    # Symlink at results/raw/n50_beta20_seed1.json must NOT be flagged.
    assert "raw/n50_beta20_seed1.json" not in out or "ORPHAN" not in out


def test_allowlist_includes_manifest_and_crosswalk(tmp_path):
    manifest_path, results = _build_tree(tmp_path)
    # Drop the crosswalk CSV next to the manifest; must not be flagged.
    with open(results / "seed_path_crosswalk.csv", "w") as f:
        f.write("old_path,new_path\n")
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 0, (out, err)
    assert "seed_path_crosswalk.csv" not in out or "ORPHAN" not in out


def test_summary_prefix_files_are_allowlisted(tmp_path):
    manifest_path, results = _build_tree(tmp_path)
    tours_dir = results / "3x_tours"
    tours_dir.mkdir()
    with open(tours_dir / "summary_n50_beta30.json", "w") as f:
        json.dump({"n": 50, "summary": True}, f)
    rc, out, err = _run_lint(manifest_path, results)
    assert rc == 0, (out, err)


def test_quiet_mode_only_prints_summary(tmp_path):
    manifest_path, results = _build_tree(tmp_path)
    argv = [
        sys.executable,
        os.path.join(ROOT, "scripts", "lint_seed_manifest.py"),
        "--manifest", str(manifest_path),
        "--results-root", str(results),
        "--quiet",
    ]
    proc = subprocess.run(argv, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "ORPHAN" not in proc.stdout
    assert "lint_seed_manifest:" in proc.stdout
