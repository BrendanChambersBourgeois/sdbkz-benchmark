"""Tests for scripts/_seed_io.py — the shared seed writer / resume guard.

The byte-identity test is the load-bearing one: every committed seed SHA-256
and results/seed_manifest.json depend on the exact serialisation, so a future
change to write_seed_atomic that alters a single byte must fail here rather
than silently invalidate the manifest.
"""

import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
from _seed_io import quarantine_corrupt, resume_skip_valid, write_seed_atomic  # noqa: E402

SEED = {
    "n": 100, "beta": 30, "seed": 1, "q": 97,
    "advantage": -1.3254321098765432,
    "status": "completed",
    "per_tour": [1.5, 2.25, 3.125],
    "nested": {"b": 1, "a": [None, True, False]},
    "unicode": "β δ ℓ",
}


def test_write_is_byte_identical_to_plain_json_dump(tmp_path):
    """write_seed_atomic must emit exactly json.dump(obj, fh, indent=2).

    This is what keeps every committed seed SHA-256 stable across the
    run_campaign / sweep_parallel / run_packed / run_3x_extended unification.
    """
    ref = tmp_path / "ref.json"
    with open(ref, "w") as fh:
        json.dump(SEED, fh, indent=2)
    out = tmp_path / "out.json"
    write_seed_atomic(str(out), SEED)
    assert out.read_bytes() == ref.read_bytes()


def test_write_creates_parents_and_leaves_no_tmp(tmp_path):
    out = tmp_path / "a" / "b" / "seed0001.json"
    write_seed_atomic(str(out), SEED)
    assert json.loads(out.read_text()) == SEED
    assert glob.glob(str(tmp_path / "**" / "*.tmp"), recursive=True) == []


def test_write_overwrites_atomically(tmp_path):
    out = tmp_path / "seed0001.json"
    write_seed_atomic(str(out), {"v": 1})
    write_seed_atomic(str(out), {"v": 2})
    assert json.loads(out.read_text()) == {"v": 2}
    assert glob.glob(str(tmp_path / "*.tmp")) == []


@pytest.mark.parametrize("body,expected", [
    (json.dumps(SEED, indent=2), True),
    (json.dumps(SEED, indent=2)[:120], False),   # power-cut truncation
    ("", False),                                  # zeroed by a crash
    ("\x00\x00\x00", False),                     # renamed-but-unflushed
])
def test_resume_skip_valid(tmp_path, body, expected):
    p = tmp_path / "seed0001.json"
    p.write_text(body)
    assert resume_skip_valid(str(p)) is expected


def test_resume_skip_valid_missing_file(tmp_path):
    assert resume_skip_valid(str(tmp_path / "nope.json")) is False


def test_quarantine_preserves_bytes_and_clears_the_json_glob(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text("{truncated")
    bad = quarantine_corrupt(str(p))
    assert not p.exists()                       # cell is pending again
    assert open(bad).read() == "{truncated"     # bytes preserved, never deleted
    assert glob.glob(str(tmp_path / "*.json")) == []


def test_quarantine_numbers_on_collision_and_never_overwrites(tmp_path):
    p = tmp_path / "seed0001.json"
    made = []
    for i in range(3):
        p.write_text(f"corrupt-{i}")
        made.append(quarantine_corrupt(str(p)))
    assert len(set(made)) == 3
    assert [open(b).read() for b in made] == ["corrupt-0", "corrupt-1", "corrupt-2"]


def test_committed_seeds_round_trip_byte_identical():
    """Every real seed the repo ships must survive load -> write_seed_atomic
    unchanged. Guards the manifest against a serialisation regression."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fixtures = sorted(glob.glob(os.path.join(
        repo, "tests", "fixtures", "synthetic_seeds", "*.json")))
    assert fixtures, "no seed fixtures found"
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for src in fixtures:
            with open(src) as fh:
                obj = json.load(fh)
            dst = os.path.join(td, os.path.basename(src))
            write_seed_atomic(dst, obj)
            with open(src, "rb") as a, open(dst, "rb") as b:
                assert a.read() == b.read(), f"serialisation drift on {src}"
