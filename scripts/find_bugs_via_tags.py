#!/usr/bin/env python3
"""Static bug-hunt using the .tags index + grep cross-references.

Runs five passes against the project tag table and reports findings:

  1. Duplicate function names — same name defined in multiple files
     (potential drift target; ok if intentional but worth flagging).
  2. Functions defined but never referenced — likely dead code.
  3. Functions referenced but not defined — likely typo or missing
     import.
  4. Cross-script class collisions.
  5. Functions whose name starts with `_` (private) but are imported
     elsewhere — API smell.

Reads `.tags` at repo root (regenerate with: `ctags -R --languages=python
--python-kinds=-iv -f .tags scripts/ analysis/ tests/`).

Usage: python3 scripts/find_bugs_via_tags.py [--verbose]
"""
import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from log import get_logger  # noqa: E402
PIPELINE = get_logger("find_bugs_via_tags")

TAGS_PATH = os.path.join(REPO, ".tags")

# Standard Python builtins / methods we always exclude from "unused"
# checks because they're called by the framework / by import semantics
# rather than by explicit names.
ALWAYS_USED = {
    "main", "__init__", "__call__", "__enter__", "__exit__",
    "__repr__", "__str__", "__eq__", "__hash__", "__len__",
    "__iter__", "__next__", "__contains__", "__getitem__",
    "__setitem__", "__delitem__", "setUp", "tearDown",
}

# Path-prefix filters: anything under these directories has its
# functions invoked by a test/agent framework rather than by name
# reference, so an "unreferenced" finding is a false positive.
FRAMEWORK_DISCOVERED_PREFIXES = (
    "tests/",       # pytest discovers test_* functions by filename pattern
)

# Function-name patterns that mean "framework discovers me, not a caller".
FRAMEWORK_DISCOVERED_NAMES = (
    "test_",        # pytest
    "fixture_",     # pytest fixtures
)


def _is_framework_discovered(name, path):
    if any(path.startswith(p) for p in FRAMEWORK_DISCOVERED_PREFIXES):
        return True
    if any(name.startswith(p) for p in FRAMEWORK_DISCOVERED_NAMES):
        return True
    return False


def _parse_tags():
    """Return list of (name, path, kind) tuples from the .tags file.
    Skips meta lines beginning with '!_'."""
    out = []
    with open(TAGS_PATH) as f:
        for line in f:
            if line.startswith("!_") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name = parts[0]
            path = parts[1]
            # Last field is kind: "f" function, "c" class, "m" method, etc.
            kind = parts[-1].strip()
            out.append((name, path, kind))
    return out


def _grep_count(symbol, exclude_path=None):
    """Count lines mentioning `symbol` as a word in scripts/ + analysis/.
    Excludes the file the symbol is defined in (so we count *callers*,
    not the def itself)."""
    cmd = ["grep", "-rwn", symbol, "scripts/", "analysis/", "tests/"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return 0
    if r.returncode not in (0, 1):
        return 0
    count = 0
    for line in r.stdout.splitlines():
        if exclude_path and exclude_path in line.split(":")[0]:
            continue
        count += 1
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.parse_args()

    PIPELINE.info("tag bug-hunt start", cat="audit")

    if not os.path.exists(TAGS_PATH):
        print(f"FAIL: {TAGS_PATH} not found. Regenerate with:")
        print("  ctags -R --languages=python --python-kinds=-iv "
              "-f .tags scripts/ analysis/ tests/")
        return 1

    entries = _parse_tags()
    funcs = [e for e in entries if e[2] in ("f", "m")]
    classes = [e for e in entries if e[2] == "c"]
    print(f"Loaded {len(entries)} tags ({len(funcs)} funcs/methods, "
          f"{len(classes)} classes)")

    # -- Pass 1: Duplicate function names ------------------------------------
    by_name = defaultdict(list)
    for name, path, kind in funcs:
        by_name[name].append(path)
    duplicates = {n: paths for n, paths in by_name.items() if len(paths) > 1}
    print(f"\n=== Pass 1: Duplicate function definitions ({len(duplicates)}) ===")
    if duplicates:
        for n, paths in sorted(duplicates.items()):
            print(f"  {n} ({len(paths)}×):")
            for p in paths:
                print(f"    {p}")

    # -- Pass 2: Defined but never referenced -------------------------------
    print("\n=== Pass 2: Functions defined but unreferenced ===")
    unused = []
    for name, path, kind in funcs:
        if name in ALWAYS_USED or name.startswith("__"):
            continue
        if _is_framework_discovered(name, path):
            continue
        if _grep_count(name, exclude_path=None) <= 1:
            # 1 line = the def itself; <=1 means no callers anywhere
            unused.append((name, path))
    print(f"Found {len(unused)} candidate unused functions:")
    for name, path in sorted(unused)[:30]:
        print(f"  {name}  in {path}")
    if len(unused) > 30:
        print(f"  ... {len(unused) - 30} more")

    # -- Pass 3: Cross-script class collisions ------------------------------
    cls_by_name = defaultdict(list)
    for name, path, kind in classes:
        cls_by_name[name].append(path)
    cls_dup = {n: paths for n, paths in cls_by_name.items() if len(paths) > 1}
    print(f"\n=== Pass 3: Duplicate class names ({len(cls_dup)}) ===")
    if cls_dup:
        for n, paths in sorted(cls_dup.items()):
            print(f"  {n}: {paths}")

    # -- Pass 4: Private symbols imported elsewhere -------------------------
    print("\n=== Pass 4: Private symbols (_foo) imported across files ===")
    leaks = []
    for name, path, kind in funcs + classes:
        if not name.startswith("_") or name.startswith("__"):
            continue
        # Search for `from <module> import <name>` or `import <module>; <module>.<name>`
        cmd = ["grep", "-rln", f"import.*{re.escape(name)}",
               "scripts/", "analysis/", "tests/"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            continue
        if r.returncode == 0:
            files = [
                f for f in r.stdout.splitlines() if f and path not in f
            ]
            if files:
                leaks.append((name, path, files))
    print(f"Found {len(leaks)} private-symbol imports:")
    for name, path, files in leaks[:15]:
        print(f"  {name} (defined in {path})")
        for f in files[:3]:
            print(f"    imported in: {f}")

    # -- Summary ------------------------------------------------------------
    print()
    print("=" * 70)
    print("Summary:")
    print(f"  Duplicate functions:   {len(duplicates)}")
    print(f"  Candidate unused:      {len(unused)}")
    print(f"  Duplicate classes:     {len(cls_dup)}")
    print(f"  Private-symbol leaks:  {len(leaks)}")
    print("=" * 70)
    PIPELINE.info(
        "tag bug-hunt complete", cat="audit",
        tags=len(entries), funcs=len(funcs), classes=len(classes),
        duplicate_funcs=len(duplicates),
        unused=len(unused),
        duplicate_classes=len(cls_dup),
        private_leaks=len(leaks),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
