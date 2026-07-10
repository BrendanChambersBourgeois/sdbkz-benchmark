"""Regression guard for the paper-2 claims ledger (deep-audit finding 6).

Locks in the reproducible-claim invariant: every RECOMPUTED and POINTER record
in results/paper_claims/paper2_claims.json must still match its paper value. A
future silent tex/figure/data drift on any of those turns into a red test (the
paper-2 analogue of the verify_reference.json guard).

DERIVED-UNRESOLVED records (the numbers that did NOT reproduce — R²=0.957,
core-hours, one bootstrap CI, the strict-max RHF bound) are deliberately NOT
asserted true: they are documented discrepancies awaiting a maintainer paper
pass, and the test asserts only that their COUNT hasn't grown (no new
regression sneaking in under that status).
"""
from __future__ import annotations

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "results", "paper_claims", "paper2_claims.json")

# The known-unresolved set as of 2026-07-10 (paper numbers that did not
# reproduce from committed data). Growth beyond this is a regression.
KNOWN_UNRESOLVED = {
    "per_position_slope_flatten_r2",   # R²=0.957 prose-only, best recipe 0.953
    "cost_core_hours",                 # tex ≈6,430; recomputed ~14,000
    "bootstrap_ci_n89_g6k_onset_gap",  # CI upper bound method-sensitive
    "rhf_fplll_le_2e-6_n101_113",      # strict max 1.76e-5 > 2e-6 (median holds)
}


def _ledger() -> dict:
    with open(LEDGER) as f:
        return json.load(f)


def test_ledger_present_and_shaped():
    d = _ledger()
    assert d["schema_version"] == 1
    assert d["records"], "ledger has no records"
    for r in d["records"]:
        for k in ("claim_id", "paper_value", "recomputed_value", "match",
                  "status", "source", "method"):
            assert k in r, f"{r.get('claim_id')} missing {k}"


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
