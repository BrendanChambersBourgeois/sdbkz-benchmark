#!/usr/bin/env python3
"""Build results/patched_seed_manifest.json — the SHA set for the Kahan-patched
fplll engine (results/seeds/ntru_patched/).

The patched seeds are produced by the Kahan-compensated GSO build
(Dockerfile.fplll_patched, paper Appendix A): their squared-form arithmetic
differs from stock fplll, so their byte hashes are NOT comparable to the main
fplll manifest and must live in a separate set -- the same reasoning that keeps
g6k separate (ADR-005). Until now these 12 n=127 validation seeds were tracked
by NO manifest (INC-49); this closes the gap with the same SHA-256 + verify-gate
discipline as build_g6k_manifest.

Behaviour mirrors build_g6k_manifest:
  - Walks results/seeds/ntru_patched/ for seed*.json, parses the v1.3 path,
    computes SHA-256; verify-gated (status=="completed" + finite advantage).
  - Creates the manifest scaffold on first run; preserves top-level blocks on
    re-run, rebuilding only seeds[].
  - Deterministic timestamp (SOURCE_DATE_EPOCH or epoch 0) so re-runs are
    byte-stable -- no wall-clock churn (INC-48).

Usage:
    python3 scripts/build_patched_manifest.py
    python3 scripts/build_patched_manifest.py --dry-run
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

PIPELINE = get_logger("build_patched_manifest")

DEFAULT_MANIFEST = os.path.join("results", "patched_seed_manifest.json")
PATCHED_TREE = os.path.join("results", "seeds", "ntru_patched")
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"

_PATH_RE = re.compile(
    r"q(?P<q>\d+)/p(?P<prec>\d+)_mt(?P<mt>\d+)/"
    r"n(?P<n>\d+)_beta(?P<beta>\d+)/seed(?P<seed>\d+)\.json$"
)

_SCAFFOLD = {
    "manifest_version": 1,
    "engine": "fplll-kahan",
    "note": ("Kahan-compensated fplll GSO build (Dockerfile.fplll_patched, "
             "paper Appendix A). Separate SHA set: these hashes are NOT "
             "comparable to the stock-fplll seed_manifest (ADR-005 reasoning)."),
    "reference": ("paper Appendix A re-validation of the fplll GSO fix on the "
                  "n=127 NTRU off-grid family."),
    "seeds": [],
}


def _det_utc() -> str:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    return dt.datetime.fromtimestamp(epoch, tz=dt.UTC).strftime(_UTC_FMT)


def _sha256(path: str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def collect(repo_root: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Walk the patched tree -> (entries, rejects). Verify-gated."""
    entries: list[dict] = []
    rejects: list[tuple[str, str]] = []
    pattern = os.path.join(repo_root, PATCHED_TREE, "q*", "p*_mt*",
                           "n*_beta*", "seed*.json")
    for path in sorted(glob.glob(pattern)):
        rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
        m = _PATH_RE.search(rel)
        if m is None:
            rejects.append((rel, "path does not match v1.3 layout"))
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
            "path": rel,
            "campaign": "ntru_patched",
            "engine": "fplll-kahan",
            "q": int(m.group("q")),
            "n": int(m.group("n")),
            "beta": int(m.group("beta")),
            "seed": int(m.group("seed")),
            "precision": int(m.group("prec")),
            "max_tours": int(m.group("mt")),
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
    manifest_path = args.manifest if os.path.isabs(args.manifest) \
        else os.path.join(repo_root, args.manifest)

    PIPELINE.info("patched manifest build start", cat="manifest",
                  manifest=args.manifest, dry_run=args.dry_run)
    t0 = time.time()

    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = dict(_SCAFFOLD)

    entries, rejects = collect(repo_root)
    for rel, reason in rejects:
        print(f"REJECT: {rel}: {reason}", file=sys.stderr)

    if args.dry_run:
        print(f"DRY RUN: would write {len(entries)} seed entries "
              f"({len(rejects)} rejects); manifest untouched")
        return 0

    manifest["seeds"] = entries
    manifest["seeds_generated_utc"] = _det_utc()

    tmp = manifest_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, manifest_path)

    elapsed = time.time() - t0
    PIPELINE.info("patched manifest build done", cat="manifest",
                  seeds=len(entries), rejects=len(rejects),
                  elapsed_s=round(elapsed, 2))
    print(f"Wrote {args.manifest}: {len(entries)} seed entries, "
          f"{len(rejects)} rejects, {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
