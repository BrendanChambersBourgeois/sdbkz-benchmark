"""Tests for the v2.0.0 symlink-drop path migration.

The migration deletes the back-compat symlink tree at
`results/{raw,cloud,q3329,cliff_500bit,fplll5*_sensitivity,3x_tours,
3x_tours_extended,convergence,convergence_test}` and promotes the
v1.3 `results/seeds/<campaign>/` tree as the sole canonical layout.

These tests guard against three regression classes:

  1. **Functional callsites** — any script that still calls
     `glob.glob` or `open` against the deleted directories breaks at
     runtime post-deletion. Static scan + integration smoke catch
     this before the destructive step lands.

  2. **Path-helper contracts** — `_seed_paths.seed_path_for` is the
     canonical surface every migrated caller routes through. Assert
     its output for each of the campaign+(n,β) tuples that the
     migration touched.

  3. **Examples bootstrap** — the three example scripts must still
     load_all_seeds + select the right seed against the manifest,
     because the README pipeline points new readers at them.

Synthetic-only — never reads `results/seeds/`. The examples test
uses subprocess against the live manifest because the examples are
__main__ entry points (would need to be importable to test inline,
and the README contract is that they're standalone scripts).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import _seed_paths  # noqa: E402

# ---------------------------------------------------------------------------
# Static scan — no script still references the deleted dirs as a glob target
# ---------------------------------------------------------------------------

# Legacy directories the v2.0.0 drop deletes. Any glob.glob / open
# against these post-rm will explode at runtime.
LEGACY_DIRS = (
    "results/raw",
    "results/cloud",
    "results/q3329",
    "results/q3329_n70_beta30",
    "results/q3329_n80_beta30",
    "results/q3329_n90_beta30",
    "results/q3329_degenerate",
    "results/cliff_500bit",
    "results/fplll543_sensitivity",
    "results/fplll544_sensitivity",
    "results/fplll54_sensitivity",
    "results/3x_tours",
    "results/3x_tours_extended",
    "results/convergence_test",
)

# Functional patterns that would reach the legacy dirs. Comments,
# docstrings, and print() strings are intentionally NOT caught — those
# are pure documentation and stay readable across the drop.
FUNCTIONAL_RE = re.compile(
    r'(?:glob\.glob|open|os\.path\.exists|os\.listdir|os\.scandir)'
    r'\([^)]*["\'](results/(?:raw|cloud|q3329|q3329_n\d+_beta\d+|'
    r'q3329_degenerate|cliff_500bit|fplll5\d*_sensitivity|3x_tours|'
    r'3x_tours_extended|convergence_test))'
)


def _all_py_files() -> list[Path]:
    out: list[Path] = []
    for sub in ("scripts", "analysis", "examples", "tests"):
        sub_path = REPO_ROOT / sub
        if sub_path.exists():
            out.extend(sub_path.rglob("*.py"))
    return out


def test_no_functional_legacy_dir_reads():
    offenders: list[tuple[str, int, str]] = []
    for path in _all_py_files():
        if path.name == "test_v2_path_migration.py":
            continue  # don't lint the lint
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), 1):
            m = FUNCTIONAL_RE.search(line)
            if m:
                offenders.append((str(path.relative_to(REPO_ROOT)),
                                  line_no, line.strip()))
    assert offenders == [], (
        "Functional reads against legacy directories that the v2.0.0 "
        "drop deletes — these will crash post-rm. Migrate to "
        "_seed_paths.seed_path_for or analysis._data.load_all_seeds:\n  "
        + "\n  ".join(f"{p}:{ln}: {src}" for p, ln, src in offenders)
    )


# ---------------------------------------------------------------------------
# Path-helper contract — seed_path_for produces expected canonical leaves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campaign,n,beta,seed,kwargs,expected", [
    ("main", 100, 30, 1, {},
     "results/seeds/main/q97/n100_beta30/seed0001.json"),
    ("main", 110, 40, 1, {"cloud": True},
     "results/seeds/main/q97/n110_beta40/seed0001_cloud.json"),
    ("q3329", 90, 30, 1,
     {"q": 3329, "precision": 1000, "max_tours": 70},
     "results/seeds/q3329/p1000_mt70/n090_beta30/seed0001.json"),
    ("cliff500", 130, 40, 1, {},
     "results/seeds/cliff500/q97/n130_beta40/seed0001.json"),
])
def test_seed_path_for_matches_expected(campaign, n, beta, seed, kwargs, expected):
    assert _seed_paths.seed_path_for(
        campaign, n, beta, seed, **kwargs,
    ) == expected


# ---------------------------------------------------------------------------
# Module-level constants — q3329_verify SUMMARY_DIR must stay under the
# canonical campaign tree post-v2.0.0 (the legacy results/q3329/ root is
# deleted). Since c778c88a the tree is keyed by TAG (--seed-tag), so the
# q3329_kahan / q3329_control arms write under their own roots; the
# default must remain "q3329". The constant runs at import + does mkdir,
# so we can't import it under pytest without consuming sys.argv; a
# static-scan match on the literals is the cheapest gate against
# regressions.
# ---------------------------------------------------------------------------

def test_q3329_verify_summary_dir_under_canonical_tree():
    src = (REPO_ROOT / "scripts" / "q3329_verify.py").read_text()
    pattern = re.compile(
        r'SUMMARY_DIR\s*=\s*os\.path\.join\(\s*BASE\s*,\s*'
        r'"results"\s*,\s*"seeds"\s*,\s*TAG\s*,\s*"summary"\s*\)'
    )
    assert pattern.search(src), (
        "q3329_verify.SUMMARY_DIR must point at "
        "results/seeds/<TAG>/summary/ (the v1.3 canonical tree keyed by "
        "--seed-tag). The legacy results/q3329/ root was deleted at "
        "v2.0.0; any other target will crash at first summary write."
    )
    default = re.compile(
        r'add_argument\(\s*"--seed-tag"[^)]*?default\s*=\s*"q3329"',
        re.DOTALL,
    )
    assert default.search(src), (
        "q3329_verify --seed-tag default must stay \"q3329\" so the "
        "canonical run still lands under results/seeds/q3329/."
    )


# ---------------------------------------------------------------------------
# Examples integration smoke — live manifest, --campaign flag honoured
# ---------------------------------------------------------------------------

def _has_manifest() -> bool:
    return (REPO_ROOT / "results" / "seed_manifest.json").exists()


@pytest.mark.skipif(not _has_manifest(),
                    reason="live manifest not present in this checkout")
def test_example_01_inspect_one_seed_runs():
    result = subprocess.run(
        [sys.executable, "examples/01_inspect_one_seed.py",
         "--n", "50", "--beta", "20", "--seed", "1"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "n=50" in out
    assert "advantage" in out.lower()
    assert "Source: results/seed_manifest.json" in out


@pytest.mark.skipif(not _has_manifest(),
                    reason="live manifest not present in this checkout")
def test_example_02_compare_two_groups_runs():
    result = subprocess.run(
        [sys.executable, "examples/02_compare_two_groups.py",
         "--group1", "100", "30", "--group2", "150", "30"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "Cohen's d" in result.stdout
    assert "Δ mean" in result.stdout


@pytest.mark.skipif(not _has_manifest(),
                    reason="live manifest not present in this checkout")
def test_example_03_plot_basis_profile_runs(tmp_path):
    # Routes the PNG write to tmp_path so the test works under a
    # read-only repo mount (CI mounts ${workspace}:/repo:ro for the
    # smoke step; the default `examples/output/` target inherits
    # that read-only-ness and the matplotlib savefig errnos 30).
    result = subprocess.run(
        [sys.executable, "examples/03_plot_basis_profile.py",
         "--n", "50", "--beta", "20", "--seed", "1",
         "--output-dir", str(tmp_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "Saved:" in result.stdout
    # PNG actually landed in tmp_path, not the read-only default.
    assert (tmp_path / "profile_n50_beta20_seed1.png").exists()
