#!/usr/bin/env python3
"""Guard: refuse commits that add an un-allowlisted top-level directory.

Scoped to the public-repo / internal-archive boundary lesson from
INC-39 (2026-04-25). Adding a new top-level directory to the public
repo is almost always either intentional (in which case the allowlist
below should be edited in the same commit) or accidental (in which
case the commit should be reworked to put the artifact offline at
``/mnt/hgfs/Research/_archives/`` or under an existing top-level
directory). This guard surfaces the choice instead of letting it slip.

Behaviour:
- Reads the staged tree (``git diff --cached --name-only``) for use as
  a pre-commit hook.
- Falls back to ``git diff --name-only ORIGIN..HEAD`` for use as a
  CI step against the pushed history.
- A "top-level directory" = the first path component of any added file
  whose path contains a ``/``.
- Allowlist is hard-coded at module scope; bumping the allowlist is the
  way to legitimise a new top-level directory and forces the bump to
  appear in the same commit that introduces it.
- Exits 0 if every new top-level directory is allowlisted; exits 1
  otherwise with a one-line per-violation diagnostic naming the
  directory and the first file that introduced it.
- Always exits 0 when there are no staged changes (e.g. amend-only
  commits with no file delta).

Allowlist policy:
- New entries are paper-grade governance decisions; do not add lightly.
- Hidden directories (``.github/``, ``.claude/``, etc.) are listed
  explicitly because the heuristic would otherwise flag them on first
  introduction.
- Generated/runtime caches (``logs/``, ``.pytest_cache/``,
  ``.ruff_cache/``) are listed because they appear in working trees
  but should never be committed; the .gitignore is the actual guard
  for those — the allowlist entry just keeps this script from being
  noisy if a stale tree state slips through.
"""
from __future__ import annotations

import os
import subprocess
import sys

ALLOWED_TOP_LEVEL = frozenset({
    # Source + paper artifacts (paper-grade, deliberate).
    "analysis",
    "config",
    "docs",
    "examples",
    "paper",
    "patches",
    "results",
    "scripts",
    "tests",
    # Tooling / CI / local-config conventions (hidden, deliberate).
    ".github",
    ".claude",
    # Runtime caches — gitignored; allowlisted defensively so a stale
    # tree state does not produce a noisy false positive.
    "logs",
    ".pytest_cache",
    ".ruff_cache",
})


def _added_files(*, base: str | None = None) -> list[str]:
    """Return the list of files added in the diff under inspection.

    If ``base`` is provided, compares ``base..HEAD`` (CI mode). Else
    inspects the staging area (pre-commit hook mode).

    If the requested base is unreachable from the local clone (the
    common CI case where ``actions/checkout@v4`` does a shallow
    ``fetch-depth: 1`` and the previous tip isn't in history), falls
    back to scanning every top-level directory currently in HEAD —
    less precise but still catches any un-allowlisted directory and
    avoids erroring the build for a benign reason.
    """
    if base:
        cmd = ["git", "diff", "--name-only", "--diff-filter=A", f"{base}..HEAD"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return [line for line in proc.stdout.splitlines() if line.strip()]
        # Base unreachable in shallow clone — scan all tracked files
        # at HEAD as a conservative fallback. Filters down to one path
        # per top-level directory so the violation list is concise.
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout
        return [line for line in ls.splitlines() if line.strip() and "/" in line]
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=A"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def _top_level_violations(added_paths: list[str]) -> list[tuple[str, str]]:
    """Return [(top_level_dir, first_offending_path), ...] for any added
    file whose top-level directory is NOT in the allowlist.
    """
    seen: dict[str, str] = {}
    for path in added_paths:
        if "/" not in path:
            continue  # top-level file, not a new directory
        top = path.split("/", 1)[0]
        if top in ALLOWED_TOP_LEVEL:
            continue
        if top not in seen:
            seen[top] = path
    return sorted(seen.items())


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    base = argv[0] if argv else os.environ.get("CHECK_TLD_BASE")
    added = _added_files(base=base)
    if not added:
        return 0
    violations = _top_level_violations(added)
    if not violations:
        return 0
    print(
        "REFUSED: commit introduces un-allowlisted top-level directory(ies).",
        file=sys.stderr,
    )
    print(
        "(Per INC-39: new public-repo top-level dirs need explicit review.)",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    for top, sample in violations:
        print(f"  {top}/  (first added file: {sample})", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "If this directory belongs in the public repo, add it to "
        "ALLOWED_TOP_LEVEL in scripts/check_new_top_level_dirs.py "
        "in the same commit. If it does not, move the artifact to "
        "/mnt/hgfs/Research/_archives/ (offline) or under an existing "
        "top-level directory before re-staging.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
