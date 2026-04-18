#!/usr/bin/env python3
"""Build results/seed_manifest.json from the existing (pre-v1.3) seed
directory scatter under results/.

Walks every directory that is known to contain seed JSONs, parses each
file's (n, beta, seed, q, precision, max_tours) tuple, computes the
SHA-256, validates the schema (required keys present, advantage finite,
status == "completed"), and writes a single authoritative manifest.

Design reference: Research/backlog/2026-04-18_seed_consolidation.md,
section "Manifest". The manifest is the source of truth for the v1.3+
analysis loader. Seeds that fail verification are listed in the run
summary but NEVER land in the manifest — the "verify-gated append"
invariant.

Usage:
    python3 scripts/build_seed_manifest.py
    python3 scripts/build_seed_manifest.py --output /tmp/manifest.json
    python3 scripts/build_seed_manifest.py --results-root results/

Safe to re-run. The script does not move files, does not touch any
seed JSON, and overwrites only the output manifest path.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("build_seed_manifest")

SCHEMA_VERSION = 1

# Map `results/<dir>` → (campaign, dir-level tags).
# Campaign = intent of the run, not parameters. A q=97 seed produced
# by the cliff500 run belongs to campaign="cliff500", not "main".
CAMPAIGN_DIRS: dict[str, tuple[str, tuple[str, ...]]] = {
    "raw":                    ("main",              ()),
    "cloud":                  ("main",              ("cloud",)),
    "q3329":                  ("q3329",             ()),
    "q3329_n70_beta30":       ("q3329",             ("intermediate",)),
    "q3329_n80_beta30":       ("q3329",             ("intermediate",)),
    "q3329_n90_beta30":       ("q3329",             ("intermediate",)),
    "q3329_degenerate":       ("q3329",             ("degenerate",)),
    "cliff_500bit":           ("cliff500",          ()),
    "fplll543_sensitivity":   ("fplll_sensitivity", ("v5.4.3",)),
    "fplll544_sensitivity":   ("fplll_sensitivity", ("v5.4.4",)),
    "fplll54_sensitivity":    ("fplll_sensitivity", ("v5.4.5",)),
    "3x_tours":               ("tours3x",           ()),
    "3x_tours_extended":      ("tours3x",           ("extended",)),
    "convergence":            ("convergence",       ()),
    "convergence_test":       ("convergence",       ("test",)),
}

# Dirs explicitly excluded from the walk (not seed data).
EXCLUDED_DIRS = frozenset({"backups", "analysis", "paper_claims"})

# Structural keys every seed JSON must carry, regardless of campaign.
# status + advantage are checked per-campaign below because schema
# varies: convergence seeds have no `status` field, tours3x seeds
# have `advantage_3x` + `advantage_equal_tours` instead of `advantage`,
# and q3329 `_fat.json` companions carry only per-tour trajectory data.
REQUIRED_KEYS = ("n", "beta", "seed", "q")

# Filename parse — tolerates the patterns actually in use:
#   n100_beta30_seed1.json
#   n100_beta30_q97_seed1.json
#   n100_beta30_q3329_seed1.json
#   n100_beta30_q3329_seed100_fat.json
#   n60_beta30_3x_seed45.json
#   convergence_n140_beta30_seed10.json
FILENAME_RE = re.compile(
    r"^(?:convergence_)?"
    r"n(?P<n>\d+)_beta(?P<beta>\d+)"
    r"(?:_q(?P<q>\d+))?"
    r"(?:_(?P<variant>3x))?"
    r"_seed(?P<seed>\d+)"
    r"(?P<fat>_fat)?"
    r"\.json$"
)


def _sha256(path: str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _iso_utc_from_epoch(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _fplll_version_from_tags(tags: tuple[str, ...]) -> Optional[str]:
    for t in tags:
        if t.startswith("v5.4"):
            return t[1:]
    return None


def _parse_filename(fname: str) -> Optional[dict]:
    m = FILENAME_RE.match(fname)
    if not m:
        return None
    return {
        "n": int(m.group("n")),
        "beta": int(m.group("beta")),
        "q_from_filename": int(m.group("q")) if m.group("q") else None,
        "variant": m.group("variant"),
        "seed": int(m.group("seed")),
        "fat": m.group("fat") is not None,
    }


def _classify(
    path: str,
    campaign: str,
    dir_tags: tuple[str, ...],
    generated_utc: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Build one manifest entry for `path`, or return (None, reason).

    Returns:
        (entry, None) on success, (None, reason) on rejection.
    """
    fname = os.path.basename(path)
    parsed = _parse_filename(fname)
    if parsed is None:
        return None, f"filename does not match expected patterns: {fname}"

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, f"json decode error: {e}"
    except OSError as e:
        return None, f"open error: {e}"

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        return None, f"missing required keys: {missing}"

    is_fat = parsed["fat"]
    is_3x = parsed["variant"] == "3x"

    # status check: main sweep + q3329 lean + cliff500 + fplll_sensitivity
    # all carry it. convergence, tours3x, and fat companions do not.
    if not is_fat and not is_3x and campaign != "convergence":
        if data.get("status") != "completed":
            return None, f"status != 'completed' (got {data.get('status')!r})"

    # advantage-finite check: varies by campaign. Fat companions carry no
    # aggregate advantage (they are per-tour trajectories pointing at a
    # lean sibling), so we simply copy nothing over.
    advantage: Optional[float]
    if is_fat:
        advantage = None
    elif is_3x:
        adv_source = data.get("advantage_equal_tours")
        if not isinstance(adv_source, (int, float)) or not math.isfinite(adv_source):
            return None, (
                f"advantage_equal_tours not finite (got {adv_source!r})"
            )
        advantage = float(adv_source)
    else:
        adv_source = data.get("advantage")
        if not isinstance(adv_source, (int, float)) or not math.isfinite(adv_source):
            return None, f"advantage not finite (got {adv_source!r})"
        advantage = float(adv_source)

    n_file, n_parsed = data["n"], parsed["n"]
    beta_file, beta_parsed = data["beta"], parsed["beta"]
    seed_file, seed_parsed = data["seed"], parsed["seed"]
    if (n_file, beta_file, seed_file) != (n_parsed, beta_parsed, seed_parsed):
        return None, (
            f"filename/content mismatch: filename says "
            f"(n={n_parsed}, beta={beta_parsed}, seed={seed_parsed}) "
            f"but JSON says (n={n_file}, beta={beta_file}, seed={seed_file})"
        )

    if parsed["q_from_filename"] is not None:
        if data["q"] != parsed["q_from_filename"]:
            return None, (
                f"q mismatch: filename={parsed['q_from_filename']} "
                f"vs content={data['q']}"
            )

    tags = list(dir_tags)
    if parsed["fat"]:
        tags.append("fat")
    if parsed["variant"] == "3x":
        tags.append("3x")

    # Reassign by intent: a q != 97 seed living in results/raw/ or
    # results/cloud/ is a q3329-campaign seed that happened to flow
    # through the main-sweep runner (the 10 cloud-AWS q=3329 seeds
    # described in paper §8). Campaign = intent, not parameters.
    effective_campaign = campaign
    if campaign == "main" and data["q"] != 97:
        effective_campaign = "q3329"

    st = os.stat(path)
    # After the v1.3 physical migration, files live under
    # results/seeds/<campaign>/... with backwards-compat symlinks at
    # the old paths. Record the canonical (realpath) location in the
    # manifest so the manifest is an index over files, not symlinks;
    # the old-path symlinks are a transition aid, not the ground truth.
    real_path = os.path.realpath(path)
    canonical_path = os.path.relpath(real_path) if real_path else os.path.relpath(path)
    entry = {
        "campaign": effective_campaign,
        "path": canonical_path,
        "n": int(data["n"]),
        "beta": int(data["beta"]),
        "seed": int(data["seed"]),
        "q": int(data["q"]),
        "precision": data.get("precision"),
        "max_tours": data.get("max_tours"),
        "store_per_tour": data.get("store_per_tour"),
        "advantage": advantage,
        "sha256": _sha256(path),
        "size_bytes": st.st_size,
        "mtime_utc": _iso_utc_from_epoch(st.st_mtime),
        "tags": tags,
        "verified": True,
        "verified_at_utc": generated_utc,
        "verified_by": "build_seed_manifest.py",
    }
    if effective_campaign == "fplll_sensitivity":
        entry["fplll_version"] = _fplll_version_from_tags(dir_tags)
    return entry, None


