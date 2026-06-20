"""Guard against README seed-count drift.

The README leads with manifest-gated seed totals ("N fplll seeds + M G6K
seeds"). Those are hand-maintained while the data grows, so they drift -- a
blind review of this repo caught the README understating the fplll count by
~24% (8,741 vs the real 10,861) after paper-2 data landed. The project's whole
pitch is "trust my numbers", so a README wrong about its own headline counts is
a real defect.

This test ties the prose back to the machine truth: the comma-formatted length
of each manifest must literally appear in the README. If a campaign adds seeds
and the README is not updated, the new count is absent and this fails -- the
same drift-catching discipline the manifest lints already apply to the data,
now applied to the prose that describes it.
"""
from __future__ import annotations

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _manifest_len(name):
    with open(os.path.join(REPO_ROOT, "results", name), encoding="utf-8") as fh:
        return len(json.load(fh)["seeds"])


def _readme():
    with open(os.path.join(REPO_ROOT, "README.md"), encoding="utf-8") as fh:
        return fh.read()


def test_readme_fplll_count_matches_manifest():
    n = _manifest_len("seed_manifest.json")
    assert f"{n:,}" in _readme(), (
        f"README does not state the live fplll seed count {n:,} "
        f"(seed_manifest.json). Update the README headline/diagram counts."
    )


def test_readme_g6k_count_matches_manifest():
    n = _manifest_len("g6k_seed_manifest.json")
    assert f"{n:,}" in _readme(), (
        f"README does not state the live G6K seed count {n:,} "
        f"(g6k_seed_manifest.json). Update the README headline counts."
    )
