"""INC-49 SHA gate: the Kahan-patched seeds are covered by a manifest.

The 12 n=127 Kahan-patched validation seeds (paper Appendix A) were tracked by
no manifest -- outside every SHA/orphan gate. results/patched_seed_manifest.json
(built by scripts/build_patched_manifest.py) now covers them. These tests are the
gate: every patched seed on disk must appear in the manifest with a matching
SHA-256, and the manifest must carry no ghost entries.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "results", "patched_seed_manifest.json")
TREE = os.path.join(REPO_ROOT, "results", "seeds", "ntru_patched")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1 << 16), b""):
            h.update(buf)
    return h.hexdigest()


def _manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _disk_seeds():
    return sorted(glob.glob(os.path.join(TREE, "q*", "p*_mt*",
                                         "n*_beta*", "seed*.json")))


def test_every_patched_seed_on_disk_is_in_manifest_with_matching_sha():
    by_path = {e["path"]: e for e in _manifest()["seeds"]}
    for path in _disk_seeds():
        rel = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        assert rel in by_path, f"patched seed not in manifest: {rel}"
        assert by_path[rel]["sha256"] == _sha256(path), f"SHA drift: {rel}"


def test_no_ghost_entries():
    on_disk = {os.path.relpath(p, REPO_ROOT).replace(os.sep, "/")
               for p in _disk_seeds()}
    for e in _manifest()["seeds"]:
        assert e["path"] in on_disk, f"ghost manifest entry: {e['path']}"


def test_manifest_is_separate_engine():
    m = _manifest()
    assert m["engine"] == "fplll-kahan"
    assert len(m["seeds"]) == len(_disk_seeds())
