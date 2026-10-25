"""Regression guard for the paper-2 claims ledger (deep-audit finding 6).

Locks in the reproducible-claim invariant: every RECOMPUTED and POINTER record
in results/paper_claims/paper2_claims.json must still match its paper value. A
future silent tex/figure/data drift on any of those turns into a red test (the
paper-2 analogue of the verify_reference.json guard).

DERIVED-UNRESOLVED records are documented discrepancies, not asserted true;
the test asserts only that their set hasn't grown. The four 2026-07-10 ones
(R², core-hours, one bootstrap CI, the RHF bound) resolved in 2026-10, and the
n=163 BKZ bound-vs-onset reading with the 40/100 at q=4049.
"""
from __future__ import annotations

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "results", "paper_claims", "paper2_claims.json")

# Paper claims that do not reproduce as read. Growth beyond this is a regression.
KNOWN_UNRESOLVED: set[str] = set()


def _ledger() -> dict:
    with open(LEDGER) as f:
        return json.load(f)


def test_ledger_present_and_shaped():
    d = _ledger()
    assert d["schema_version"] == 1
    assert d["records"], "ledger has no records"
    for r in d["records"]:
        for k in ("claim_id", "paper_value", "recomputed_value", "match",
                  "status", "source", "method", "tex_anchors", "tex_lines"):
            assert k in r, f"{r.get('claim_id')} missing {k}"
        assert r["tex_lines"], f"{r['claim_id']} points at no tex line"


def test_recomputed_and_pointer_all_match():
    d = _ledger()
    bad = [r["claim_id"] for r in d["records"]
           if r["status"] in ("RECOMPUTED", "POINTER") and not r["match"]]
    assert not bad, f"RECOMPUTED/POINTER claims stopped matching: {bad}"


def test_unresolved_set_has_not_grown():
    d = _ledger()
    unresolved = {r["claim_id"] for r in d["records"]
                  if r["status"] == "DERIVED-UNRESOLVED"}
    new = unresolved - KNOWN_UNRESOLVED
    assert not new, (
        f"NEW unresolved claims appeared (a paper number stopped reproducing): "
        f"{new}. Investigate before updating KNOWN_UNRESOLVED.")


def test_status_taxonomy_valid():
    d = _ledger()
    allowed = {"RECOMPUTED", "POINTER", "DERIVED", "DERIVED-UNRESOLVED"}
    for r in d["records"]:
        assert r["status"] in allowed, f"{r['claim_id']}: bad status {r['status']}"


def test_committed_ledger_matches_builder():
    """The committed ledger is what the builder emits from the current tex and
    seeds: a tex or seed edit without `make paper2-claims` turns this red."""
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from build_paper2_claims import build
    assert build() == _ledger(), "stale ledger: run `make paper2-claims`"