def walk(results_root: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Scan results_root for seed JSONs. Returns (entries, rejects)."""
    generated_utc = dt.datetime.now(tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    entries: list[dict] = []
    rejects: list[tuple[str, str]] = []

    for dirname, (campaign, tags) in CAMPAIGN_DIRS.items():
        abs_dir = os.path.join(results_root, dirname)
        if not os.path.isdir(abs_dir):
            PIPELINE.info(
                "manifest dir_skipped",
                cat="manifest",
                directory=dirname,
                reason="missing",
            )
            continue

        for fname in sorted(os.listdir(abs_dir)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(abs_dir, fname)
            entry, reason = _classify(path, campaign, tags, generated_utc)
            if entry is None:
                rejects.append((path, reason))
                continue
            entries.append(entry)

    entries.sort(
        key=lambda e: (
            e["campaign"],
            e["q"],
            e["n"],
            e["beta"],
            e["seed"],
            tuple(e["tags"]),
        )
    )
    return entries, rejects


def summarise(entries: list[dict]) -> dict:
    per_campaign: dict[str, dict] = {}
    for e in entries:
        c = e["campaign"]
        bucket = per_campaign.setdefault(
            c, {"total_seeds": 0, "tags": set(), "q_values": set()}
        )
        bucket["total_seeds"] += 1
        for t in e["tags"]:
            bucket["tags"].add(t)
        bucket["q_values"].add(e["q"])
    for bucket in per_campaign.values():
        bucket["tags"] = sorted(bucket["tags"])
        bucket["q_values"] = sorted(bucket["q_values"])
    return per_campaign


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-root", default="results")
    ap.add_argument("--output", default=os.path.join("results", "seed_manifest.json"))
    ap.add_argument(
        "--emit-rejects-to",
        default=None,
        help="write rejected files + reasons to this path (optional; "
        "default: rejects printed to stderr only)",
    )
    args = ap.parse_args()

    PIPELINE.info(
        "manifest build start",
        cat="manifest",
        results_root=args.results_root,
        output=args.output,
    )
    t0 = time.time()

    entries, rejects = walk(args.results_root)
    per_campaign = summarise(entries)

    generated_utc = dt.datetime.now(tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": generated_utc,
        "results_root": os.path.relpath(args.results_root),
        "campaigns": per_campaign,
        "seeds": entries,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    tmp_path = args.output + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp_path, args.output)

    elapsed = time.time() - t0
    PIPELINE.info(
        "manifest build done",
        cat="manifest",
        output=args.output,
        seeds=len(entries),
        rejects=len(rejects),
        campaigns=len(per_campaign),
        elapsed_s=round(elapsed, 2),
    )

    print(f"Wrote {args.output}")
    print(f"  {len(entries)} seeds across {len(per_campaign)} campaigns "
          f"in {elapsed:.1f} s")
    for c in sorted(per_campaign):
        info = per_campaign[c]
        print(f"    {c:20s} {info['total_seeds']:5d}  "
              f"q={info['q_values']}  tags={info['tags']}")

    if rejects:
        print(f"  {len(rejects)} file(s) rejected:", file=sys.stderr)
        for path, reason in rejects[:20]:
            print(f"    {path}: {reason}", file=sys.stderr)
        if len(rejects) > 20:
            print(f"    ... and {len(rejects) - 20} more", file=sys.stderr)
        if args.emit_rejects_to:
            with open(args.emit_rejects_to, "w") as f:
                for path, reason in rejects:
                    f.write(f"{path}\t{reason}\n")
            print(f"  wrote reject log to {args.emit_rejects_to}",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
