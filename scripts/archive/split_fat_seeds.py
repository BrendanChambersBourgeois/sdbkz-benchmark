"""Split a fat-schema seed JSON into a lean file and a companion _fat file.

Background: the main sweep scripts (sweep_parallel, sweep_cloud) produce
"lean" per-seed JSONs that only store the final/stagnation state for
Rankin profile, gs_lognorms, and RHF. The post-v1 `q3329_verify.run_single`
grew a `store_per_tour=True` option that additionally records every tour's
Rankin profile, gs_lognorms, and RHF for both BKZ and SD-BKZ variants.

Seeds produced with `store_per_tour=True` therefore have 7 extra top-level
keys that lean-schema readers will ignore. That's fine as long as the
published dataset stays conceptually uniform. To keep lean consumers happy
AND preserve the extra tour-level data without duplicating the lean
fields, this script splits every fat file into:

    n100_beta30_q3329_seed56.json       # LEAN  — identical to what the
                                        #   lean sweep would have produced
    n100_beta30_q3329_seed56_fat.json   # FAT   — ONLY the per-tour arrays
                                        #   plus a minimal identifier block,
                                        #   so analysis code can pair it
                                        #   back with its lean companion

Nothing is duplicated. Lean consumers see the normal dataset. Fat-aware
consumers can join on (n, beta, seed, q) to recover the extra tour data.

Usage:

    # Split a single file:
    python3 scripts/split_fat_seeds.py --input path/to/fat.json \\
        --lean-out-dir results/q3329 --fat-out-dir results/q3329

    # Split an entire directory:
    python3 scripts/split_fat_seeds.py --input-dir path/to/dylan/data \\
        --lean-out-dir results/q3329 --fat-out-dir results/q3329

    # Dry-run (print what would happen, write nothing):
    python3 scripts/split_fat_seeds.py --input-dir ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("split_fat_seeds")

# Keys present ONLY in fat-schema files. Everything else is lean.
#
# Note: `bkz_dln_per_tour` and `sdbkz_dln_per_tour` are NOT in this set
# because they have always been part of the lean schema — the baseline
# sweep scripts record the per-tour d(LN) trajectory even when
# store_per_tour=False. Only the Rankin profile, gs_lognorms, and RHF
# per-tour arrays are truly fat-only.
FAT_ONLY_KEYS = {
    "bkz_rankin_per_tour",
    "bkz_gs_lognorms_per_tour",
    "bkz_rhf_per_tour",
    "sdbkz_rankin_per_tour",
    "sdbkz_gs_lognorms_per_tour",
    "sdbkz_rhf_per_tour",
    "store_per_tour",
}

# Minimal identifier block copied into the fat companion file so it can
# be joined back to its lean partner without ambiguity.
IDENTIFIER_KEYS = ("n", "beta", "seed", "q")


def is_fat(data: dict) -> bool:
    """Return True if the result dict has any fat-only keys."""
    return bool(FAT_ONLY_KEYS.intersection(data.keys()))


def split(data: dict) -> tuple[dict, dict | None]:
    """Split a result dict into (lean_dict, fat_dict_or_None).

    If the input is already lean, returns (data, None). If fat, returns
    a lean copy (fat keys stripped) and a fat companion dict (fat keys
    only + identifier block).
    """
    if not is_fat(data):
        return data, None

    lean = {k: v for k, v in data.items() if k not in FAT_ONLY_KEYS}
    fat = {k: data[k] for k in IDENTIFIER_KEYS if k in data}
    for k in FAT_ONLY_KEYS:
        if k in data:
            fat[k] = data[k]
    return lean, fat


def fat_filename_for(lean_filename: str) -> str:
    """Return the fat companion filename for a given lean filename.

    Convention: insert `_fat` before the `.json` suffix.
    `n100_beta30_q3329_seed56.json` → `n100_beta30_q3329_seed56_fat.json`
    """
    stem, ext = os.path.splitext(lean_filename)
    if stem.endswith("_fat"):
        return lean_filename  # already fat — don't double-suffix
    return f"{stem}_fat{ext}"


def process_one(
    input_path: Path,
    lean_out_dir: Path,
    fat_out_dir: Path,
    dry_run: bool,
    overwrite: bool,
) -> str:
    """Split one file. Returns a status string for logging."""
    try:
        data = json.loads(input_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"SKIP (read error: {e})"

    lean, fat = split(data)

    lean_path = lean_out_dir / input_path.name
    if fat is not None:
        fat_path = fat_out_dir / fat_filename_for(input_path.name)
    else:
        fat_path = None

    if not overwrite and lean_path.exists():
        return f"SKIP (lean exists: {lean_path.name})"
    if fat_path is not None and not overwrite and fat_path.exists():
        return f"SKIP (fat exists: {fat_path.name})"

    if dry_run:
        if fat is None:
            return f"DRY-RUN lean-only → {lean_path.name}"
        return (
            f"DRY-RUN lean → {lean_path.name} "
            f"({len(lean)} keys), fat → {fat_path.name} "
            f"({len(fat)} keys)"
        )

    lean_out_dir.mkdir(parents=True, exist_ok=True)
    lean_path.write_text(json.dumps(lean, indent=2))
    if fat is not None:
        fat_out_dir.mkdir(parents=True, exist_ok=True)
        fat_path.write_text(json.dumps(fat, indent=2))
        return f"WROTE lean={lean_path.name}, fat={fat_path.name}"
    return f"WROTE lean={lean_path.name} (was already lean)"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="Single input JSON file")
    src.add_argument("--input-dir", type=Path, help="Directory containing JSON files to split")
    p.add_argument("--lean-out-dir", type=Path, required=True, help="Where to write lean files")
    p.add_argument("--fat-out-dir", type=Path, required=True, help="Where to write fat companion files")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing anything")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    p.add_argument("--pattern", default="*.json", help="Glob pattern for --input-dir (default: *.json)")
    args = p.parse_args(argv)

    if args.input:
        files = [args.input]
    else:
        if not args.input_dir.is_dir():
            print(f"error: not a directory: {args.input_dir}", file=sys.stderr)
            return 2
        files = sorted(args.input_dir.glob(args.pattern))
        # Skip any already-fat files that would be inputs
        files = [f for f in files if not f.stem.endswith("_fat")]

    if not files:
        print("no files to process", file=sys.stderr)
        PIPELINE.warning("split_fat_seeds no files to process",
                         cat="schema", input_dir=str(args.input_dir))
        return 1

    print(f"processing {len(files)} file(s)", file=sys.stderr)
    PIPELINE.info("split_fat_seeds start",
                  cat="schema",
                  file_count=len(files),
                  lean_out_dir=str(args.lean_out_dir),
                  fat_out_dir=str(args.fat_out_dir),
                  dry_run=args.dry_run)
    n_wrote = n_skip = n_dry = 0
    for f in files:
        status = process_one(f, args.lean_out_dir, args.fat_out_dir,
                             args.dry_run, args.overwrite)
        print(f"  {f.name}: {status}")
        if status.startswith("WROTE"):
            n_wrote += 1
        elif status.startswith("SKIP"):
            n_skip += 1
        elif status.startswith("DRY-RUN"):
            n_dry += 1

    print(
        f"\ntotal: {len(files)} files, "
        f"wrote {n_wrote}, skipped {n_skip}, dry-run {n_dry}",
        file=sys.stderr,
    )
    PIPELINE.info("split_fat_seeds complete",
                  cat="schema",
                  files=len(files), wrote=n_wrote, skipped=n_skip,
                  dry_run_count=n_dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
