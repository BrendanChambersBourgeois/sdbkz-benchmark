"""Guard for the paper-1 claims ledger: tex numbers, anchors and seeds agree."""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "results", "paper_claims", "paper1_claims.json")
sys.path.insert(0, os.path.join(REPO, "scripts"))


def _ledger() -> dict:
    with open(LEDGER) as f:
        return json.load(f)


def test_every_claim_matches_and_points_at_tex():
    d = _ledger()
    assert d["records"], "ledger has no records"
    assert not [r["claim_id"] for r in d["records"] if not r["match"]]
    assert not [r["claim_id"] for r in d["records"] if not r["tex_lines"]]


def test_committed_ledger_matches_builder():
    """A tex or seed edit without `make paper1-claims` turns this red."""
    from build_paper1_claims import build
    assert json.loads(json.dumps(build())) == _ledger(), \
        "stale ledger: run `make paper1-claims`"


def test_rounding_rule():
    from build_paper1_claims import _matches
    assert _matches(1.1634, 1.163, 3)
    assert not _matches(1.1636, 1.163, 3)
    assert not _matches([0.1], [0.1, 0.2], 1)
