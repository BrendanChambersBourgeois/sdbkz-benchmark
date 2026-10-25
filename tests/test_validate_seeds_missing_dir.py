"""A missing listed directory must fail --strict, not be skipped (cleanup plan C91)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate_seeds  # noqa: E402


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["validate_seeds.py", *argv])
    with pytest.raises(SystemExit) as e:
        validate_seeds.main()
    return e.value.code


def test_missing_dir_fails_strict(tmp_path, monkeypatch):
    assert _run(monkeypatch, "--strict", str(tmp_path / "no_such_tree")) == 1


def test_missing_dir_is_a_warning_without_strict(tmp_path, monkeypatch):
    assert _run(monkeypatch, str(tmp_path / "no_such_tree")) == 0
