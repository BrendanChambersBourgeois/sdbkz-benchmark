#!/usr/bin/env python3
"""Build the paper-2 claims ledger: results/paper_claims/paper2_claims.json.

Deep-audit finding 6 flagged that paper-2 (paper2/latex/sdbkz_paper2.tex) §6-§7
cite quantitative numbers with NO machine-written derivation record, unlike
paper-1 whose numbers each sit behind a committed JSON. This builder emits one
ledger record per flagged number, mirroring the build_verify_reference.py idiom
(deterministic emit -> regenerable, so an edited figure/tex number can be diffed
against a committed source of truth).

Each record: {claim_id, tex_lines, verbatim, paper_value, source, method,
recomputed_value, match, status, note}. status taxonomy:
  RECOMPUTED         rebuilt from committed seeds via extract_dsd_onset (byte-
                     identical to the figure/table path)
  POINTER            copied verbatim from a committed validation JSON/manifest,
                     with a fail-loud assert against the source field
  DERIVED            a new computation defined in the vendored modules
  DERIVED-UNRESOLVED the paper number did NOT reproduce; the recomputed value +
                     a note are recorded so the discrepancy is visible, NOT
                     papered over (route any tex fix via paper_findings.md)

The compute lives in scripts/_paper2_claims/ (vendored + tested by the
2026-07-10 fleet, importing extract_dsd_onset primitives). This script only
concatenates their build_records() and writes the ledger deterministically.

Read-only on results/seeds/ (safe to run alongside a live campaign); writes
exactly results/paper_claims/paper2_claims.json.
"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from _paper2_claims import (  # noqa: E402
    derived_numeric,
    pointer,
    r2_fit,
    recomputed,
)

try:
    from log import get_logger
    PIPELINE = get_logger("build_paper2_claims")
except Exception:  # pragma: no cover
    PIPELINE = None

OUT = os.path.join(BASE, "results", "paper_claims", "paper2_claims.json")
SCHEMA_VERSION = 1

_SLICES = (
    ("recomputed", recomputed),
    ("pointer", pointer),
    ("derived", derived_numeric),
    ("r2", r2_fit),
)


def build() -> dict:
    records: list[dict] = []
    for name, mod in _SLICES:
        recs = mod.build_records()
        for r in recs:
            r.setdefault("slice", name)
        records.extend(recs)
    records.sort(key=lambda r: r["claim_id"])

    n_match = sum(1 for r in records if r.get("match"))
    unresolved = [r["claim_id"] for r in records
                  if r.get("status") == "DERIVED-UNRESOLVED"]
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc_epoch": 0.0,   # deterministic emit (byte-stable reruns)
        "description": "Paper-2 §6-§7 claim -> source -> method -> verified-value "
                       "ledger (deep-audit finding 6). See scripts/build_paper2_claims.py.",
        "guard_invariant": True,      # poison guard changes 0 of these numbers
                                      # (finding 6: 0/188 sentinel seeds in the
                                      # scored cells; onsets use _cell_rate, a
                                      # path the guard does not touch)
        "n_records": len(records),
        "n_match": n_match,
        "by_status": by_status,
        "unresolved": sorted(unresolved),
        "records": records,
    }


def main(argv=None) -> int:
    manifest = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"paper2_claims: {manifest['n_records']} records, "
          f"{manifest['n_match']} match; by_status={manifest['by_status']}")
    if manifest["unresolved"]:
        print("  UNRESOLVED (paper number did not reproduce — see records + "
              "route tex fixes via paper_findings.md):")
        for cid in manifest["unresolved"]:
            print(f"    - {cid}")
    print(f"  wrote {os.path.relpath(OUT, BASE)}")
    if PIPELINE is not None:
        PIPELINE.info("paper2 claims built", cat="claims",
                      n_records=manifest["n_records"], n_match=manifest["n_match"],
                      unresolved=len(manifest["unresolved"]))
    # Exit 0 always: the ledger is a provenance RECORD, not a gate. The
    # reproducible-claim regression is enforced by tests/test_paper2_claims.py.
    return 0


if __name__ == "__main__":
    sys.exit(main())
