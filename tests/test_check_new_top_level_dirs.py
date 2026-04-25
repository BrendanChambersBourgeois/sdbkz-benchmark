"""Tests for the INC-39 top-level directory guard.

Covers the pure logic of _top_level_violations against synthetic file
lists. The git-diff fallback path is exercised by the CI step itself
on every push and doesn't need a unit fixture.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_new_top_level_dirs import (  # noqa: E402
    ALLOWED_TOP_LEVEL,
    _top_level_violations,
)


def test_empty_input_returns_no_violations():
    assert _top_level_violations([]) == []


def test_top_level_files_are_skipped():
    # Files at the repo root (no `/` in path) introduce no new directory.
    paths = ["README.md", "pyproject.toml", "Dockerfile", ".gitignore"]
    assert _top_level_violations(paths) == []


def test_allowlisted_dirs_pass():
    paths = [
        "scripts/foo.py",
        "tests/test_bar.py",
        "analysis/plots/baz.py",
        "docs/adr.md",
        "results/seeds/main/q97/seed.json",
        ".github/workflows/x.yml",
        ".claude/agent.md",
    ]
    assert _top_level_violations(paths) == []


def test_unallowlisted_dir_is_flagged():
    paths = ["new_top_level/sub/file.txt"]
    violations = _top_level_violations(paths)
    assert violations == [("new_top_level", "new_top_level/sub/file.txt")]


def test_inc39_archives_dir_is_flagged():
    # The actual INC-39 regression: _archives/ in the public repo.
    paths = [
        "_archives/logs_legacy_2026-04-25.tar.gz",
        "_archives/CHECKSUMS.sha256",
    ]
    violations = _top_level_violations(paths)
    assert violations == [
        ("_archives", "_archives/logs_legacy_2026-04-25.tar.gz"),
    ]


def test_multiple_violations_sorted_and_deduped():
    paths = [
        "zfoo/x.txt",
        "abar/y.txt",
        "abar/z.txt",  # duplicate top-level — only first sample kept
        "scripts/ok.py",  # allowlisted, no violation
        "_archives/blob.bin",
    ]
    violations = _top_level_violations(paths)
    # Sorted by top-level dir name.
    assert [v[0] for v in violations] == ["_archives", "abar", "zfoo"]
    # First-seen sample preserved per directory.
    assert violations[1] == ("abar", "abar/y.txt")


def test_mixed_allowlisted_and_violating():
    paths = [
        "scripts/legit.py",
        "tests/legit_test.py",
        "shadow_dir/leak.txt",
    ]
    violations = _top_level_violations(paths)
    assert violations == [("shadow_dir", "shadow_dir/leak.txt")]


def test_allowlist_is_a_frozenset():
    # Guards against accidental mutation in fixture or helper code.
    assert isinstance(ALLOWED_TOP_LEVEL, frozenset)


def test_allowlist_contains_expected_baseline():
    # Sanity check: the categories the audit doc mentions.
    expected = {
        "scripts", "tests", "analysis", "docs", "examples",
        "paper", "patches", "results",
        ".github", ".claude",
        "logs", ".pytest_cache", ".ruff_cache",
    }
    missing = expected - ALLOWED_TOP_LEVEL
    assert not missing, f"allowlist missing {missing}"


@pytest.mark.parametrize("path", [
    "_archives/x.tar.gz",
    "_originals/snapshot.md",
    "tmp/foo.py",
    "scratch/draft.json",
])
def test_offline_naming_conventions_are_flagged(path):
    # Conventions that the project uses for offline / scratch /
    # backup-but-not-public directories must not slip into the public
    # repo. Each should be flagged.
    violations = _top_level_violations([path])
    assert len(violations) == 1
    top = path.split("/", 1)[0]
    assert violations[0] == (top, path)
