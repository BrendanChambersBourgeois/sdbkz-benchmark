#!/usr/bin/env python3
"""Migrate seed JSONs from the pre-v1.3 scatter into the unified
results/seeds/<campaign>/... tree specified in
Research/backlog/2026-04-18_seed_consolidation.md §Proposed structure.

Reads results/seed_manifest.json as the source of truth for which
files exist and where they currently live. Computes the new path per
campaign per design spec. In --dry-run mode (default) prints the
planned actions; in --execute mode performs the physical moves,
writes the crosswalk CSV, and drops backwards-compat symlinks at
the old paths.

USAGE

    python3 scripts/migrate_seeds_to_new_layout.py
    python3 scripts/migrate_seeds_to_new_layout.py --execute
    python3 scripts/migrate_seeds_to_new_layout.py \\
        --manifest results/seed_manifest.json \\
        --crosswalk-out results/seed_path_crosswalk.csv \\
        --dry-run

SAFETY

The --execute path is idempotent and manifest-gated:

  - Refuses to run if --manifest is missing.
  - Refuses to run if ANY manifest entry's current `path` is absent
    on disk (stale manifest — rebuild before migrating).
  - Refuses to clobber a pre-existing file at the target new_path
    unless its SHA-256 matches the source (re-running on a partial
    migration is safe; overwriting a DIFFERENT file is not).
  - Backwards-compat symlinks at old paths preserve the paper
    hash_verification.txt receipts (Open Question 3, resolved
    2026-04-18: keep symlinks through v1.4, drop at v2 with the
    crosswalk as the permanent record).

The physical move is an in-place rename() where possible, falling
back to copy+verify+unlink across filesystem boundaries. Every move
is logged through pipeline.jsonl via scripts/log.py.

This script does not touch seed_manifest.json. Re-run
scripts/build_seed_manifest.py after --execute so the manifest's
`path` fields point at the new layout.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("migrate_seeds")

DEFAULT_MANIFEST = os.path.join("results", "seed_manifest.json")
DEFAULT_CROSSWALK = os.path.join("results", "seed_path_crosswalk.csv")
NEW_LAYOUT_ROOT = os.path.join("results", "seeds")


@dataclass(frozen=True)
class Move:
    old_path: str
    new_path: str
    sha256: str
    campaign: str
    n: int
    beta: int
    seed: int
    is_fat: bool
    size_bytes: int


def _sha256(path: str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _leaf_name(entry: dict, is_fat: bool) -> str:
    """File name at the leaf under the new layout.

    Strips the n/beta/q noise that lived in the old filenames — every
    leaf directory already pins (campaign, n, beta, q, precision,
    max_tours, fplll_version), so seedNNNN[_cloud][_fat].json is enough.

    The `_cloud` provenance suffix is necessary for the main campaign
    because the paper's §3.7 cross-environment verification produced
    two legitimate copies of every main-sweep seed — one from the
    local VM (results/raw/) and one from the AWS Batch worker
    (results/cloud/). Both are byte-distinct (different mtimes /
    key ordering / etc.) but equal on every scientific quantity. We
    keep both under the new layout to preserve every paper-cited file
    (CLAUDE.md: "Never delete experimental data").
    """
    seed = entry["seed"]
    tags = set(entry.get("tags", []))
    suffix = ""
    if entry["campaign"] == "main" and "cloud" in tags:
        suffix += "_cloud"
    if is_fat:
        suffix += "_fat"
    return f"seed{seed:04d}{suffix}.json"


def _fplll_version_slug(entry: dict) -> str:
    ver = entry.get("fplll_version")
    if ver is None:
        raise ValueError(
            f"fplll_sensitivity entry missing fplll_version: {entry!r}"
        )
    return "v" + ver.replace(".", "_")


def new_path_for(entry: dict) -> str:
    """Compute the target path under results/seeds/ for a manifest entry.

    Per design spec (Research/backlog/2026-04-18_seed_consolidation.md
    §Proposed structure). Raises ValueError on unknown campaign.
    """
    campaign = entry["campaign"]
    n = entry["n"]
    beta = entry["beta"]
    is_fat = "fat" in entry.get("tags", [])
    fname = _leaf_name(entry, is_fat)

    n_str = f"n{n:03d}"
    beta_str = f"beta{beta:02d}"
    n_beta = f"{n_str}_{beta_str}"

    if campaign == "main":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "main", "q97", n_beta)
    elif campaign == "q3329":
        precision = entry.get("precision") or 0
        max_tours = entry.get("max_tours") or 0
        bucket = f"p{int(precision)}_mt{int(max_tours)}"
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "q3329", bucket, n_beta)
    elif campaign == "cliff500":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "cliff500", "q97", n_beta)
    elif campaign == "fplll_sensitivity":
        ver_slug = _fplll_version_slug(entry)
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT, "fplll_sensitivity", ver_slug, "q97", n_beta
        )
    elif campaign == "tours3x":
        leaf_dir = os.path.join(NEW_LAYOUT_ROOT, "tours3x", "q97", n_beta)
    elif campaign == "convergence":
        max_tours = entry.get("max_tours") or 0
        leaf_dir = os.path.join(
            NEW_LAYOUT_ROOT,
            "convergence",
            "q97",
            f"{n_beta}_mt{int(max_tours)}",
        )
    else:
        raise ValueError(f"unknown campaign: {campaign!r}")

    return os.path.join(leaf_dir, fname)


def plan_moves(manifest: dict) -> list[Move]:
    """Build the Move plan from a loaded manifest dict."""
    moves: list[Move] = []
    for entry in manifest["seeds"]:
        is_fat = "fat" in entry.get("tags", [])
        moves.append(Move(
            old_path=entry["path"],
            new_path=new_path_for(entry),
            sha256=entry["sha256"],
            campaign=entry["campaign"],
            n=entry["n"],
            beta=entry["beta"],
            seed=entry["seed"],
            is_fat=is_fat,
            size_bytes=entry["size_bytes"],
        ))
    return moves


def preflight_checks(moves: list[Move]) -> list[str]:
    """Return a list of blocker messages. Empty list = safe to proceed."""
    problems: list[str] = []
    seen_new_paths: dict[str, Move] = {}

    for mv in moves:
        if not os.path.exists(mv.old_path):
            problems.append(f"missing source: {mv.old_path}")
            continue
        if mv.new_path in seen_new_paths:
            prev = seen_new_paths[mv.new_path]
            problems.append(
                f"new_path collision: {mv.new_path!r} "
                f"claimed by ({prev.campaign} n={prev.n} β={prev.beta} "
                f"seed={prev.seed} fat={prev.is_fat}) AND "
                f"({mv.campaign} n={mv.n} β={mv.beta} "
                f"seed={mv.seed} fat={mv.is_fat})"
            )
        seen_new_paths[mv.new_path] = mv

    return problems


def _move_file(mv: Move) -> None:
    """Physical move + SHA-256 re-verify. Raises on any integrity issue."""
    os.makedirs(os.path.dirname(mv.new_path), exist_ok=True)

    if os.path.exists(mv.new_path):
        existing_sha = _sha256(mv.new_path)
        if existing_sha != mv.sha256:
            raise RuntimeError(
                f"refusing to clobber {mv.new_path}: "
                f"existing SHA-256 {existing_sha[:12]}... "
                f"differs from expected {mv.sha256[:12]}..."
            )
        # Target already in place with matching content — idempotent path.
        # Unlink the source if it still exists and is not a symlink into
        # the new location (defensive; the two-path case should not happen
        # after the first successful migration).
        if os.path.exists(mv.old_path) and not os.path.islink(mv.old_path):
            os.unlink(mv.old_path)
        return

    try:
        os.rename(mv.old_path, mv.new_path)
    except OSError:
        shutil.copy2(mv.old_path, mv.new_path)
        post_sha = _sha256(mv.new_path)
        if post_sha != mv.sha256:
            os.unlink(mv.new_path)
            raise RuntimeError(
                f"SHA-256 drift during copy: {mv.old_path} → "
                f"{mv.new_path}: expected {mv.sha256[:12]}..., "
                f"got {post_sha[:12]}..."
            )
        os.unlink(mv.old_path)


def _symlink_old_to_new(mv: Move) -> None:
    """Create a relative symlink at old_path → new_path."""
    old_dir = os.path.dirname(mv.old_path) or "."
    rel_target = os.path.relpath(mv.new_path, start=old_dir)
    if os.path.islink(mv.old_path) or os.path.exists(mv.old_path):
        return  # idempotent
    os.symlink(rel_target, mv.old_path)


def _write_crosswalk(path: str, moves: list[Move]) -> None:
    """Write one-row-per-move CSV so paper SHA-256 receipts still resolve."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "old_path", "new_path", "sha256", "campaign",
            "n", "beta", "seed", "is_fat", "size_bytes",
        ])
        for mv in moves:
            w.writerow([
                mv.old_path, mv.new_path, mv.sha256, mv.campaign,
                mv.n, mv.beta, mv.seed, int(mv.is_fat), mv.size_bytes,
            ])


