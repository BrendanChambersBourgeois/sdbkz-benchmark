#!/usr/bin/env python3
"""CI lint: every committed entry-point script must emit through
scripts/log.py to logs/pipeline.jsonl per CLAUDE.md §16.

Heuristic: a file under scripts/ or analysis/ is an "entry point" if
it has either `def main(` or `if __name__ == "__main__"`. Library
files (no main, just helper functions) are exempt — they are
caller-logged.

For each entry-point file, this lint checks the source for either
`from log import` or `get_logger(`. Files that fail the check are
listed; non-zero exit if any.

Allowlist for files we have audited and intentionally skip:
  - scripts/log.py itself (defines get_logger)
  - scripts/lint_logging.py (this file)
  - scripts/_*.py and analysis/_*.py (private helpers, library-only)
  - analysis/__init__.py
  - analysis/diagnostics.py, analysis/tables.py (helper modules
    consumed by paper_figures, no main entry point)

Usage:
  python3 scripts/lint_logging.py            # exit 0 = clean, 1 = fail
  python3 scripts/lint_logging.py --verbose  # show exempt files too
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files that are libraries (no main entry) but happen to start with a
# non-underscore name, OR files we have inspected and exempted.
EXEMPT = {
    "scripts/log.py",
    "scripts/lint_logging.py",
    "analysis/__init__.py",
    "analysis/diagnostics.py",
    "analysis/tables.py",
}

ENTRY_RE = re.compile(r"^\s*(def\s+main\s*\(|if\s+__name__\s*==\s*['\"]__main__['\"])",
                      re.MULTILINE)
LOGGER_RE = re.compile(r"from\s+log\s+import|get_logger\s*\(")


def _scan(directory):
    """Return list of (relpath, source_text) for *.py under directory,
    excluding files starting with _ at the leaf level."""
    out = []
    abs_dir = os.path.join(REPO, directory)
    if not os.path.isdir(abs_dir):
        return out
    for fname in sorted(os.listdir(abs_dir)):
        if not fname.endswith(".py"):
            continue
        rel = os.path.join(directory, fname)
        # Underscore-prefixed files are private helpers — skipped.
        if fname.startswith("_") and fname != "__init__.py":
            continue
        path = os.path.join(abs_dir, fname)
        with open(path) as f:
            out.append((rel, f.read()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    candidates = _scan("scripts") + _scan("analysis")
    failures = []
    skipped = []
    passed = []

    for rel, src in candidates:
        if rel in EXEMPT:
            skipped.append((rel, "exempt"))
            continue
        # Library file: no main, no __main__ guard — exempt
        if not ENTRY_RE.search(src):
            skipped.append((rel, "library (no main)"))
            continue
        # Entry point: must import logger
        if LOGGER_RE.search(src):
            passed.append(rel)
        else:
            failures.append(rel)

    print(f"Scanned {len(candidates)} .py files in scripts/ + analysis/")
    print(f"  Entry points logged:  {len(passed)}")
    print(f"  Library / exempt:     {len(skipped)}")
    print(f"  Entry points missing: {len(failures)}")

    if args.verbose:
        print("\nExempt:")
        for rel, why in skipped:
            print(f"  {rel}  ({why})")
        print("\nPassed:")
        for rel in passed:
            print(f"  {rel}")

    if failures:
        print("\nFAIL — these entry-point scripts do not import a logger:")
        for rel in failures:
            print(f"  {rel}")
        print()
        print("Per CLAUDE.md §16, every committed script must emit through")
        print("scripts/log.py to logs/pipeline.jsonl. Add at the top:")
        print()
        print("    from log import get_logger")
        print('    PIPELINE = get_logger("<filename_stem>")')
        print()
        print("And call `PIPELINE.info(...)` for at least start + complete")
        print("events in main(). If this file is genuinely a library with")
        print("no main entry point, add it to the EXEMPT set in")
        print("scripts/lint_logging.py with a one-line justification.")
        return 1

    print("\nPASS — all entry-point scripts have centralised logging wired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
