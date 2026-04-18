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


# ---------------------------------------------------------------------------
# v1.3 layout parser
# ---------------------------------------------------------------------------
# Leaf-filename pattern under results/seeds/<campaign>/...:
#   seed{NNNN}[_cloud][_fat].json
_V13_LEAF_RE = re.compile(
    r"^seed(?P<seed>\d+)(?P<cloud>_cloud)?(?P<fat>_fat)?\.json$"
)
# Parent-dir pattern: n{NNN}_beta{BB} or (convergence) n{NNN}_beta{BB}_mt{MT}
_V13_NBETA_RE = re.compile(
    r"^n(?P<n>\d+)_beta(?P<beta>\d+)(?:_mt(?P<mt>\d+))?$"
)


def _parse_v13_path(
    rel_path: str,
) -> Optional[dict]:
    """Parse a path under results/seeds/ into (campaign, n, β, seed, ...).

    Returns None when the path shape does not match any known v1.3 layout.
    Matches the emit logic in scripts/_seed_paths.py — any drift there
    must be mirrored here or the walker will miss new entries.
    """
    parts = rel_path.split(os.sep)
    # Expected: ["results", "seeds", "<campaign>", ..., "n{n}_beta{b}[_mt]", "seed{s}.json"]
    if len(parts) < 5 or parts[0] != "results" or parts[1] != "seeds":
        return None
    campaign = parts[2]
    leaf = parts[-1]
    m_leaf = _V13_LEAF_RE.match(leaf)
    if m_leaf is None:
        return None
    seed = int(m_leaf.group("seed"))
    is_cloud = m_leaf.group("cloud") is not None
    is_fat = m_leaf.group("fat") is not None

    parent = parts[-2]
    m_nb = _V13_NBETA_RE.match(parent)
    if m_nb is None:
        return None
    n = int(m_nb.group("n"))
    beta = int(m_nb.group("beta"))
    conv_mt = int(m_nb.group("mt")) if m_nb.group("mt") else None

    # Campaign-specific path middles between seeds/<campaign>/ and the
    # n_beta leaf. Extract precision / max_tours / fplll_version as
    # relevant.
    mid = parts[3:-2]
    q = 97
    precision: Optional[int] = None
    max_tours: Optional[int] = None
    fplll_version: Optional[str] = None

    if campaign == "main":
        # seeds/main/q97/n{n}_beta{b}/
        if mid != ["q97"]:
            return None
    elif campaign == "q3329":
        # seeds/q3329/p{prec}_mt{mt}/n{n}_beta{b}/
        if len(mid) != 1:
            return None
        m_q = re.match(r"^p(?P<p>\d+)_mt(?P<mt>\d+)$", mid[0])
        if m_q is None:
            return None
        q = 3329
        precision = int(m_q.group("p"))
        max_tours = int(m_q.group("mt"))
    elif campaign == "cliff500":
        if mid != ["q97"]:
            return None
    elif campaign == "fplll_sensitivity":
        # seeds/fplll_sensitivity/v{x_y_z}/q97/n{n}_beta{b}/
        if len(mid) != 2 or mid[1] != "q97":
            return None
        ver_slug = mid[0]
        if not ver_slug.startswith("v"):
            return None
        fplll_version = ver_slug[1:].replace("_", ".")
    elif campaign == "tours3x":
        if mid != ["q97"]:
            return None
    elif campaign == "convergence":
        if mid != ["q97"]:
            return None
        max_tours = conv_mt
    else:
        return None

    return {
        "campaign": campaign,
        "n": n, "beta": beta, "seed": seed, "q": q,
        "precision": precision, "max_tours": max_tours,
        "fplll_version": fplll_version,
        "is_cloud": is_cloud, "is_fat": is_fat,
    }