def scan_orphans(manifest: dict, results_root: str = "results") -> list[str]:
    """Return files under results/ that are not referenced by the manifest.

    Informational only — orphans do not block migration. Backup, logs,
    summaries, and hash_verification are intentionally excluded.
    """
    indexed = {
        os.path.normpath(entry["path"]) for entry in manifest["seeds"]
    }
    orphans: list[str] = []
    exclude_dirs = {"backups", "analysis"}
    for root, dirs, files in os.walk(results_root):
        # Prune excluded subtrees.
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            if not fname.endswith(".json"):
                continue
            path = os.path.normpath(os.path.join(root, fname))
            if path in indexed:
                continue
            if fname == "seed_manifest.json":
                continue
            if fname.startswith("summary"):
                continue
            orphans.append(path)
    return orphans


def summarise(moves: list[Move]) -> dict:
    per_campaign: dict[str, dict] = {}
    total_bytes = 0
    fat_count = 0
    for mv in moves:
        bucket = per_campaign.setdefault(
            mv.campaign, {"seeds": 0, "fat": 0, "bytes": 0}
        )
        bucket["seeds"] += 1
        if mv.is_fat:
            bucket["fat"] += 1
            fat_count += 1
        bucket["bytes"] += mv.size_bytes
        total_bytes += mv.size_bytes
    return {
        "total_moves": len(moves),
        "fat_moves": fat_count,
        "lean_moves": len(moves) - fat_count,
        "total_bytes": total_bytes,
        "per_campaign": per_campaign,
    }


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest", default=DEFAULT_MANIFEST,
        help=f"path to seed_manifest.json (default: {DEFAULT_MANIFEST})",
    )
    ap.add_argument(
        "--crosswalk-out", default=DEFAULT_CROSSWALK,
        help=f"crosswalk CSV path (default: {DEFAULT_CROSSWALK})",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", default=True,
        help="print actions only (default)",
    )
    mode.add_argument(
        "--execute", action="store_true",
        help="perform the physical move + symlinks + crosswalk write",
    )
    ap.add_argument(
        "--no-symlinks", action="store_true",
        help="skip creating backwards-compat symlinks at old paths "
        "(default: symlinks are written in --execute mode)",
    )
    args = ap.parse_args()

    if args.execute:
        args.dry_run = False
    mode_str = "execute" if args.execute else "dry-run"

    PIPELINE.info(
        "migrate start",
        cat="migrate",
        mode=mode_str,
        manifest=args.manifest,
        crosswalk_out=args.crosswalk_out,
    )
    t0 = time.time()

    if not os.path.exists(args.manifest):
        print(f"error: manifest not found at {args.manifest}", file=sys.stderr)
        print("run scripts/build_seed_manifest.py first.", file=sys.stderr)
        return 2

    with open(args.manifest) as f:
        manifest = json.load(f)

    moves = plan_moves(manifest)
    problems = preflight_checks(moves)

    if problems:
        print(f"BLOCKED: {len(problems)} preflight issue(s):", file=sys.stderr)
        for p in problems[:20]:
            print(f"  {p}", file=sys.stderr)
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more", file=sys.stderr)
        PIPELINE.error(
            "migrate blocked", cat="migrate", problems=len(problems),
        )
        return 3

    summary = summarise(moves)

    header = "PLAN" if args.dry_run else "EXECUTING"
    print(f"{header}: migrate {summary['total_moves']} seeds "
          f"({summary['lean_moves']} lean + {summary['fat_moves']} fat), "
          f"{_fmt_bytes(summary['total_bytes'])} total")
    print(f"  manifest: {args.manifest}")
    print(f"  crosswalk: {args.crosswalk_out}")
    print(f"  symlinks at old paths: "
          f"{'NO' if args.no_symlinks else 'yes'}")
    print()
    print("Per-campaign breakdown:")
    for campaign in sorted(summary["per_campaign"]):
        bucket = summary["per_campaign"][campaign]
        print(f"  {campaign:20s} {bucket['seeds']:5d} seeds "
              f"({bucket['fat']:4d} fat)  {_fmt_bytes(bucket['bytes'])}")
    print()

    if args.dry_run:
        preview_n = min(len(moves), 20)
        print(f"First {preview_n} planned moves:")
        for mv in moves[:preview_n]:
            fat_mark = "  [FAT]" if mv.is_fat else ""
            print(f"  {mv.old_path}")
            print(f"    → {mv.new_path}{fat_mark}")
        if len(moves) > preview_n:
            print(f"  ... and {len(moves) - preview_n} more moves")
        print()
        print("Orphan scan (files under results/ not in manifest):")
        orphans = scan_orphans(manifest)
        if not orphans:
            print("  (none)")
        else:
            print(f"  {len(orphans)} orphan file(s) — NOT blocking, "
                  f"informational only:")
            for p in orphans[:20]:
                print(f"    {p}")
            if len(orphans) > 20:
                print(f"    ... and {len(orphans) - 20} more")
        print()
        print(f"DRY-RUN complete in {time.time() - t0:.2f} s. "
              f"No filesystem changes made. Pass --execute to perform "
              f"the migration.")
        PIPELINE.info(
            "migrate dry_run done",
            cat="migrate",
            total_moves=summary["total_moves"],
            total_bytes=summary["total_bytes"],
            orphans=len(orphans),
            elapsed_s=round(time.time() - t0, 2),
        )
        return 0

    # ----- --execute path -----
    moved = 0
    symlinked = 0
    for mv in moves:
        _move_file(mv)
        moved += 1
        if not args.no_symlinks:
            _symlink_old_to_new(mv)
            symlinked += 1
        if moved % 500 == 0:
            PIPELINE.info(
                "migrate heartbeat",
                cat="migrate",
                moved=moved,
                total=summary["total_moves"],
            )

    _write_crosswalk(args.crosswalk_out, moves)

    elapsed = time.time() - t0
    print(f"Moved {moved} seeds, wrote {symlinked} symlinks, "
          f"crosswalk at {args.crosswalk_out} in {elapsed:.1f} s.")
    print("Next: python3 scripts/build_seed_manifest.py "
          "to refresh manifest paths.")
    PIPELINE.info(
        "migrate done",
        cat="migrate",
        moved=moved,
        symlinked=symlinked,
        crosswalk=args.crosswalk_out,
        elapsed_s=round(elapsed, 2),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
