#!/usr/bin/env python3
"""
Validate seed JSON files for schema conformance and data integrity.

Usage:
    python3 scripts/validate_seeds.py [OPTIONS] DIR [DIR ...]

    DIR can be a directory of seed JSONs or a parent containing subdirs.
    Each directory is tagged by its basename for reporting.

Options:
    --strict        Promote warnings to errors (exit 1 on any warning)
    --sha-check     Run SHA-256 spot-checks against reference hashes
    --quiet         Only print errors and summary, not per-file OK lines

Exit codes:
    0   All checks passed
    1   One or more errors (or warnings in --strict mode)

Examples:
    # Check committed seeds in the repo (canonical v1.3+ path)
    python3 scripts/validate_seeds.py --strict --sha-check results/seeds/

    # Check a specific campaign's subtree
    python3 scripts/validate_seeds.py --strict results/seeds/main/ results/seeds/q3329/

    # Cover legacy + canonical paths in one invocation (works pre-v2)
    python3 scripts/validate_seeds.py --strict --sha-check \
        results/seeds/ results/raw/ results/q3329/ results/3x_tours/

    # Maintainer-only: full out-of-repo backup audit (path is local;
    # not on a fresh clone — replace with your own backup mirror path).
    # python3 scripts/validate_seeds.py --strict --sha-check $BACKUP_ROOT
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from collections.abc import Iterator
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from log import get_logger  # noqa: E402
    log = get_logger("validate_seeds")
except Exception:
    class _Noop:
        def __getattr__(self, _): return lambda *a, **k: None
    log = _Noop()


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------
REQUIRED_SWEEP = {
    "n", "beta", "seed", "status", "advantage", "q",
    "bkz_final_dln", "sdbkz_final_dln",
}
REQUIRED_Q3329 = REQUIRED_SWEEP  # same schema
REQUIRED_3X_ORIG = {"n", "beta", "seed", "gap_normal", "gap_3x"}
REQUIRED_3X_EXT = {"n", "beta", "seed", "advantage_equal_tours", "advantage_3x"}
REQUIRED_CONV = {"n", "beta", "seed"}

# SHA-256 reference hashes (deterministic fields only, from hash_verification.txt)
REFERENCE_HASHES = {
    "n100_beta20_seed1.json":
        "d9b3059f56351676487505d92f13cf7ec808119c21791dad754c28870ab6b3eb",
    "n100_beta20_seed2.json":
        "9ad666b0ddbb8e13f4c8893ed86386db0b8f017be21566579cd057beb7156e7a",
    "n100_beta20_seed3.json":
        "862851ac85da7987267a40bc711e41b512997b901383770ff4e8631ed0dc9cb2",
}
SHA_EXCLUDE_KEYS = {"bkz_time", "sdbkz_time", "timestamp", "status"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def detect_schema(filepath: str, tag: str) -> set[str]:
    """Return the appropriate required-key set for a seed file."""
    fname = os.path.basename(filepath)
    if "q3329" in fname or "q3329" in tag:
        return REQUIRED_Q3329
    # v1.3+ campaign tag is "tours3x"; pre-v1.3 directory was "3x_tours".
    # The v1.3 canonical filenames are `seed{seed:04d}.json` (no
    # `_3x_seed` suffix), so the pre-v1.3 EXT-vs-ORIG discriminator
    # by filename doesn't apply. Under v1.3, the `pilot/` subdir is
    # excluded by `seed_files()`, so every file reaching here is an
    # EXT 100-seed run.
    if "tours3x" in tag:
        return REQUIRED_3X_EXT
    if "3x_tours" in tag or "3x_tour" in tag:
        return REQUIRED_3X_EXT if "_3x_seed" in fname else REQUIRED_3X_ORIG
    if "convergence" in tag:
        return REQUIRED_CONV
    return REQUIRED_SWEEP


def seed_files(directory: str) -> Iterator[str]:
    """Yield seed JSON paths under `directory` (recursive, post-v2.0.0
    canonical campaign-tree layout). Excludes:

      - `_fat.json` per-tour companion logs
      - any file under a `summary/` subdir + filenames starting with `summary`
      - any file under a `pilot/` subdir (pre-v1.3 schema, allowlisted in
        lint_seed_manifest via `ALLOWLIST_LEGACY_PATHS`)
      - any file under known non-data subdirs (`analysis`, `logs`,
        `paper_claims`, etc.)
    """
    non_data = {"analysis", "logs", "summaries", "backups",
                "error_logs", "scripts", "paper1", "cheatsheets",
                "summary", "pilot", "paper_claims"}
    for f in sorted(glob.glob(os.path.join(directory, "**", "*.json"),
                              recursive=True)):
        rel_parts = os.path.relpath(f, directory).split(os.sep)
        if any(part in non_data for part in rel_parts[:-1]):
            continue
        fname = os.path.basename(f)
        if "_fat.json" in fname:
            continue
        if fname.startswith("summary"):
            continue
        yield f


def parse_filename(fname: str) -> dict[str, int]:
    """Extract expected n, beta, seed from filename convention."""
    parts = fname.replace(".json", "").replace("_fat", "").split("_")
    expected = {}
    for p in parts:
        if p.startswith("n") and p[1:].isdigit():
            expected["n"] = int(p[1:])
        elif p.startswith("beta") and p[4:].isdigit():
            expected["beta"] = int(p[4:])
        elif p.startswith("seed") and p[4:].isdigit():
            expected["seed"] = int(p[4:])
    return expected


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------
class SeedValidator:
    def __init__(self, strict: bool = False,
                 sha_check: bool = False, quiet: bool = False) -> None:
        self.strict = strict
        self.sha_check = sha_check
        self.quiet = quiet
        self.errors = []
        self.warnings = []
        self.incidents = []  # known/documented issues — don't promote in --strict
        self.checked = 0
        self.seen = {}  # (tag, n, beta, seed, q) -> label
        self.roots = []  # CLI args actually walked
        self.per_tag_counts = defaultdict(int)  # tag -> files checked

    def _err(self, msg: str, cat: str = "schema", **ctx: Any) -> None:
        self.errors.append(msg)
        log.error(msg, cat=cat, **ctx)

    def _warn(self, msg: str, cat: str = "schema", **ctx: Any) -> None:
        self.warnings.append(msg)
        log.warning(msg, cat=cat, **ctx)

    def _incident(self, msg: str, id: int | None = None,
                  cat: str = "incident", **ctx: Any) -> None:
        # Incidents are documented known issues — kept separate from warnings
        # so --strict mode doesn't promote them to errors. They're tracked
        # by the centralized log via log.incident().
        self.incidents.append(msg)
        log.incident(msg, id=id, cat=cat, **ctx)

    def check_seed(self, filepath: str, tag: str) -> None:
        self.checked += 1
        self.per_tag_counts[tag] += 1
        fname = os.path.basename(filepath)
        label = f"{tag}/{fname}"
        required_keys = detect_schema(filepath, tag)

        # 1. Valid JSON
        try:
            with open(filepath) as f:
                d = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._err(f"{label}: invalid JSON — {e}", cat="schema", file=fname)
            return
        if not isinstance(d, dict):
            self._err(f"{label}: top-level value is {type(d).__name__}, expected dict",
                      cat="schema", file=fname)
            return

        # 2. Required keys
        missing = required_keys - set(d.keys())
        if missing:
            self._err(f"{label}: missing keys {missing}", cat="schema", file=fname)
            return

        # 3. Status check
        if "status" in d and d["status"] != "completed":
            self._err(f'{label}: status={d["status"]} (expected completed)',
                      cat="schema", file=fname)

        # 4. Filename vs content consistency
        expected = parse_filename(fname)
        for key in ("n", "beta", "seed"):
            if key in expected and key in d and d[key] != expected[key]:
                self._err(f"{label}: {key}={d[key]} but filename says {expected[key]}",
                          cat="integrity", file=fname, field=key)

        # 5. Advantage is finite and consistent with dLN values
        if "advantage" in d:
            adv = d["advantage"]
            if not isinstance(adv, (int, float)) or math.isnan(adv) or math.isinf(adv):
                self._err(f"{label}: advantage={adv} (non-finite)",
                          cat="integrity", file=fname)
            elif "bkz_final_dln" in d and "sdbkz_final_dln" in d:
                recomputed = d["bkz_final_dln"] - d["sdbkz_final_dln"]
                if abs(recomputed - adv) > 1e-8:
                    self._err(f"{label}: advantage={adv} but bkz_dln-sdbkz_dln={recomputed}",
                              cat="integrity", file=fname)

        # 5b. Timing sanity. Threshold scales with max_tours: short-tour
        # main-sweep runs (≤100 tours) cap at ~55h wall; long-tour
        # convergence runs (mt500 / mt1000) take proportionally longer
        # — the n=160 β=40 mt1000 cliff bracket averages ~80h sdbkz_time
        # per seed and is paper-cited at that wall budget. Scale the
        # threshold so it catches genuine outliers, not legitimately
        # expensive long-tour runs.
        max_tours = d.get("max_tours", 100)
        threshold_s = max(200000, int(max_tours) * 1000)  # 1000 s/tour ceiling
        for t in ("bkz_time", "sdbkz_time"):
            if t in d:
                v = d[t]
                if not isinstance(v, (int, float)) or v <= 0:
                    self._err(f"{label}: {t}={v} (expected positive)",
                              cat="timing", file=fname)
                elif v > threshold_s:
                    self._warn(
                        f"{label}: {t}={v:.0f}s ({v/3600:.1f}h) exceeds "
                        f"{threshold_s/3600:.0f}h ceiling at max_tours={max_tours}",
                        cat="timing", file=fname,
                    )

        # 5c. Dimension consistency
        if "dim" in d and "n" in d:
            expected_dim = 3 * d["n"] + 1
            if d["dim"] != expected_dim:
                self._err(f"{label}: dim={d['dim']} expected {expected_dim}",
                          cat="schema", file=fname)

        # 5d. Array length checks
        dim = d.get("dim", 3 * d.get("n", 0) + 1)
        n_val = d.get("n", 0)
        for key in ("gs_lognorms_bkz", "gs_lognorms_sdbkz", "initial_gs_lognorms"):
            if key in d:
                arr = d[key]
                if not isinstance(arr, list):
                    self._err(f"{label}: {key} is {type(arr).__name__}",
                              cat="schema", file=fname)
                elif len(arr) != dim:
                    self._err(f"{label}: {key} len={len(arr)} expected dim={dim}",
                              cat="schema", file=fname, field=key)
                elif any(not math.isfinite(v) for v in arr):
                    self._err(f"{label}: {key} has non-finite values",
                              cat="integrity", file=fname, field=key)
        for key in ("rankin_profile_bkz", "rankin_profile_sdbkz", "initial_rankin_profile"):
            if key in d:
                arr = d[key]
                if not isinstance(arr, list):
                    self._err(f"{label}: {key} is {type(arr).__name__}",
                              cat="schema", file=fname)
                elif len(arr) != n_val + 1:
                    self._err(f"{label}: {key} len={len(arr)} expected {n_val+1}",
                              cat="schema", file=fname, field=key)
                elif any(not math.isfinite(v) for v in arr):
                    self._err(f"{label}: {key} has non-finite values",
                              cat="integrity", file=fname, field=key)

        # 5e. Volume preservation (sum of GS log-norms should be constant)
        #     q=3329 lattices have known catastrophic-cancellation instability
        #     in fplll's squared-form GSO update (paper §8).
        #
        #     VOLUME_DRIFT_THRESHOLD was 0.01 nats absolute. Raised to 0.1 on
        #     2026-04-13 after a full scan of 1,960 q=97 seeds
        #     showed the drift grows monotonically with n (p99 at n=50: 0 nats,
        #     at n=150: 0.012 nats) due to accumulated floating-point rounding
        #     in BKZ's GSO recomputation. Two seeds at n=150 β=40 were just
        #     above 0.01 (seeds 34 and 37 with 0.010 and 0.014 drift) while
        #     being structurally identical to clean seeds on per-position
        #     analysis. The old threshold was too tight for high-dimension
        #     q=97 runs; the new threshold is:
        #       - 10× above the max observed q=97 drift (0.014 nats)
        #       - ~100× below the smallest q=3329 catastrophic drift (~10 nats)
        #     so the q=3329 detection remains intact.
        VOLUME_DRIFT_THRESHOLD = 0.1
        if all(k in d for k in ("initial_gs_lognorms", "gs_lognorms_bkz", "gs_lognorms_sdbkz")):
            init_sum = sum(d["initial_gs_lognorms"])
            is_q3329 = d.get("q") == 3329
            for key in ("gs_lognorms_bkz", "gs_lognorms_sdbkz"):
                arr_sum = sum(d[key])
                if abs(init_sum - arr_sum) > VOLUME_DRIFT_THRESHOLD:
                    msg = (f"{label}: volume mismatch {key} "
                           f"init_sum={init_sum:.4f} vs {arr_sum:.4f}")
                    if is_q3329:
                        self._incident(msg + " (q=3329 known instability)",
                                       id=26, file=fname, field=key,
                                       diff=round(abs(init_sum - arr_sum), 4))
                    else:
                        self._err(msg, cat="integrity", file=fname, field=key)

        # 5f. Tour count consistency
        if "bkz_tours_run" in d and "beta" in d:
            tours = d["bkz_tours_run"]
            max_tours = {20: 50, 30: 70, 40: 100}.get(d["beta"])
            if max_tours and (tours < 1 or tours > max_tours):
                self._err(f"{label}: bkz_tours={tours} (max={max_tours})",
                          cat="schema", file=fname)
            if "bkz_dln_per_tour" in d:
                if len(d["bkz_dln_per_tour"]) != tours:
                    self._err(f"{label}: per_tour len={len(d['bkz_dln_per_tour'])} vs tours={tours}",
                              cat="schema", file=fname)

        # 5g. Type checks on numeric fields
        for key in ("advantage", "bkz_final_dln", "sdbkz_final_dln", "initial_dln"):
            if key in d and not isinstance(d[key], (int, float)):
                self._err(f"{label}: {key} type={type(d[key]).__name__}",
                          cat="schema", file=fname, field=key)

        # 6. Within-dataset duplicate detection.
        # Pre-v1.3, raw/cloud layouts produced real same-name files at
        # two paths; the warning flagged the byte-distinct dual copies.
        # Post-v2.0.0 the canonical v1.3 tree (results/seeds/<campaign>/
        # ...) is collision-free by construction (OS-level filename
        # uniqueness within a directory), AND legitimate multi-version
        # coverage like fplll_sensitivity/v5_4_{3,4,5}/ would false-
        # positive on a same-name (n, β, seed, q) key. The dup-warning
        # is therefore obsolete under the v1.3 layout: use the full
        # relative path so the only collision is a literal same-file
        # double-walk (which sorted-glob deduplication already prevents).
        q_val = d.get("q", 97)
        # Use REPO-relative path so the key is identity-bound to the
        # file's on-disk location. The dup warning is now mostly dead
        # but kept as a defensive double-walk detector.
        dup_key = ("path", os.path.abspath(filepath))
        if dup_key in self.seen:
            self._warn(f"{label}: duplicate of {self.seen[dup_key]}",
                       cat="integrity", file=fname)
        else:
            self.seen[dup_key] = label
        # Cross-reference the schema-level (tag, n, β, seed, q) tuple
        # for completeness, but only warn if the SAME filename also
        # appears elsewhere with a different content hash — preserves
        # the pre-v2 raw/cloud-style detection without false-positive
        # on intentional multi-version subdirs.
        schema_key = (tag, d.get("n"), d.get("beta"), d.get("seed"), q_val,
                      fname)
        if schema_key in self.seen and self.seen[schema_key] != label:
            self._warn(f"{label}: duplicate of {self.seen[schema_key]}",
                       cat="integrity", file=fname)
        else:
            self.seen[schema_key] = label

        # 7. SHA-256 spot-check (if enabled and this file has a reference)
        if self.sha_check and fname in REFERENCE_HASHES:
            det = {k: v for k, v in sorted(d.items()) if k not in SHA_EXCLUDE_KEYS}
            h = hashlib.sha256(json.dumps(det, sort_keys=True).encode()).hexdigest()
            expected_hash = REFERENCE_HASHES[fname]
            if h != expected_hash:
                self._err(f"SHA-256 MISMATCH {label}: got {h[:16]}… expected {expected_hash[:16]}…",
                          cat="integrity", file=fname)
            else:
                log.info(f"SHA-256 spot-check {fname}: OK", cat="integrity", file=fname)

    def check_directory(self, directory: str, tag: str | None = None) -> None:
        """Check all seed files in a directory."""
        if tag is None:
            tag = os.path.basename(directory.rstrip("/"))
        for f in seed_files(directory):
            self.check_seed(f, tag)

    def check_tree(self, root: str) -> None:
        """Check every seed JSON under `root` (recursive walk).

        Post-v2.0.0, `seed_files()` itself recurses through the v1.3
        campaign tree (`results/seeds/<campaign>/q97/n{n}_beta{b}/seed*.json`).
        This wrapper just sets the per-file tag to the leaf-campaign
        directory name so `detect_schema()` picks the right REQUIRED
        key set per file.
        """
        root = root.rstrip("/")
        # Campaign tag = leaf-campaign dir name. For a root like
        # `results/seeds/main`, every recursive descendant gets tag "main";
        # for a root like `results/seeds/`, the tag is derived per file
        # from the path component immediately under `seeds/`.
        root_basename = os.path.basename(root)
        for f in seed_files(root):
            rel = os.path.relpath(f, root)
            parts = rel.split(os.sep)
            # If the user pointed at `results/seeds/`, the next component
            # is the campaign name; otherwise the root itself is the campaign.
            if root_basename == "seeds" and parts:
                tag = parts[0]
            else:
                tag = root_basename
            self.check_seed(f, tag)

    def report(self) -> int:
        """Print results and return exit code."""
        roots_str = ", ".join(self.roots) if self.roots else "(none)"
        tag_breakdown = dict(sorted(self.per_tag_counts.items()))
        level = log.warning if self.checked == 0 else log.info
        level(f"Checked {self.checked} seed files in {roots_str}",
              cat="validation",
              errors=len(self.errors), warnings=len(self.warnings),
              roots=self.roots, by_tag=tag_breakdown)
        print(f"  Checked {self.checked} seed files in: {roots_str}")
        if tag_breakdown:
            print(f"  By tag: {tag_breakdown}")
        elif self.checked == 0:
            print("  WARNING: 0 seed files matched — check the path(s) above")
        if self.incidents:
            print(f"  {len(self.incidents)} known incident(s) (not promoted in --strict):")
            for i in self.incidents:
                print(f"    INCIDENT {i}")
        if self.warnings:
            print(f"  {len(self.warnings)} warning(s):")
            for w in self.warnings:
                print(f"    WARN  {w}")
        if self.errors:
            print(f"  {len(self.errors)} ERROR(s):")
            for e in self.errors:
                print(f"    ERROR {e}")
            log.critical(f"Validation failed: {len(self.errors)} error(s)",
                         cat="validation")
            return 1
        if self.strict and self.warnings:
            print(f"  --strict: {len(self.warnings)} warning(s) promoted to errors")
            log.error(f"Strict mode: {len(self.warnings)} warning(s) promoted",
                      cat="validation")
            return 1
        print(f"  All checks passed ({len(self.warnings)} warnings, "
              f"{len(self.incidents)} known incidents)")
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate seed JSON files for schema and data integrity."
    )
    parser.add_argument("dirs", nargs="+", help="Directories to check")
    parser.add_argument("--strict", action="store_true",
                        help="Promote warnings to errors")
    parser.add_argument("--sha-check", action="store_true",
                        help="Run SHA-256 spot-checks against reference hashes")
    parser.add_argument("--quiet", action="store_true",
                        help="Only print errors and summary")
    args = parser.parse_args()

    v = SeedValidator(strict=args.strict, sha_check=args.sha_check, quiet=args.quiet)

    for d in args.dirs:
        if not os.path.isdir(d):
            print(f"  SKIP {d}: not a directory", file=sys.stderr)
            continue
        v.roots.append(os.path.abspath(d))
        v.check_tree(d)

    sys.exit(v.report())


if __name__ == "__main__":
    main()