def _classify_v13(
    path: str,
    rel_path: str,
    generated_utc: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Build a manifest entry from a v1.3-layout path, or reject it."""
    parsed = _parse_v13_path(rel_path)
    if parsed is None:
        return None, f"path does not match v1.3 layout: {rel_path}"

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

    # Cross-check path-derived vs content-derived params.
    if data["n"] != parsed["n"] or data["beta"] != parsed["beta"] \
            or data["seed"] != parsed["seed"]:
        return None, (
            f"path/content mismatch: path (n,β,seed)="
            f"({parsed['n']},{parsed['beta']},{parsed['seed']}) vs "
            f"content ({data['n']},{data['beta']},{data['seed']})"
        )
    if data["q"] != parsed["q"]:
        return None, (
            f"q mismatch: path implies q={parsed['q']}, "
            f"content says q={data['q']}"
        )

    is_fat = parsed["is_fat"]
    advantage: Optional[float]
    if is_fat:
        advantage = None
    elif parsed["campaign"] == "tours3x":
        adv_source = data.get("advantage_equal_tours")
        if not isinstance(adv_source, (int, float)) or not math.isfinite(adv_source):
            return None, f"advantage_equal_tours not finite (got {adv_source!r})"
        advantage = float(adv_source)
    else:
        adv_source = data.get("advantage")
        if not isinstance(adv_source, (int, float)) or not math.isfinite(adv_source):
            return None, f"advantage not finite (got {adv_source!r})"
        advantage = float(adv_source)

    # status check: same rules as legacy walker
    if not is_fat and parsed["campaign"] not in ("tours3x", "convergence"):
        if data.get("status") != "completed":
            return None, f"status != 'completed' (got {data.get('status')!r})"

    tags: list[str] = []
    if parsed["is_cloud"]:
        tags.append("cloud")
    if is_fat:
        tags.append("fat")
    # tours3x legacy tag (single-runner campaign; all v1.3 seeds are 3x-variant)
    if parsed["campaign"] == "tours3x":
        tags.append("3x")

    st = os.stat(path)
    entry = {
        "campaign": parsed["campaign"],
        "path": os.path.relpath(os.path.realpath(path)),
        "n": parsed["n"],
        "beta": parsed["beta"],
        "seed": parsed["seed"],
        "q": parsed["q"],
        "precision": parsed["precision"] if parsed["precision"] is not None
                     else data.get("precision"),
        "max_tours": parsed["max_tours"] if parsed["max_tours"] is not None
                     else data.get("max_tours"),
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
    if parsed["fplll_version"] is not None:
        entry["fplll_version"] = parsed["fplll_version"]
    return entry, None


def walk(results_root: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Scan results_root for seed JSONs via both the legacy-CAMPAIGN_DIRS
    walker and the v1.3 results/seeds/ native walker. Entries dedup by
    canonical (os.path.realpath) destination so a file reachable via
    both a pre-v1.3 symlink and its new canonical path lands once.

    Returns (entries, rejects).
    """
    generated_utc = dt.datetime.now(tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rejects: list[tuple[str, str]] = []
    # keyed by canonical realpath → entry
    by_real: dict[str, dict] = {}

    # ----- legacy walker -----
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
            real = os.path.realpath(path)
            by_real.setdefault(real, entry)

    # ----- v1.3 native walker -----
    seeds_root = os.path.join(results_root, "seeds")
    results_leaf = os.path.basename(os.path.abspath(results_root)) or "results"
    if os.path.isdir(seeds_root):
        for root, _dirs, files in os.walk(seeds_root):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(root, fname)
                if os.path.islink(path):
                    continue
                # Build a path whose first component is "results" so
                # _parse_v13_path's shape check lines up regardless of
                # where results_root sits in the filesystem (repo root,
                # tmp_path, etc.).
                rel_under_results = os.path.relpath(path, results_root)
                rel_path = os.path.join(results_leaf, rel_under_results) \
                    if results_leaf == "results" \
                    else os.path.join("results", rel_under_results)
                entry, reason = _classify_v13(path, rel_path, generated_utc)
                if entry is None:
                    rejects.append((path, reason))
                    continue
                real = os.path.realpath(path)
                # If the legacy walker already indexed the same file via
                # a symlink, keep the legacy entry (preserves existing
                # tag/category semantics). Otherwise use the v1.3 entry.
                by_real.setdefault(real, entry)

    entries = list(by_real.values())
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
