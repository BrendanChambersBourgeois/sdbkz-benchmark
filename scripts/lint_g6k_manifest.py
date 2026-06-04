#!/usr/bin/env python3
"""Verify results/g6k_seed_manifest.json — the SEPARATE g6k SHA set.

Mirror of lint_seed_manifest.py, three invariants tuned to the g6k
determinism contract (ADR-005):

  (1) Contract: the manifest's determinism_contract.threads is 1, the
      reference is threads=1, and EVERY seed entry is threads=1. A
      threads>1 record is rejected outright — the multi-threaded G6K
      sieve is nondeterministic (Phase 0 verdict), so any MT hash in
      this file would be a silently-poisoned reference.

  (2) Ghost: a seed entry's `path` points at a file absent from disk.
      (Phase 1 ships zero seeds — seeds[] is empty — so this is vacuous
      until Phase 4 populates it.)

  (3) Separation + drift:
        (3a) Disjointness — no `path` and no `sha256` in this manifest
             also appears in results/seed_manifest.json. The g6k and
             fplll manifests describe different engines whose hashes are
             not comparable and must NEVER be merged. A shared path or
             SHA means the two trees have bled into each other.
        (3b) Drift — under --sha-check, a present seed file's on-disk
             SHA-256 differs from its recorded value.

The PENDING-FIRST-BUILD reference sentinel is reported as informational
(the scaffold has not captured its canonical hash yet). Pass --require-ref
to turn a still-PENDING reference into a hard failure — CI flips that on
once the first canonical build has filled the reference.

Exit codes:
  0  clean
  1  any contract / ghost / separation / drift violation
  2  manifest missing, parse error, or unreadable
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("lint_g6k_manifest")

DEFAULT_MANIFEST = os.path.join("results", "g6k_seed_manifest.json")
FPLLL_MANIFEST = os.path.join("results", "seed_manifest.json")
PENDING_SENTINEL = "PENDING-FIRST-BUILD"


def _sha256(path: str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def check_contract(manifest: dict) -> list[str]:
    """Invariant (1): threads==1 everywhere."""
    errors: list[str] = []
    contract = manifest.get("determinism_contract", {})
    if contract.get("threads") != 1:
        errors.append(
            f"determinism_contract.threads = {contract.get('threads')!r} "
            f"(must be 1)"
        )
    ref = manifest.get("reference", {})
    if ref.get("threads") != 1:
        errors.append(f"reference.threads = {ref.get('threads')!r} (must be 1)")
    for i, entry in enumerate(manifest.get("seeds", [])):
        if entry.get("threads") != 1:
            errors.append(
                f"seeds[{i}] ({entry.get('path', '?')}): threads = "
                f"{entry.get('threads')!r} (must be 1) — MT sieve is "
                f"nondeterministic, reject"
            )
    return errors


def check_ghosts_and_drift(
    manifest: dict, repo_root: str, check_sha: bool
) -> tuple[list[str], list[str]]:
    """Invariant (2) ghost + (3b) drift over seed entries."""
    ghost: list[str] = []
    drift: list[str] = []
    for entry in manifest.get("seeds", []):
        path = entry.get("path")
        if not path:
            ghost.append("<entry with no path field>")
            continue
        abs_path = os.path.join(repo_root, path)
        if not os.path.exists(abs_path):
            ghost.append(path)
            continue
        if check_sha:
            observed = _sha256(abs_path)
            expected = entry.get("sha256") or entry.get("basis_sha256")
            if expected and observed != expected:
                drift.append(
                    f"{path}: expected {expected[:12]}…, got {observed[:12]}…"
                )
    return ghost, drift


def check_separation(manifest: dict, fplll_manifest_path: str) -> list[str]:
    """Invariant (3a): g6k and fplll manifests share no path or sha."""
    errors: list[str] = []
    if not os.path.exists(fplll_manifest_path):
        return errors  # nothing to collide with
    try:
        with open(fplll_manifest_path) as f:
            fplll = json.load(f)
    except (json.JSONDecodeError, OSError):
        return errors  # the fplll lint owns that manifest's validity

    fplll_paths = set()
    fplll_shas = set()
    for entry in fplll.get("seeds", []):
        if entry.get("path"):
            fplll_paths.add(os.path.normpath(entry["path"]))
        if entry.get("sha256"):
            fplll_shas.add(entry["sha256"])

    for entry in manifest.get("seeds", []):
        p = entry.get("path")
        if p and os.path.normpath(p) in fplll_paths:
            errors.append(f"path collides with fplll manifest: {p}")
        s = entry.get("sha256") or entry.get("basis_sha256")
        if s and s in fplll_shas:
            errors.append(f"sha256 collides with fplll manifest: {s[:12]}…")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--fplll-manifest", default=FPLLL_MANIFEST)
    ap.add_argument("--sha-check", action="store_true",
                    help="recompute on-disk SHA of each seed entry (invariant 3b)")
    ap.add_argument("--require-ref", action="store_true",
                    help="fail if the reference SHA is still the "
                         f"{PENDING_SENTINEL} sentinel (CI flips this on "
                         "after the first canonical build)")
    args = ap.parse_args()

    t0 = time.time()
    PIPELINE.info("lint start", cat="audit", manifest=args.manifest,
                  sha_check=args.sha_check, require_ref=args.require_ref)

    if not os.path.exists(args.manifest):
        print(f"error: manifest not found at {args.manifest}", file=sys.stderr)
        print("create results/g6k_seed_manifest.json first.", file=sys.stderr)
        return 2
    try:
        with open(args.manifest) as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"error: manifest parse/read failed: {e}", file=sys.stderr)
        return 2

    repo_root = os.path.dirname(os.path.abspath(args.manifest))
    repo_root = os.path.dirname(repo_root)  # results/ -> repo root

    contract_err = check_contract(manifest)
    ghost_err, drift_err = check_ghosts_and_drift(
        manifest, repo_root, args.sha_check)
    sep_err = check_separation(manifest, args.fplll_manifest)

    # Reference-pending state.
    ref = manifest.get("reference", {})
    pending = (ref.get("basis_sha256") == PENDING_SENTINEL
               or ref.get("rprof_sha256") == PENDING_SENTINEL)
    ref_err: list[str] = []
    if pending and args.require_ref:
        ref_err.append(
            f"reference SHA still {PENDING_SENTINEL} (run the first "
            "canonical Dockerfile.g6k build to capture it)")

    for label, errs in (("CONTRACT", contract_err), ("GHOST", ghost_err),
                        ("SEPARATION", sep_err), ("DRIFT", drift_err),
                        ("REFERENCE", ref_err)):
        if errs:
            print(f"{label}: {len(errs)} violation(s):")
            for e in errs:
                print(f"  {e}")
    if pending and not args.require_ref:
        print(f"info: reference SHA is {PENDING_SENTINEL} (scaffold state; "
              "not yet captured)")

    n_viol = sum(len(e) for e in
                 (contract_err, ghost_err, sep_err, drift_err, ref_err))
    n_seeds = len(manifest.get("seeds", []))
    summary = (
        f"lint_g6k_manifest: {n_seeds} seed entr(ies); "
        f"{len(contract_err)} contract, {len(ghost_err)} ghost, "
        f"{len(sep_err)} separation, {len(drift_err)} drift, "
        f"{len(ref_err)} reference; {time.time() - t0:.2f}s"
        + (" (+sha)" if args.sha_check else "")
    )
    print(summary)
    PIPELINE.info("lint done", cat="audit", contract=len(contract_err),
                  ghost=len(ghost_err), separation=len(sep_err),
                  drift=len(drift_err), reference=len(ref_err),
                  seeds=n_seeds, pending=pending)
    return 1 if n_viol else 0


if __name__ == "__main__":
    sys.exit(main())
