#!/usr/bin/env python3
"""Verify results/seed_manifest.json matches the on-disk seed tree.

Three invariants (design doc §Verify-gated append, "Manifest integrity"):

  (a) Orphan: a file exists under results/seeds/<campaign>/... (the
      v1.3 canonical tree) or at a pre-v1.3 path (non-symlink) but is
      not referenced by any manifest entry.

  (b) Ghost: a manifest entry's `path` field points at a file that is
      absent from disk.

  (c) Drift: the file at a manifest entry's `path` exists but its
      current SHA-256 differs from the record. Only checked under
      --sha-check (slow; recomputes 4387+ hashes).

Default run mode is FAST (file existence + orphan scan only). CI wires
this as a per-commit gate so drift-of-tree is caught within one push.
--sha-check is a slower local-or-nightly verification that the files
themselves have not been mutated.

Allowlist for orphan scan:
  - results/seed_manifest.json / results/seed_path_crosswalk.csv
  - results/*.json non-seed aggregates at the top level
  - results/paper_claims/ (paper-evidence summaries)
  - summary_*.json under any results/ subdir
  - results/3x_tours/n60_beta30_seed{1..10}.json (10 legacy pilot
    seeds with no `q` field — superseded by the 500-seed extended
    campaign; kept on disk per CLAUDE.md data-preservation rule)
  - symlinks at pre-v1.3 paths (transition aid through v1.4)

Exit codes:
  0  clean
  1  any orphan/ghost/drift violation
  2  manifest missing, parse error, or unreadable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("lint_seed_manifest")

DEFAULT_MANIFEST = os.path.join("results", "seed_manifest.json")
DEFAULT_RESULTS_ROOT = "results"
NEW_LAYOUT_DIRNAME = "seeds"

# Dir names at results/<name> that are *not* seed trees: skipped on
# the orphan walk entirely.
NON_SEED_DIRS = frozenset({
    "backups",            # rolling backup of sweep_seed_*.json files
    "analysis",           # analysis rollups only
    "paper_claims",       # curated paper-evidence JSONs
    "3x_tours_extended",  # summary-JSON scratch dir (3x runner)
    "validation",         # validation/ADR records, not seeds
})

# Seed trees under results/seeds/<campaign> that are DELIBERATELY not in
# the fplll seed_manifest: skipped on the orphan walk.
NON_MANIFEST_SEED_TREES = frozenset({
    # G6K engine seeds — byte-identity owned by the SEPARATE
    # results/g6k_seed_manifest.json (ADR-005; the two manifests must
    # never be merged).
    "ntru_g6k",
    # Patched-fplll (Kahan) validation campaign — its own tree by
    # design, never overwrites or joins the canonical seeds.
    "ntru_patched",
})

# Filenames we explicitly do not flag (informational only, known
# non-seeds that historically landed under results/ or in results/seeds/
# leaves).
ALLOWLIST_BASENAMES = frozenset({
    "seed_manifest.json",
    # G6K determinism manifest — a SEPARATE SHA set owned by
    # lint_g6k_manifest.py (ADR-005), intentionally not an fplll seed.
    "g6k_seed_manifest.json",
    # Patched-fplll (Kahan) validation manifest — its own SHA set, built
    # by build_patched_manifest.py and gated by test_patched_manifest.py;
    # mirrors the g6k split, not an fplll canonical seed.
    "patched_seed_manifest.json",
    "seed_path_crosswalk.csv",
    "summary.json",
    "summary_convergence.json",
    "summary_q3329.json",
    # Top-level analysis-rollup JSONs (written by analysis/ scripts).
    "runtime_table.json",
    "runtime_table.html",
    "q3329_degeneracy_check.json",
    "q3329_get_r_investigation.json",
    "dGSA_summary.json",
    "profile_decomposition.json",
    "convergence_headroom.json",
    "hash_verification.txt",
    "failed.json",
    # Preserved at v2.0.0 from the deleted `results/q3329_degenerate/`
    # legacy dir; documents the q=3329 degenerate-seed subset.
    "q3329_degenerate_README.md",
})

ALLOWLIST_PREFIXES = ("summary_",)  # summary_n50_beta30.json etc.

# 10 legacy 3x_tours pilot seeds (missing `q` field) preserved at
# `results/seeds/tours3x/pilot/` after the v2.0.0 symlink drop relocated
# them from the deleted `results/3x_tours/` back-compat tree. They are
# intentionally not in the manifest (the schema requires `q` and would
# reject these stubs) but stay on disk per the never-delete-experimental-
# data convention.
ALLOWLIST_LEGACY_PATHS: frozenset[str] = frozenset({
    os.path.join("results", "seeds", "tours3x", "pilot",
                 f"n60_beta30_seed{i}.json")
    for i in range(1, 11)
})


def _sha256(path: str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _is_allowlisted(path: str) -> bool:
    fname = os.path.basename(path)
    if fname in ALLOWLIST_BASENAMES:
        return True
    if any(fname.startswith(p) for p in ALLOWLIST_PREFIXES):
        return True
    if os.path.normpath(path) in ALLOWLIST_LEGACY_PATHS:
        return True
    return False


def collect_orphans(
    results_root: str,
    indexed: set[str],
) -> tuple[list[str], list[str]]:
    """Return (orphan_errors, orphan_informational). Orphans are files
    not in the manifest; informational orphans hit the allowlist.

    Comparison is done on paths relative to the parent of results_root
    (the repo root) so that the `indexed` set — which the manifest
    stores as `results/seeds/...` — matches walker output regardless of
    absolute working directory.
    """
    errors: list[str] = []
    informational: list[str] = []

    repo_root = os.path.dirname(os.path.abspath(results_root))

    for root, dirs, files in os.walk(results_root):
        rel_root = os.path.relpath(root, results_root)
        rel_parts = rel_root.split(os.sep) if rel_root != "." else []
        top = rel_parts[0] if rel_parts else ""
        if top in NON_SEED_DIRS:
            dirs[:] = []
            continue
        if (len(rel_parts) >= 2 and top == NEW_LAYOUT_DIRNAME
                and rel_parts[1] in NON_MANIFEST_SEED_TREES):
            dirs[:] = []
            continue
        for fname in files:
            if not fname.endswith(".json"):
                continue
            abs_path = os.path.normpath(os.path.join(root, fname))
            # Skip symlinks — the transitional back-compat symlinks at
            # pre-v1.3 paths are expected and do not count as orphans.
            if os.path.islink(abs_path):
                continue
            rel_path = os.path.normpath(os.path.relpath(abs_path, repo_root))
            if rel_path in indexed:
                continue
            if _is_allowlisted(rel_path):
                informational.append(rel_path)
                continue
            errors.append(rel_path)

    return errors, informational


def collect_ghosts_and_drift(
    manifest: dict,
    results_root: str,
    check_sha: bool,
) -> tuple[list[str], list[str]]:
    """Return (ghost_errors, drift_errors). drift_errors empty unless
    check_sha=True.
    """
    ghost: list[str] = []
    drift: list[str] = []
    root_abs = os.path.abspath(results_root)
    # Manifest paths are recorded relative to the repo root (e.g.
    # `results/seeds/...`). We want to resolve them against the
    # parent of results_root for absolute filesystem access.
    repo_root = os.path.dirname(root_abs) if root_abs.endswith("results") \
        else root_abs
    for entry in manifest["seeds"]:
        abs_path = os.path.join(repo_root, entry["path"])
        if not os.path.exists(abs_path):
            ghost.append(entry["path"])
            continue
        if check_sha:
            observed = _sha256(abs_path)
            expected = entry.get("sha256")
            if expected and observed != expected:
                drift.append(
                    f"{entry['path']}: expected sha256 "
                    f"{expected[:12]}..., got {observed[:12]}..."
                )
    return ghost, drift


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--results-root", default=DEFAULT_RESULTS_ROOT)
    ap.add_argument(
        "--sha-check", action="store_true",
        help="recompute SHA-256 of every manifest entry and compare "
        "against the recorded value. Measured ~0.3s on 4,432 entries "
        "(~300 MB) on NVMe; safe to enable in CI.",
    )
    ap.add_argument(
        "--quiet", action="store_true",
        help="print only the final summary line",
    )
    args = ap.parse_args()

    t0 = time.time()
    PIPELINE.info(
        "lint start",
        cat="audit",
        manifest=args.manifest,
        results_root=args.results_root,
        sha_check=args.sha_check,
    )

    if not os.path.exists(args.manifest):
        print(f"error: manifest not found at {args.manifest}",
              file=sys.stderr)
        print("run scripts/build_seed_manifest.py first.", file=sys.stderr)
        return 2

    try:
        with open(args.manifest) as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"error: manifest parse/read failed: {e}", file=sys.stderr)
        return 2

    indexed = set()
    for entry in manifest["seeds"]:
        indexed.add(os.path.normpath(entry["path"]))

    orphan_errors, orphan_info = collect_orphans(args.results_root, indexed)
    ghost_errors, drift_errors = collect_ghosts_and_drift(
        manifest, args.results_root, args.sha_check,
    )

    n_viol = len(orphan_errors) + len(ghost_errors) + len(drift_errors)

    if not args.quiet:
        if orphan_errors:
            print(f"ORPHAN: {len(orphan_errors)} file(s) on disk but "
                  f"not in manifest (fail):")
            for p in orphan_errors[:20]:
                print(f"  {p}")
            if len(orphan_errors) > 20:
                print(f"  ... and {len(orphan_errors) - 20} more")
        if ghost_errors:
            print(f"GHOST: {len(ghost_errors)} manifest entry(ies) with "
                  f"missing files (fail):")
            for p in ghost_errors[:20]:
                print(f"  {p}")
            if len(ghost_errors) > 20:
                print(f"  ... and {len(ghost_errors) - 20} more")
        if drift_errors:
            print(f"DRIFT: {len(drift_errors)} on-disk SHA-256 mismatch(es) "
                  f"vs manifest (fail):")
            for p in drift_errors[:20]:
                print(f"  {p}")
            if len(drift_errors) > 20:
                print(f"  ... and {len(drift_errors) - 20} more")
        if orphan_info:
            print(f"info: {len(orphan_info)} orphan file(s) on the "
                  f"allowlist (not flagged):")
            for p in orphan_info[:10]:
                print(f"  {p}")
            if len(orphan_info) > 10:
                print(f"  ... and {len(orphan_info) - 10} more")

    elapsed = time.time() - t0
    summary = (
        f"lint_seed_manifest: {len(manifest['seeds'])} entries checked; "
        f"{len(orphan_errors)} orphan, {len(ghost_errors)} ghost, "
        f"{len(drift_errors)} drift; "
        f"{len(orphan_info)} allowlisted non-seeds; "
        f"{elapsed:.1f} s"
        + (" (+sha)" if args.sha_check else "")
    )
    print(summary)
    PIPELINE.info(
        "lint done",
        cat="audit",
        orphan=len(orphan_errors),
        ghost=len(ghost_errors),
        drift=len(drift_errors),
        info=len(orphan_info),
        entries=len(manifest["seeds"]),
        elapsed_s=round(elapsed, 2),
    )

    return 1 if n_viol else 0


if __name__ == "__main__":
    sys.exit(main())
