#!/usr/bin/env python3
"""Populate the seeds[] block of results/g6k_seed_manifest.json from the
on-disk G6K campaign tree (results/seeds/ntru_g6k/).

The g6k manifest is the SEPARATE SHA set for the G6K engine (ADR-005):
its hashes are not comparable to the fplll path's and the two manifests
must never be merged. Until 2026-06-11 the seeds[] list shipped empty
(Phase-1 scaffold), so no hash gate covered the 464 ntru_g6k campaign
seeds beyond the single verify_g6k.sh reference probe. This builder
closes that gap.

Behaviour:
  - Reads the existing manifest and preserves every top-level block
    (determinism_contract, build_pins, reference, note, ...) verbatim;
    ONLY seeds[] is rebuilt.
  - Walks results/seeds/ntru_g6k/ for seed*.json, parses the v1.3 path
    (q / precision / max_tours / n / beta / seed), computes SHA-256.
  - Every entry records threads=1 (the determinism contract;
    lint_g6k_manifest rejects anything else). The per-seed JSONs do not
    carry a threads field — single-threaded sieving is enforced at the
    backend (_engine_backends.py: SieverParams(threads=1)).
  - Verify-gated append (same invariant as build_seed_manifest):
    status != "completed" or non-finite advantage -> rejected, reported,
    never written.

Safe to re-run; rewrites only the manifest. Pair with
scripts/lint_g6k_manifest.py [--sha-check] to verify.

Usage:
    python3 scripts/build_g6k_manifest.py
    python3 scripts/build_g6k_manifest.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("build_g6k_manifest")

DEFAULT_MANIFEST = os.path.join("results", "g6k_seed_manifest.json")
G6K_TREE = os.path.join("results", "seeds", "ntru_g6k")

# results/seeds/ntru_g6k/q{q}/p{prec}_mt{mt}/n{n:03d}_beta{b:02d}/seed{s:04d}.json
_PATH_RE = re.compile(
    r"q(?P<q>\d+)/p(?P<prec>\d+)_mt(?P<mt>\d+)/"
    r"n(?P<n>\d+)_beta(?P<beta>\d+)/seed(?P<seed>\d+)\.json$"
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


def collect(repo_root: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Walk the g6k tree -> (entries, rejects). Verify-gated."""
    entries: list[dict] = []
    rejects: list[tuple[str, str]] = []
    pattern = os.path.join(repo_root, G6K_TREE, "q*", "p*_mt*",
                           "n*_beta*", "seed*.json")
    for path in sorted(glob.glob(pattern)):
        rel = os.path.relpath(path, repo_root)
        m = _PATH_RE.search(rel.replace(os.sep, "/"))
        if m is None:
            rejects.append((rel, "path does not match g6k v1.3 layout"))
            continue
        try:
            with open(path) as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            rejects.append((rel, f"unreadable: {type(exc).__name__}"))
            continue
        if doc.get("status") != "completed":
            rejects.append((rel, f"status={doc.get('status')!r}"))
            continue
        adv = doc.get("advantage")
        if not isinstance(adv, (int, float)) or not math.isfinite(adv):
            rejects.append((rel, f"non-finite advantage: {adv!r}"))
            continue
        entries.append({
            "path": rel.replace(os.sep, "/"),
            "campaign": "ntru_g6k",
            "engine": "g6k",
            "q": int(m.group("q")),
            "n": int(m.group("n")),
            "beta": int(m.group("beta")),
            "seed": int(m.group("seed")),
            "precision": int(m.group("prec")),
            "max_tours": int(m.group("mt")),
            "threads": 1,
            "sha256": _sha256(path),
        })
    entries.sort(key=lambda e: (e["q"], e["n"], e["beta"], e["seed"]))
    return entries, rejects


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written; touch nothing")
    args = ap.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, args.manifest) \
        if not os.path.isabs(args.manifest) else args.manifest

    PIPELINE.info("g6k manifest build start", cat="manifest",
                  manifest=args.manifest, dry_run=args.dry_run)
    t0 = time.time()

    with open(manifest_path) as f:
        manifest = json.load(f)

    entries, rejects = collect(repo_root)

    for rel, reason in rejects:
        print(f"REJECT: {rel}: {reason}", file=sys.stderr)

    if args.dry_run:
        print(f"DRY RUN: would write {len(entries)} seed entries "
              f"({len(rejects)} rejects); manifest untouched")
        return 0

    manifest["seeds"] = entries
    manifest["seeds_generated_utc"] = dt.datetime.now(tz=dt.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    tmp = manifest_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    os.replace(tmp, manifest_path)

    elapsed = time.time() - t0
    PIPELINE.info("g6k manifest build done", cat="manifest",
                  seeds=len(entries), rejects=len(rejects),
                  elapsed_s=round(elapsed, 2))
    print(f"Wrote {args.manifest}: {len(entries)} seed entries, "
          f"{len(rejects)} rejects, {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
