"""SHA gate for the separate manifests built by scripts/build_patched_manifest.py.

patched_seed_manifest.json covers the Kahan-patched trees; side_seed_manifest.json
covers the auxiliary trees (reruns, probes, controls). Every seed on disk in a
set's trees must appear in its manifest with a matching SHA-256, and the
manifest must carry no ghost entries.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from build_patched_manifest import SETS  # noqa: E402


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1 << 16), b""):
            h.update(buf)
    return h.hexdigest()


def _manifest(name):
    with open(os.path.join(REPO_ROOT, SETS[name][0]), encoding="utf-8") as f:
        return json.load(f)


def _disk_seeds(name):
    return sorted(
        os.path.relpath(p, REPO_ROOT).replace(os.sep, "/")
        for tree in SETS[name][1]
        for p in glob.glob(os.path.join(REPO_ROOT, "results", "seeds", tree, "**",
                                        "seed*.json"), recursive=True))


@pytest.mark.parametrize("name", sorted(SETS))
def test_every_seed_on_disk_is_in_manifest_with_matching_sha(name):
    by_path = {e["path"]: e for e in _manifest(name)["seeds"]}
    for rel in _disk_seeds(name):
        assert rel in by_path, f"{name}: seed not in manifest: {rel}"
        assert by_path[rel]["sha256"] == _sha256(os.path.join(REPO_ROOT, rel)), \
            f"{name}: SHA drift: {rel}"


@pytest.mark.parametrize("name", sorted(SETS))
def test_no_ghost_entries(name):
    on_disk = set(_disk_seeds(name))
    for e in _manifest(name)["seeds"]:
        assert e["path"] in on_disk, f"{name}: ghost manifest entry: {e['path']}"


def test_patched_manifest_is_separate_engine():
    assert _manifest("patched")["engine"] == "fplll-kahan"
